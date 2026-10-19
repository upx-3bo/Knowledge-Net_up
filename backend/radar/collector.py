"""技术情报雷达·独立采集引擎（不写图谱，只检索/搜集/整理）。

来源类型支持：
  arxiv_query      arXiv 搜索 API（可靠）
  semanticscholar   Semantic Scholar 搜索 API
  crossref         Crossref 论文检索 API
  rss              通用 RSS/Atom（失败自动回退 HTML 链接解析）
  sitemap          站点 sitemap.xml / robots.txt 定位 sitemap
  page             列表页 HTML 链接提取
  urls             手工 URL 清单

每个来源都做：探测可用性 -> 枚举条目 -> 去重入库；结果存 data/radar.db。
引擎本身与图谱解耦；后续集成时再通过 GraphStore 写库。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from httpx import Client

from backend.services.fetch_url import fetch_text, _system_proxies

ROOT = Path(__file__).resolve().parents[2]
SOURCES_FILE = ROOT / "backend" / "radar_sources.json"
DB_PATH = ROOT / "data" / "radar.db"
MAX_TEXT = 12000
MAX_ITEMS_PER_SOURCE = 12
PROBE_TIMEOUT = 10

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            site TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            collected_at REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
        );
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_radar_url ON items(url);")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            site TEXT, kind TEXT, type TEXT,
            config TEXT, enabled INTEGER DEFAULT 1,
            last_probe TEXT DEFAULT '', last_probe_at REAL, last_count INTEGER DEFAULT 0,
            updated_at REAL
        );
        """
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS seen(url TEXT PRIMARY KEY, collected_at REAL);"
    )
    conn.commit()
    return conn


