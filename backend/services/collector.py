"""自动技术采集：从多来源抓取→AI抽取→候选待入库。

流程：读 sources 配置 -> 枚举新增目击条目 -> 抓取正文/摘要 -> LLM 抽取 ->
存候选表(待人工确认) -> 人工在界面「入库」后调用 commit_extraction 写库。
后台线程支持固定周期自动采集 + 手动触发，均共用同一 run 队列。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from backend.services.extractor import commit_extraction, extract_from_text
from backend.services.fetch_url import fetch_text, _system_proxies
from backend.store import GraphStore

ROOT = Path(__file__).resolve().parents[2]
SOURCES_FILE = ROOT / "collector_sources.json"
DB_PATH = ROOT / "data" / "collector.db"
MAX_TEXT = 8000          # 与抽取器一致
MAX_ITEMS_PER_SOURCE = 8
MAX_TOTAL = 40           # 单次运行提取上限（避免长时间占用 LLM）


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL DEFAULT '',
            site TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            payload TEXT,               -- 抽取 JSON；空表示未成功抽取
            status TEXT NOT NULL DEFAULT 'pending',  -- pending|done|skipped
            note TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cand_url ON candidates(url);")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS seen(url TEXT PRIMARY KEY, kind TEXT, site TEXT, added_at REAL);"
    )
    conn.commit()
    return conn


class Collector:
    """负责读取源、抓取、抽取、持久化候选、以及后台运行状态的线程。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job = {
            "running": False,
            "last_start": 0.0,
            "last_finish": 0.0,
            "processed": 0,
            "added": 0,
            "skipped": 0,
            "errors": 0,
            "message": "尚未运行",
        }

    # ---------- 状态 ----------
    def status(self) -> dict:
        with self._lock:
            return dict(self._job)

    def _update(self, **kw) -> None:
        with self._lock:
            self._job.update(kw)

    # ---------- 采集 ----------
    def run(self, force: bool = True) -> dict:
        """同步执行一次采集（供后台线程/任务调度调用），返回本次结果。"""
        with self._lock:
            if self._job["running"]:
                return {"started": True, "message": "采集正在运行中，请稍候"}
            self._job.update(
                running=True, last_start=time.time(), processed=0, added=0,
                skipped=0, errors=0, message="采集中…",
            )
        try:
            processed = added = skipped = errors = 0
            for entry in self._iter_new_items():
                processed += 1
                ok, note = self._handle_item(entry)
                if ok:
                    added += 1
                elif note == "skipped_no_text":
                    skipped += 1
                else:
                    errors += 1
                self._update(processed=processed, added=added, skipped=skipped, errors=errors)
                if added + skipped + errors >= MAX_TOTAL:
                    break
            msg = f"完成：处理 {processed}，新增候选 {added}，跳过 {skipped}，失败 {errors}"
            self._update(running=False, last_finish=time.time(), message=msg)
            return {"started": True, "message": msg, "added": added, "processed": processed}
        except Exception as exc:  # noqa: BLE001
            self._update(running=False, last_finish=time.time(), message=f"采集失败: {exc}")
            return {"started": True, "message": f"采集失败: {exc}"}

    def start_async(self) -> dict:
        """后台线程方式启动（手动 or 定时通用），立即返回。"""
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return {"started": True, "message": "后台采集已启动，可查看状态"}

    # ---------- 候选库操作 ----------
    def list_candidates(self, status: str = "pending", limit: int = 100) -> list[dict]:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id, kind, site, url, title, payload, status, note, created_at "
                "FROM candidates WHERE (? = '' OR status = ?) ORDER BY id DESC LIMIT ?",
                (status, status, int(limit)),
            ).fetchall()
            return [
                {
                    "id": r[0], "kind": r[1], "site": r[2], "url": r[3], "title": r[4],
                    "payload": json.loads(r[5]) if r[5] else None,
                    "status": r[6], "note": r[7], "created_at": r[8],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def commit_candidate(self, cand_id: int, store=None) -> dict:
        conn = _connect()
        row = conn.execute(
            "SELECT id, url, payload, status FROM candidates WHERE id=?", (cand_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "reason": "候选不存在"}
        _, url, payload, status = row
        if status == "done":
            return {"ok": False, "reason": "该候选已入库"}
        if not payload:
            return {"ok": False, "reason": "该候选无可入库内容（抽取未成功）"}
        from backend.history import get_history
        store = store if store is not None else GraphStore(history=get_history())
        try:
            written = commit_extraction(json.loads(payload), store=store)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"写入失败: {exc}"}
        conn.execute(
            "UPDATE candidates SET status='done', updated_at=? WHERE id=?",
            (time.time(), cand_id),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "url": url, "written": written}

    def reject_candidate(self, cand_id: int) -> dict:
        conn = _connect()
        cur = conn.execute(
            "UPDATE candidates SET status='skipped', note='user_rejected', updated_at=? WHERE id=?",
            (time.time(), cand_id),
        )
        conn.commit()
        conn.close()
        return {"ok": bool(cur.rowcount)}

    # ---------- 内部 ----------
    def _iter_new_items(self):
        sources = self._load_sources()
        return self._sources_to_items(sources)

    def _load_sources(self) -> list[dict]:
        if not SOURCES_FILE.exists():
            return []
        try:
            data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
            sources = data.get("sources") or []
            return [s for s in sources if s.get("url") or s.get("query")]
        except Exception:
            return []

    def _sources_to_items(self, sources: list[dict]):
        """把源配置展开为候选条目 (kind, site, url, title, text, already_known)。"""
        conn = _connect()
        known = set(r[0] for r in conn.execute("SELECT url FROM seen").fetchall())
        local_seen: set[str] = set()
        try:
            for src in sources:
                typ = src.get("type", "page")
                kind = src.get("kind", "资讯")
                site = src.get("site", "")
                try:
                    if typ == "arxiv":
                        items = self._arXiv_items(src)
                    elif typ == "feed":
                        items = self._feed_items(src.get("url", ""))
                    else:
                        items = self._page_items(src.get("url", ""))
                except Exception:  # noqa: BLE001
                    self._update(errors=self._job["errors"] + 1)
                    continue
                for it in items:
                    it.setdefault("kind", kind)
                    it.setdefault("site", site)
                    if not it.get("url"):
                        continue
                    if it.get("url") in known or it.get("url") in local_seen:
                        continue
                    local_seen.add(it.get("url"))
                    yield it
        finally:
            conn.close()

    def _handle_item(self, entry: dict) -> tuple[bool, str]:
        """抓取正文→抽取→入库候选。返回 (是否新增, 原因)。"""
        url = entry.get("url", "")
        text = (entry.get("text") or "").strip()
        title = (entry.get("title") or "").strip()
        if len(text) < 50:
            # 尝试从页面抓正文
            try:
                got = fetch_text(url)
                text = (got.get("text") or "").strip() or text
                if not title:
                    title = got.get("title") or ""
            except Exception:
                pass
        if len(text) < 50:
            self._mark_seen(url, entry.get("kind", ""), entry.get("site", ""))
            return False, "skipped_no_text"
        try:
            payload = extract_from_text(text, title=title, translate=True)
        except Exception:  # noqa: BLE001
            payload = None
        conn = _connect()
        try:
            if payload:
                conn.execute(
                    "INSERT OR IGNORE INTO candidates(kind, site, url, title, payload, status, note, created_at, updated_at) "
                    "VALUES (?,?,?,?,?, 'pending','',?,?)",
                    (entry.get("kind", ""), entry.get("site", ""), url, title,
                     json.dumps(payload, ensure_ascii=False), time.time(), time.time()),
                )
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO candidates(kind, site, url, title, payload, status, note, created_at, updated_at) "
                    "VALUES (?,?,?,?,NULL,'skipped','extract_failed',?,?)",
                    (entry.get("kind", ""), entry.get("site", ""), url, title, time.time(), time.time()),
                )
            conn.commit()
        finally:
            conn.close()
        self._mark_seen(url, entry.get("kind", ""), entry.get("site", ""))
        return bool(payload), "added"

    def _mark_seen(self, url: str, kind: str, site: str) -> None:
        if not url:
            return
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO seen(url, kind, site, added_at) VALUES (?,?,?,?)",
                (url, kind, site, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _arXiv_items(src: dict) -> list[dict]:
        import urllib.parse
        import xml.etree.ElementTree as ET
        from httpx import Client

        q = src.get("query", "")
        link = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": q, "max_results": int(src.get("max") or 5), "sortBy": "submittedDate", "sortOrder": "descending"}
        )
        proxy = _system_proxies()
        with Client(timeout=25, verify=False, proxy=proxy) as c:
            r = c.get(link)
            r.raise_for_status()
        root = ET.fromstring(r.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        items = []
        for e in root.findall("a:entry", ns):
            title = "".join(e.findtext("a:title", "", ns).split())
            url = (e.findtext("a:id", "", ns) or "").strip()
            summary = "".join((e.findtext("a:summary", "", ns) or "").split())
            items.append({"url": url, "title": title, "text": summary[:MAX_TEXT]})
        return items

    @staticmethod
    def _feed_items(url: str) -> list[dict]:
        import xml.etree.ElementTree as ET
        from httpx import Client

        proxy = _system_proxies()
        raw = ""
        with Client(timeout=25, verify=False, follow_redirects=True, proxy=proxy) as c:
            r = c.get(url)
            r.raise_for_status()
            raw = r.text
        items = []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            # 站点返回的不是 XML（常是 HTML/反爬页）→ 退回 HTML 列表页解析
            return Collector._page_items(url)
        for e in root.iter():
            tag = (e.tag or "").split("}")[-1]
            if tag == "item":
                title = e.findtext("title", default="") or ""
                link = e.findtext("link", default="") or ""
                desc = e.findtext("description", default="") or e.findtext("encoded", "", "http://purl.org/rss/1.0/modules/content/") or ""
                items.append({"url": link, "title": title, "text": desc[:MAX_TEXT]})
            elif tag == "entry":  # atom
                ns = {"a": "http://www.w3.org/2005/Atom"}
                title = "".join((e.findtext("a:title", "", ns) or "").split())
                link_el = e.find("a:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                summary = "".join((e.findtext("a:summary", "", ns) or "").split())
                items.append({"url": link, "title": title, "text": summary[:MAX_TEXT]})
        return items

    @staticmethod
    def _page_items(url: str) -> list[dict]:
        """抓列表页 HTML，提取候选文章链接（标题+URL），正文交给 _handle_item 再抓。"""
        import urllib.parse
        from lxml import html as lh

        with_http = url if url.startswith(("http://", "https://")) else "https://" + url
        proxy = _system_proxies()
        from httpx import Client
        with Client(timeout=25, verify=False, follow_redirects=True, proxy=proxy) as c:
            r = c.get(with_http)
            r.raise_for_status()
            raw = r.text
        doc = lh.fromstring(raw)
        base = urllib.parse.urljoin(with_http, "/")
        seen = set()
        out = []
        for a in doc.xpath("//a[@href]"):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            abs_url = urllib.parse.urljoin(with_http, href)
            if abs_url in seen:
                continue
            title = "".join(a.itertext()).strip()
            title = re.sub(r"\s+", " ", title).strip()
            if len(title) < 6:
                continue
            if not abs_url.startswith(("http://", "https://")):
                continue
            seen.add(abs_url)
            out.append({"url": abs_url, "title": title, "text": ""})
            if len(out) >= 30:
                break
        return out


def get_collector() -> Collector:
    global _collector
    if _collector is None:
        _collector = Collector()
    return _collector


_collector: Collector | None = None
