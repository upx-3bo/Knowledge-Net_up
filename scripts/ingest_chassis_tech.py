#!/usr/bin/env python3
"""导入「底盘技术」新领域：域 -> 11板块(subdomain) -> 主题(technology) -> 技术点(technology) -> 材料(material)。

- 独立新网络：材料节点全部新建（不复用旧领域同名节点）。
- 确定性 vid（前缀+md5）保证幂等：重跑时先删除本脚本会创建的所有节点，再重建。
- 层级边：subdomain->domain、theme->subdomain、tech->theme 用 belongs_to；材料->技术点/主题 用 supports。
- 缺主题/技术点时降级挂上级。
- 排除板块 待定/其他/待定/【跳过·商用车/混动】/空。
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.store import GraphStore  # noqa: E402

DATA = Path(r"C:\Users\x30085681\Desktop\up_X\知识库-refs\_脚本\chassis_labels_exported.json")

DBOARD = "domain_chassis_tech"
SKIP = {"其他/待定", "待定", "【跳过·商用车/混动】"}


def h(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:10]


def sub_vid(name: str) -> str:
    return f"sub_{h(name)}_{hashlib.md5(DBOARD.encode()).hexdigest()[:6]}"


def theme_vid(board: str, theme: str) -> str:
    return f"tech_{h(board + '|' + theme)}_{hashlib.md5(sub_vid(board).encode()).hexdigest()[:6]}"


def tech_vid(board: str, theme: str, tp: str) -> str:
    parent = theme_vid(board, theme) if theme else sub_vid(board)
    return f"tec_{h(board + '|' + theme + '|' + tp)}_{hashlib.md5(parent.encode()).hexdigest()[:6]}"


def mat_vid(fname: str) -> str:
    return f"mat_{h(fname)}"


def main() -> int:
    rows = [
        r for r in json.loads(DATA.read_text(encoding="utf-8"))
        if r.get("board") and r["board"] not in SKIP
    ]
    print("入库记录数:", len(rows))

    # ---- 收集本次会创建的全部 vid ----
    vids = {DBOARD}
    for r in rows:
        b, th = r["board"], (r.get("theme") or "").strip()
        vids.add(sub_vid(b))
        if th:
            vids.add(theme_vid(b, th))
        for tp in [t.strip() for t in (r.get("tech") or "").replace("，", "、").replace(",", "、").split("、") if t.strip()]:
            vids.add(tech_vid(b, th, tp))
        vids.add(mat_vid(r["file"]))

    # ---- 幂等清理：删除上次运行创建的节点 ----
    store = GraphStore()
    for v in sorted(vids):
        if store.delete_vertex(v):
            pass

    # 清理旧版本残留的孤立 tech 节点（无 belongs_to 边且描述为 主题/技术点 前缀）
    for n in store.list_vertices("technology", limit=500):
        desc = (n.get("props") or {}).get("description") or ""
        if (desc.startswith("主题（") or desc.startswith("技术点（")) and not store.children(n["vid"]):
            mat_children = [m for m in store.neighbors(n["vid"], depth=1).get("nodes", []) if m.get("tag") == "material"]
            if not mat_children:
                store.delete_vertex(n["vid"])


    # ---- 1. 域 ----
    store.insert_vertex("domain", DBOARD, {"name": "底盘技术", "description": "底盘技术 11 大板块网络（板块-主题-技术点-材料）"})

    # ---- 2. 板块(subdomain) ----
    for r in rows:
        b = r["board"]
        n = store.insert_vertex("subdomain", sub_vid(b), {"name": b, "description": f"板块：{b}"})
        store.insert_edge("belongs_to", n["vid"], DBOARD, {"weight": 1.0})
        print("+ subdomain", b)

    # ---- 3. 主题 + 技术点 (technology) ----
    for r in rows:
        b, th = r["board"], (r.get("theme") or "").strip()
        if th:
            tv = theme_vid(b, th)
            if not store.get_vertex(tv):
                store.insert_vertex("technology", tv, {"name": th, "description": f"主题（{b}）", "status": "active"})
                store.insert_edge("belongs_to", tv, sub_vid(b), {"weight": 1.0})
                print("+ theme", th, "->", b)
            for tp in [t.strip() for t in (r.get("tech") or "").replace("，", "、").replace(",", "、").split("、") if t.strip()]:
                tc = tech_vid(b, th, tp)
                if not store.get_vertex(tc):
                    store.insert_vertex("technology", tc, {"name": tp, "description": f"技术点（{b}/{th}）", "status": "active"})
                    store.insert_edge("belongs_to", tc, tv, {"weight": 1.0})
                    print("+ tech", tp, "->", th)

    # ---- 4. 材料 (material) ----
    for r in rows:
        fname = r["file"]
        base = Path(fname).stem.strip()
        mv = mat_vid(fname)
        store.insert_vertex("material", mv, {
            "name": base, "material_type": "doc", "title": fname,
            "summary": (r.get("note") or ""),
            "source_url": (r.get("site") or ""),
            "published_at": (r.get("phone") or ""),
        })
        print("+ material", fname[:40])

    # ---- 5. 建边 材料 -> 技术点/主题/板块 ----
    for r in rows:
        b, th, tpl = r["board"], (r.get("theme") or "").strip(), (r.get("tech") or "").strip()
        mv = mat_vid(r["file"])
        tech_list = [t.strip() for t in tpl.replace("，", "、").replace(",", "、").split("、") if t.strip()]
        if tech_list:
            for tp in tech_list:
                store.insert_edge("supports", mv, tech_vid(b, th, tp), {"weight": 1.0})
                print("  supports", r["file"][:30], "->", tp)
        elif th:
            store.insert_edge("supports", mv, theme_vid(b, th), {"weight": 1.0})
            print("  supports(dir->theme)", r["file"][:30], "->", th)
        else:
            store.insert_edge("supports", mv, sub_vid(b), {"weight": 1.0})
            print("  supports(dir->board)", r["file"][:30], "->", b)

    print("\nafter:", store.stats())
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
