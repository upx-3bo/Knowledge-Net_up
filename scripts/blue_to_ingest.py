#!/usr/bin/env python3
"""蓝区简报 → 绿区候选入库 转换器（file sync bridge）。

读蓝区同步文件夹里的 tech_points.json（如 D:\\download\\底盘新技术检索_@_\\2026-09-23\\tech_points.json），
按「原文链接 + 目标子域」分组，转换为入库抽取 payload，写入本地 data/collector.db 的 candidates(pending)，
供工作台「自动采集」面板人工核对后一键入库（/collect/candidates/{id}/commit）。

- 防重：candidates.url 唯一索引自动去重；同一文章多子域用 `#sub=` 片段区分；seen 表记录干净 URL。
- 复用优先：子域/TECH 名称优先映射到图谱已存在的位置，避免重复建节点。
- 只写候选队列、不直接写图：供应商/客户/成熟度等仍需人工复核。

用法：
  python scripts/blue_to_ingest.py [PATH_TO_FOLDER_OR_JSON] [--dry-run]
  不带参数时自动扫描 D:\\download\\底盘新技术检索_@_ 下最新日期目录。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "collector.db"

DOMAIN = "底盘技术"

# 「目标主题」（蓝区简报 meta.topic / 每条 目标主题）-> 子域（绿区架构映射）
TOPIC_TO_SUBDOMAIN = {
    "制动": "制动技术",
    "制动与驱动制动集成": "制动技术",
    "制动与驱动制动集成（wet brake）": "制动技术",
    "湿式制动": "制动技术",
    "wet brake": "制动技术",
    "悬架": "悬架技术",
    "空气悬架": "悬架技术",
    "转向": "转向技术",
    "线控转向": "转向技术",
    "线性转向": "转向技术",
}

# 一级领域 -> 子域（旧格式兼容；复用图谱已有子域）
AREA_TO_SUBDOMAIN = {
    "悬架": "悬架技术",
    "制动": "制动技术",
    "转向": "转向技术",
}

# 技术子类 -> 优先映射到的已有子域（旧格式兼容；图谱上该技术已存在的位置）
TECH_SUB_OVERRIDE = {
    "电子机械制动EMB": "线控制动",
    "电子机械制动": "线控制动",
    "EMB": "线控制动",
    "线控制动": "制动技术",
    "线控转向": "转向技术",
    "主动悬架": "悬架技术",
    "空气悬架": "悬架技术",
}

MAX_TECH_DESC = 200
MAX_MAT_TITLE = 24
SITE = "盖世汽车"
KIND = "情报"


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
            payload TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
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


def _short(s: str, n: int) -> str:
    s = (s or "").strip()
    return s[:n] + "…" if len(s) > n else s


def _f(item: dict, *keys: str) -> str:
    """按顺序取第一个非空字段（兼容新旧格式的字段命名）。"""
    for k in keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _resolve_subdomain(item: dict) -> str:
    """子域解析（绿区架构映射），优先级：
    1) 技术点/子主题 名称命中复用映射（如 EMB→线控制动，避免重复建点）
    2) 目标主题 / 一级领域 命中主题映射（如 wet brake→制动技术）
    3) 目标主题原样作为子域（绿区后续可并入）
    """
    for name in _tech_names(item):
        if name in TECH_SUB_OVERRIDE:
            return TECH_SUB_OVERRIDE[name]
    topic = _f(item, "目标主题", "一级领域")
    if topic in TOPIC_TO_SUBDOMAIN:
        return TOPIC_TO_SUBDOMAIN[topic]
    if topic:
        return topic
    return "未分类"


def _tech_names(item: dict) -> list[str]:
    """技术点/子主题 列表（新格式可多值）；旧格式回退 技术子类/技术名称；空则业务主题兜底。"""
    raw = _f(item, "技术点/子主题", "技术子类", "技术名称")
    names = [n for n in raw.replace("，", "、").replace(",", "、").split("、") if n.strip()]
    if not names:
        topic = _f(item, "目标主题", "一级领域")
        if topic:
            names = [topic]
    return names


def _published_date(ts: str) -> str:
    return (ts or "").strip()[:10]


def _notes_for(item: dict) -> str:
    bits = []
    code = _f(item, "编号", "技术点编号")
    if code:
        bits.append(f"蓝区简报{code}")
    adv = _f(item, "备注", "入库建议")
    if adv and adv != "未说明":
        bits.append(f"备注:{adv}")
    sup = _f(item, "涉及厂商", "供应商")
    if sup and sup != "未识别":
        bits.append(f"供应商:{sup}")
    cust = _f(item, "客户", "配套客户")
    if cust and cust != "未识别":
        bits.append(f"客户:{cust}")
    veh = _f(item, "车型", "配套车型")
    if veh and veh != "未识别":
        bits.append(f"车型:{veh}")
    return "；".join(bits)


def build_payloads(items: list[dict]) -> list[dict]:
    """items 为同一简报文件里的全部技术点。返回候选 payload 列表（按 原文链接+子域 分组）。"""
    by_article: dict[str, list[dict]] = {}
    for it in items:
        url = _f(it, "链接", "原文链接")
        if not url or not _tech_names(it):
            continue
        by_article.setdefault(url, []).append(it)

    out: list[dict] = []
    for url, its in by_article.items():
        by_sub: dict[str, list[dict]] = {}
        for it in its:
            by_sub.setdefault(_resolve_subdomain(it), []).append(it)
        for subdomain, sub_items in by_sub.items():
            techs: dict[str, dict] = {}
            notes_seen: set[str] = set()
            notes: list[str] = []
            for it in sub_items:
                for name in _tech_names(it):
                    if name in techs:
                        continue
                    desc = _f(it, "摘要要点", "技术要点")
                    kw = _f(it, "命中检索词", "命中关键词").replace("、", "，")
                    techs[name] = {
                        "name": name,
                        "description": _short(desc, MAX_TECH_DESC),
                        "keywords": kw,
                    }
                n = _notes_for(it)
                if n and n not in notes_seen:
                    notes_seen.add(n)
                    notes.append(n)
            first = sub_items[0]
            title = _f(first, "资讯标题", "原文标题")
            detail_vals = [v for v in (_f(it, "摘要要点", "技术要点") for it in sub_items) if v]
            summary = "\n".join(dict.fromkeys(_short(v, MAX_TECH_DESC) for v in detail_vals))
            mat_name = _short(title, MAX_MAT_TITLE) or _short(url, MAX_MAT_TITLE)
            unified = {
                "domain": DOMAIN,
                "subdomain": subdomain,
                "tech_points": list(techs.values()),
                "materials": [
                    {
                        "name": mat_name,
                        "type": "news",
                        "title": title,
                        "summary": _short(summary, MAX_TECH_DESC) if summary else "",
                        "source_url": url,
                        "published_at": _published_date(_f(first, "原文日期", "发布时间")),
                    }
                ],
                "tech_material_links": [{"tech": t["name"], "material": mat_name} for t in techs.values()],
                "notes": "；".join(notes),
            }
            out.append({"site": _f(first, "来源", "信息来源") or SITE, "title": title, "url": url, "subdomain": subdomain, "payload": unified})
    return out


def write_candidates(payloads: list[dict], dry_run: bool = False) -> dict:
    conn = _connect()
    now = time.time()
    added, skipped, errors = 0, 0, 0
    try:
        for p in payloads:
            clean_url = p["url"]
            full_url = f"{clean_url}#sub={urllib.parse.quote(p['subdomain'])}"
            if dry_run:
                added += 1
                continue
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO candidates(kind, site, url, title, payload, status, note, created_at, updated_at) "
                    "VALUES (?,?,?,?,?, 'pending', 'blue_brief', ?,?)",
                    (KIND, p["site"], full_url, p["title"],
                     json.dumps(p["payload"], ensure_ascii=False), now, now),
                )
                changed = conn.total_changes
                conn.commit()
                if changed:
                    added += 1
                else:
                    skipped += 1
                conn.execute(
                    "INSERT OR IGNORE INTO seen(url, kind, site, added_at) VALUES (?,?,?,?)",
                    (clean_url, KIND, p["site"], now),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                skipped += 1
            except Exception:  # noqa: BLE001
                errors += 1
    finally:
        conn.close()
    return {"added": added, "skipped": skipped, "errors": errors}


def find_briefing(path: str | None) -> Path | None:
    if path:
        p = Path(path)
        if p.is_file():
            return p
        if p.is_dir():
            cand = p / "tech_points.json"
            return cand if cand.exists() else None
        return None
    root = Path(r"D:\download\底盘新技术检索_@_")
    if root.is_dir():
        days = sorted([d for d in root.iterdir() if d.is_dir()], reverse=True)
        for d in days:
            cand = d / "tech_points.json"
            if cand.exists():
                return cand
    return None


def preview_summary(payloads: list[dict]) -> None:
    title_len = shutil.get_terminal_size((120, 40)).columns
    print(f"\n生成候选 {len(payloads)} 条（均待人工核对）\n" + "-" * title_len)
    for i, p in enumerate(payloads, 1):
        pl = p["payload"]
        techs = "、".join(t["name"] for t in pl["tech_points"])
        mats = "、".join(m["name"] for m in pl["materials"])
        print(f"[{i:02d}] {pl['subdomain']} | {_short(p['title'], 36)}")
        print(f"       域: {pl['domain']}  技术点: {techs}")
        print(f"       材料: {_short(mats, 40)}")
        if pl.get("notes"):
            print(f"       备注: {pl['notes']}")
    print("-" * title_len)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="蓝区技术简报 -> 绿区候选入库")
    ap.add_argument("path", nargs="?", default=None, help="简报文件夹或 tech_points.json 路径")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写库")
    args = ap.parse_args(argv)

    bf = find_briefing(args.path)
    if not bf:
        print("未找到 tech_points.json（自动扫描 D:\\download\\底盘新技术检索_@_ 或指定路径）")
        return 2
    try:
        data = json.loads(bf.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"读取 {bf} 失败: {exc}")
        return 2

    meta = data.get("meta") or {}
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]
    print(f"简报: {bf}")
    print(f"  窗口 {meta.get('since','')} → {meta.get('retrieved_at','')} | "
          f"扫描 {meta.get('scanned','?')} 条 | 技术点 {len(items)} 条 | 来源 {meta.get('sources','')}")

    payloads = build_payloads(items)
    preview_summary(payloads)

    res = write_candidates(payloads, dry_run=args.dry_run)
    mode = "DRY-RUN（未写库）" if args.dry_run else "写入"
    print(f"[{mode}] 新增候选 {res['added']} · 重复已跳过 {res['skipped']} · 失败 {res['errors']}")
    if not args.dry_run:
        print(f"候选库: {DB_PATH}  →  打开工作台「自动采集」面板核对后逐条入库")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