class Radar:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job = {
            "running": False, "last_start": 0.0, "last_finish": 0.0,
            "processed": 0, "added": 0, "skipped": 0, "errors": 0, "message": "尚未运行",
        }

    # ---------- 状态 ----------
    def status(self) -> dict:
        with self._lock:
            return dict(self._job)

    def _update(self, **kw) -> None:
        with self._lock:
            self._job.update(kw)

    # ---------- 来源管理 ----------
    def _ensure_sources(self) -> None:
        """运行/探测/列表前确保 sources 表有内容（首次或换库后自动同步）。"""
        conn = _conn()
        try:
            n = conn.execute("SELECT count(*) FROM sources").fetchone()[0]
        finally:
            conn.close()
        if n == 0:
            self.sync_sources()

    def load_sources(self) -> list[dict]:
        if not SOURCES_FILE.exists():
            return []
        try:
            data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
            return data.get("sources") or []
        except Exception:
            return []

    def sync_sources(self) -> dict:
        """把 sources 配置文件同步到库（含启停状态自上次配置）+ 探测结果。"""
        conn = _conn()
        try:
            conn.execute("UPDATE sources SET enabled=0")
            for s in self.load_sources():
                conn.execute(
                    "INSERT INTO sources(id, site, kind, type, config, enabled) "
                    "VALUES (?,?,?,?,?,1) "
                    "ON CONFLICT(id) DO UPDATE SET site=excluded.site, kind=excluded.kind, "
                    "type=excluded.type, config=excluded.config, enabled=1",
                    (s.get("id"), s.get("site"), s.get("kind"), s.get("type"),
                     json.dumps(s, ensure_ascii=False)),
                )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "count": len(self.load_sources())}

    def list_sources(self) -> list[dict]:
        self._ensure_sources()
        cfg = {s.get("id"): s for s in self.load_sources()}
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT id, site, kind, type, enabled, last_probe, last_probe_at, last_count FROM sources "
                "ORDER BY kind, site"
            ).fetchall()
            out = []
            for r in rows:
                c = cfg.get(r[0]) or {}
                detail = c.get("query") or c.get("url") or ""
                out.append({"id": r[0], "site": r[1], "kind": r[2], "type": r[3], "enabled": bool(r[4]),
                            "last_probe": r[5], "last_probe_at": r[6], "last_count": r[7], "filter": detail[:60]})
            return out
        finally:
            conn.close()

    def set_enabled(self, source_id: str, enabled: bool) -> dict:
        conn = _conn()
        try:
            cur = conn.execute("UPDATE sources SET enabled=? WHERE id=?", (1 if enabled else 0, source_id))
            conn.commit()
            return {"ok": bool(cur.rowcount)}
        finally:
            conn.close()

    # ---------- 探测可用性 ----------
    def probe(self) -> dict:
        """并发探测来源可达性（每源独立超时，整体快速返回），不采集正文。"""
        import concurrent.futures

        self._ensure_sources()
        conn = _conn()
        results: list[dict] = []

        def probe_one(s: dict) -> dict:
            sid, typ = s.get("id"), s.get("type", "page")
            url = s.get("url", "")
            try:
                if typ == "arxiv_query" or typ == "arxiv":
                    status, detail, count = self._probe_arxiv(s)
                elif typ == "semanticscholar":
                    status, detail, count = self._probe_api("semanticscholar", s)
                elif typ == "crossref":
                    status, detail, count = self._probe_api("crossref", s)
                elif typ in ("rss", "sitemap", "page"):
                    status, detail, count = self._probe_http(url)
                else:  # urls / 其它
                    status, detail, count = "ok", "配置类来源", 0
                conn.execute("UPDATE sources SET last_probe=?, last_probe_at=?, last_count=? WHERE id=?",
                             (f"{status} {detail}", time.time(), int(count or 0), sid))
                conn.commit()
                return {"id": sid, "site": s.get("site"), "status": status, "detail": detail, "count": count}
            except Exception as e:  # noqa: BLE001
                try:
                    conn.execute("UPDATE sources SET last_probe=?, last_probe_at=? WHERE id=?",
                                 (f"error {type(e).__name__}: {str(e)[:60]}", time.time(), sid))
                    conn.commit()
                except Exception:
                    pass
                return {"id": sid, "site": s.get("site"), "status": "error", "detail": str(e)[:80], "count": 0}

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                futures = [ex.submit(probe_one, s) for s in self.load_sources()]
                for f in concurrent.futures.as_completed(futures):
                    results.append(f.result())
        finally:
            conn.close()
        return {"results": results}

    def _probe_http(self, url: str):
        if not url:
            return "skip", "无URL", 0
        with Client(timeout=PROBE_TIMEOUT, verify=False, follow_redirects=True, proxy=_system_proxies(), headers={"User-Agent": UA}) as c:
            r = c.get(url)
        return ("ok" if r.status_code < 400 else "blocked", f"HTTP {r.status_code}", 0)

    def _probe_arxiv(self, s: dict) -> tuple[str, str, int]:
        try:
            items = self._arxiv_items(s)
            return ("ok", f"items {len(items)}", len(items))
        except Exception as e:
            return ("error", str(e)[:60], 0)

    def _probe_api(self, which: str, s: dict) -> tuple[str, str, int]:
        try:
            items = self._api_items(which, s)
            return ("ok", f"items {len(items)}", len(items))
        except Exception as e:
            return ("error", str(e)[:60], 0)

    # ---------- 采集 ----------
    def run(self) -> dict:
        self._ensure_sources()
        with self._lock:
            if self._job["running"]:
                return {"started": True, "message": "雷达采集中，请稍候"}
            self._job.update(running=True, last_start=time.time(), processed=0, added=0,
                             skipped=0, errors=0, message="采集中…")
        conn = _conn()
        seen = set(r[0] for r in conn.execute("SELECT url FROM seen").fetchall())
        conn.close()
        try:
            processed = added = skipped = errors = 0
            for src in self._enabled_sources():
                sid = src.get("id")
                typ = src.get("type", "page")
                try:
                    if typ == "arxiv_query" or typ == "arxiv":
                        cand = self._arxiv_items(src)
                    elif typ == "semanticscholar":
                        cand = self._api_items("semanticscholar", src)
                    elif typ == "crossref":
                        cand = self._api_items("crossref", src)
                    elif typ == "rss":
                        cand = self._rss_items(src.get("url", ""))
                    elif typ == "sitemap":
                        cand = self._sitemap_items(src.get("url", ""))
                    elif typ == "urls":
                        cand = [{"url": u, "title": u, "text": ""} for u in (src.get("urls") or [])]
                    else:
                        cand = self._page_items(src.get("url", ""))
                except Exception as e:  # noqa: BLE001
                    errors += 1
                    self._update(processed=processed, added=added, skipped=skipped, errors=errors)
                    continue
                local_done = set()
                for it in cand:
                    processed += 1
                    url = (it.get("url") or "").strip()
                    if not url or url in seen or url in local_done:
                        skipped += 1
                        continue
                    try:
                        txt = (it.get("text") or "").strip()
                        if len(txt) < 50 and (typ == "urls" or typ == "sitemap" or typ == "page"):
                            got = fetch_text(url)
                            txt = (got.get("text") or "").strip() or txt
                            if not it.get("title"):
                                it["title"] = got.get("title") or url
                        if len(txt) < 50:
                            skipped += 1
                            continue
                        self._insert_item(sid, src, url, it, txt)
                        local_done.add(url)
                        added += 1
                    except Exception:  # noqa: BLE001
                        skipped += 1
                    self._update(processed=processed, added=added, skipped=skipped, errors=errors)
                    if added + skipped + errors >= 60:  # 单轮硬上限
                        break
                self._update(processed=processed, added=added, skipped=skipped, errors=errors)
            msg = f"完成：处理 {processed}，新增 {added}，跳过 {skipped}，失败 {errors}"
            self._update(running=False, last_finish=time.time(), message=msg)
            return {"started": True, "message": msg, "added": added}
        except Exception as exc:  # noqa: BLE001
            self._update(running=False, last_finish=time.time(), message=f"采集失败: {exc}")
            return {"started": True, "message": f"采集失败: {exc}"}

    def start_async(self) -> dict:
        threading.Thread(target=self.run, daemon=True).start()
        return {"started": True, "message": "雷达后台采集已启动，可查看进度"}

    def _enabled_sources(self) -> list[dict]:
        cfg = {s.get("id"): s for s in self.load_sources()}
        conn = _conn()
        try:
            rows = conn.execute("SELECT id FROM sources WHERE enabled=1").fetchall()
            return [cfg[r[0]] for r in rows if r[0] in cfg]
        finally:
            conn.close()

    def _insert_item(self, sid, src, url, it, txt) -> None:
        title = re.sub(r"\s+", " ", (it.get("title") or url or "")).strip()[:300]
        conn = _conn()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO items(source_id, site, kind, url, title, summary, text, collected_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (sid, src.get("site"), src.get("kind"), url, title,
                 txt[:500], txt[:MAX_TEXT], time.time()),
            )
            conn.execute("INSERT OR IGNORE INTO seen(url, collected_at) VALUES (?,?)", (url, time.time()))
            conn.commit()
        finally:
            conn.close()

    # ---------- 结果 ----------
    def list_items(self, source_id: str = "", keyword: str = "", limit: int = 200) -> list[dict]:
        conn = _conn()
        try:
            sql = "SELECT id, source_id, site, kind, url, title, summary, tags, collected_at, status FROM items WHERE 1=1"
            args: list = []
            if source_id:
                sql += " AND source_id=?"
                args.append(source_id)
            if keyword:
                sql += " AND (title LIKE ? OR summary LIKE ? OR url LIKE ?)"
                k = f"%{keyword}%"
                args += [k, k, k]
            sql += " ORDER BY collected_at DESC LIMIT ?"
            args.append(int(limit))
            rows = conn.execute(sql, args).fetchall()
            return [
                {"id": r[0], "source_id": r[1], "site": r[2], "kind": r[3], "url": r[4],
                 "title": r[5], "summary": r[6], "tags": r[7], "collected_at": r[8], "status": r[9]}
                for r in rows
            ]
        finally:
            conn.close()

    def item_count(self) -> dict:
        conn = _conn()
        try:
            total = conn.execute("SELECT count(*) FROM items").fetchone()[0]
            by_site = dict(conn.execute("SELECT site, count(*) FROM items GROUP BY site").fetchall())
            return {"total": total, "by_site": by_site}
        finally:
            conn.close()

    def clear_all(self) -> dict:
        conn = _conn()
        try:
            conn.execute("DELETE FROM items")
            conn.execute("DELETE FROM seen")
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    # ---------- 各来源枚举 ----------
    @staticmethod
    def _arxiv_items(src: dict) -> list[dict]:
        q = src.get("query", "")
        link = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": q, "max_results": int(src.get("max") or 5),
             "sortBy": "submittedDate", "sortOrder": "descending"}
        )
        with Client(timeout=25, verify=False, proxy=_system_proxies()) as c:
            r = c.get(link)
            r.raise_for_status()
        root = ET.fromstring(r.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        out = []
        for e in root.findall("a:entry", ns):
            out.append({
                "url": (e.findtext("a:id", "", ns) or "").strip(),
                "title": "".join((e.findtext("a:title", "", ns) or "").split()),
                "text": "".join((e.findtext("a:summary", "", ns) or "").split())[:MAX_TEXT],
            })
        return out

    @staticmethod
    def _api_items(which: str, src: dict) -> list[dict]:
        q = src.get("query", "")
        if which == "semanticscholar":
            url = ("https://api.semanticscholar.org/graph/v1/paper/search?query=" +
                   urllib.parse.quote(q) + f"&limit={int(src.get('max') or 5)}&fields=title,url,abstract")
            with Client(timeout=25, verify=False, proxy=_system_proxies(), headers={"User-Agent": UA}) as c:
                r = c.get(url)
                r.raise_for_status()
                data = r.json().get("data") or []
            return [{"url": d.get("url") or "", "title": d.get("title") or "", "text": (d.get("abstract") or "")[:MAX_TEXT]} for d in data]
        url = ("https://api.crossref.org/works?query=" + urllib.parse.quote(q) +
               f"&rows={int(src.get('max') or 5)}&select=title,URL,abstract")
        with Client(timeout=25, verify=False, proxy=_system_proxies(), headers={"User-Agent": UA}) as c:
            r = c.get(url)
            r.raise_for_status()
            items = (r.json().get("message") or {}).get("items") or []
        out = []
        for it in items:
            t = (it.get("title") or [""])[0] if isinstance(it.get("title"), list) else (it.get("title") or "")
            abstract = it.get("abstract") or ""
            out.append({"url": it.get("URL") or "", "title": t, "text": re.sub(r"<[^>]+>", " ", abstract)[:MAX_TEXT]})
        return out

    @staticmethod
    def _rss_items(url: str) -> list[dict]:
        with Client(timeout=25, verify=False, follow_redirects=True, proxy=_system_proxies(), headers={"User-Agent": UA}) as c:
            r = c.get(url)
            r.raise_for_status()
            raw = r.text
        out = []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return Radar._page_items(url)  # HTML 回退
        for e in root.iter():
            tag = (e.tag or "").split("}")[-1]
            if tag == "item":
                title = e.findtext("title", default="") or ""
                link = e.findtext("link", default="") or ""
                desc = (e.findtext("description", default="") or e.findtext("encoded", "", "http://purl.org/rss/1.0/modules/content/") or "")
                out.append({"url": link, "title": title, "text": desc[:MAX_TEXT]})
            elif tag == "entry":
                ns = {"a": "http://www.w3.org/2005/Atom"}
                title = "".join((e.findtext("a:title", "", ns) or "").split())
                le = e.find("a:link", ns)
                link = le.get("href", "") if le is not None else ""
                summ = "".join((e.findtext("a:summary", "", ns) or "").split())
                out.append({"url": link, "title": title, "text": summ[:MAX_TEXT]})
        return out

    @staticmethod
    def _sitemap_items(url: str) -> list[dict]:
        """抓站点 sitemap：优先 /sitemap.xml，其次从 robots.txt 的 Sitemap: 行解析。"""
        base = url.rstrip("/")
        def fetch_xml(u: str):
            with Client(timeout=25, verify=False, follow_redirects=True, proxy=_system_proxies(), headers={"User-Agent": UA}) as c:
                r = c.get(u)
                r.raise_for_status()
                return r.text
        urls: list[str] = []

        def parse_sitemap(text: str):
            try:
                root = ET.fromstring(text)
            except ET.ParseError:
                return
            sitemap_ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
            for loc in root.iter(f"{{{sitemap_ns}}}loc"):
                urls.append((loc.text or "").strip())

        try:
            parse_sitemap(fetch_xml(f"{base}/sitemap.xml"))
        except Exception:
            urls = []
        if not urls:
            try:
                with Client(timeout=25, verify=False, follow_redirects=True, proxy=_system_proxies(), headers={"User-Agent": UA}) as c:
                    robots = c.get(f"{base}/robots.txt")
                    if robots.status_code == 200:
                        for line in robots.text.splitlines():
                            if line.lower().startswith("sitemap:"):
                                try:
                                    parse_sitemap(fetch_xml(line.split(":", 1)[1].strip()))
                                except Exception:
                                    pass
            except Exception:
                pass
        # 过滤明显非文章（图片/静态资源），最多取前 N 条外层 url
        out = []
        for u in urls:
            if re.search(r"\.(png|jpg|jpeg|gif|css|js|xml|json|pdf|zip)$", u, re.I):
                continue
            out.append({"url": u, "title": u.rsplit("/", 1)[-1], "text": ""})
            if len(out) >= MAX_ITEMS_PER_SOURCE:
                break
        return out

    @staticmethod
    def _page_items(url: str) -> list[dict]:
        from lxml import html as lh
        with_http = url if url.startswith(("http://", "https://")) else "https://" + url
        with Client(timeout=25, verify=False, follow_redirects=True, proxy=_system_proxies(), headers={"User-Agent": UA}) as c:
            r = c.get(with_http)
            r.raise_for_status()
            raw = r.text
        doc = lh.fromstring(raw)
        seen = set()
        out = []
        for a in doc.xpath("//a[@href]"):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            abs_url = urllib.parse.urljoin(with_http, href)
            if abs_url in seen:
                continue
            title = re.sub(r"\s+", " ", "".join(a.itertext()).strip()).strip()
            if len(title) < 6:
                continue
            seen.add(abs_url)
            out.append({"url": abs_url, "title": title, "text": ""})
            if len(out) >= MAX_ITEMS_PER_SOURCE:
                break
        return out

    # ---------- 导出 ----------
    def export(self, fmt: str = "json") -> str:
        conn = _conn()
        items = conn.execute(
            "SELECT site, kind, url, title, summary, collected_at FROM items ORDER BY collected_at DESC"
        ).fetchall()
        conn.close()
        import io
        if fmt == "csv":
            import csv
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["时间", "来源", "类型", "标题", "链接", "摘要"])
            for r in items:
                w.writerow([time.ctime(r[5]), r[0], r[1], r[3], r[2], r[4]])
            return buf.getvalue()
        data = [{"site": r[0], "kind": r[1], "url": r[2], "title": r[3], "summary": r[4], "collected_at": r[5]} for r in items]
        return json.dumps(data, ensure_ascii=False, indent=2)


_radar: Radar | None = None


def get_radar() -> Radar:
    global _radar
    if _radar is None:
        _radar = Radar()
    return _radar
