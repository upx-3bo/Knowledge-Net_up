#!/usr/bin/env python3
"""清理「已删领域」下挂着的孤儿子树（子域/技术点/文档）。

原理：从当前仍存在的 domain 出发，沿 belongs_to/supports 的「子→父」边反向 BFS，
不可达的非领域节点即为孤儿（属于已被删除的领域子树），按 材料→技术点→子域 顺序删除。

- 仅通过本地 HTTP API 操作（无需 nebula 客户端）。
- 每次删除都走服务端 history（可「撤回」）；同时先把孤儿明细备份到 snapshots 便于恢复。
- 默认 dry-run 只统计；加 --yes 才真正删除。

用法：
  python scripts/clean_orphans.py            # 干跑：统计会删哪些
  python scripts/clean_orphans.py --yes      # 备份 + 真正删除
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"
SNAP_DIR = ROOT / "scripts" / "snapshots"
DELETE_ORDER = ["material", "technology", "subdomain"]


def _pw() -> str:
    envf = ROOT / ".env"
    for line in envf.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("WRITE_PASSWORD="):
            return line.split("=", 1)[1].strip()
    return ""


def api(method: str, path: str, token: str = "", body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{API}{path}", method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    else:
        data = None
    with urllib.request.urlopen(req, data=data, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="真正执行删除（否则仅统计）")
    ap.add_argument("--limit-nodes", type=int, default=1000)
    ap.add_argument("--limit-edges", type=int, default=3000)
    args = ap.parse_args(argv)

    pw = _pw()
    if not pw:
        print("未在 .env 中找到 WRITE_PASSWORD")
        return 2
    tok = api("POST", "/ai/login", body={"password": pw}).get("token", "") if args.yes else ""
    if args.yes and not tok:
        print("登录失败：写入口令错误")
        return 2

    ov = api("GET", f"/overview?limit_nodes={args.limit_nodes}&limit_edges={args.limit_edges}")
    nodes, edges = ov.get("nodes", []), ov.get("edges", [])
    by_id = {n["vid"]: n for n in nodes}
    print(f"当前图：{len(nodes)} 节点 / {len(edges)} 边")
    print("领域(alive)：", [n.get("props", {}).get("name") for n in nodes if n.get("tag") == "domain"])

    # 子->父 边：belongs_to 子域/技术点→上层；supports 文档→技术点
    children: dict[str, list[str]] = collections.defaultdict(list)
    parents: dict[str, list[str]] = collections.defaultdict(list)
    for e in edges:
        t = e.get("edge_type")
        if t in ("belongs_to", "supports"):
            children.setdefault(e["dst_vid"], []).append(e["src_vid"])
            parents.setdefault(e["src_vid"], []).append(e["dst_vid"])

    # 从存活领域 BFS 标记可达（保留）
    keep = set()
    queue = collections.deque(n["vid"] for n in nodes if n.get("tag") == "domain")
    while queue:
        v = queue.popleft()
        if v in keep:
            continue
        keep.add(v)
        for c in children.get(v, []):
            queue.append(c)

    orphans = [n for n in nodes if n.get("tag") != "domain" and n["vid"] not in keep]
    by_tag = collections.Counter(n.get("tag") for n in orphans)
    print(f"\n孤儿（将删除）: {len(orphans)}，按类型: {dict(by_tag)}")

    # 统计各自挂在哪个已删的顶层（缺失的祖先）
    root_of: dict[str, str] = {}
    for n in orphans:
        cur = n["vid"]
        seen = set()
        while cur in by_id and cur not in seen and by_id[cur].get("tag") != "domain":
            seen.add(cur)
            ps = parents.get(cur, [])
            nxt = next((x for x in ps if by_id[x].get("tag") == "subdomain"), ps[0] if ps else None)
            if nxt is None:
                break
            cur = nxt
        root_of[n["vid"]] = cur if cur not in by_id else "in-graph"

    missing_counts = collections.Counter(root_of.values())
    print("按缺失顶层统计：")
    for root, c in missing_counts.most_common():
        print(f"   {root}（图谱中已不存在）: {c}")
    missing_counts.pop("in-graph", None)

    # 明细备份 + 示例
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = SNAP_DIR / f"orphans_{datetime.now():%Y%m%d_%H%M%S}.json"
    detail = []
    for n in orphans:
        try:
            full = api("GET", f"/vertices/{n['vid']}") if args.yes else {"vid": n["vid"], "tag": n["tag"], "props": n.get("props", {})}
        except Exception:
            full = {"vid": n["vid"], "tag": n["tag"], "props": n.get("props", {})}
        detail.append({"tag": full.get("tag") or n.get("tag"), "vid": n["vid"],
                       "props": full.get("props", n.get("props", {})),
                       "parents_in_graph": parents.get(n["vid"], []),
                       "top_missing": root_of.get(n["vid"])})
    snap_path.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"孤儿明细已备份: {snap_path}（{len(detail)} 条）")

    print("\n示例（前 25 条）：")
    for n in detail[:25]:
        name = (n["props"] or {}).get("name") or n["props"].get("title") or n["vid"]
        print(f"  [{n['tag']}] {name}  <-- 缺失顶层 {root_of.get(n['vid'])}")

    if not args.yes:
        print("\n[dry-run] 未删除任何数据。确认后用：python scripts/clean_orphans.py --yes")
        return 0

    # 真正删除：材料→技术点→子域
    order = {t: i for i, t in enumerate(DELETE_ORDER)}
    orphan_sorted = sorted(orphans, key=lambda n: (order.get(n["tag"], 9), n["vid"]))
    ok, miss = 0, 0
    for n in orphan_sorted:
        try:
            api("DELETE", f"/vertices/{n['vid']}", token=tok)
            ok += 1
        except urllib.error.HTTPError as e:
            if e.code == 404:
                miss += 1  # 已被删（可能为之前已删）
            else:
                print(f"  !! 删除失败 {n['vid']}: HTTP {e.code}")
    print(f"\n删除完成：成功 {ok}，已不存在(跳过) {miss}")

    ov2 = api("GET", "/overview?limit_nodes=1000&limit_edges=3000")
    print(f"删除后：{len(ov2.get('nodes', []))} 节点 / {len(ov2.get('edges', []))} 边")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
