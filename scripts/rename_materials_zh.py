#!/usr/bin/env python3
"""Rename material.name to short Chinese labels derived from content."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.store import GraphStore  # noqa: E402

# old name -> meaningful short Chinese name
RENAMES = {
    "GB21670-2025": "国标·乘用车制动系统GB21670",
    "GB21670-2025-平台页": "国标平台·GB21670起草信息",
    "GB17675-2025": "国标·汽车转向系GB17675",
    "EU2024-1257-Euro7": "欧7法规·制动颗粒物限值",
    "US12071019B2": "舍弗勒专利·电驱桥集成制动",
    "US12590612B2": "舍弗勒专利·湿式多片制动作动",
    "Schaeffler-Integrated-Wet-Brake": "舍弗勒·集成湿式制动产品",
    "Miba-Zero-Emission-MDB": "Miba·零排放多片制动",
    "Schaeffler-E-Wheel-Drive-OnePager": "舍弗勒·轮毂电驱动方案",
    "Bosch-Brake-by-Wire": "博世·线控制动方案",
    "IEEE-TIE-2023-SESO-EMB": "论文·EMB夹紧力SESO估计",
    "MDPI-Electronics-2025-EMB-Fusion": "论文·EMB摩擦扭矩融合估计",
    "MDPI-Energies-2025-RBS-Review": "综述·再生制动控制策略",
    "MDPI-Energies-2025-IWM-Review": "综述·轮毂电机与热管理",
    "MDPI-Sustainability-2023-EMB-Review": "综述·EMB结构控制应用",
    "People-CN-GB17675-2025": "资讯·GB17675线控转向发布",
}


def find_by_name(store: GraphStore, name: str, tag: str = "material"):
    for item in store.list_vertices(tag=tag, keyword=name, limit=50):
        if item.get("props", {}).get("name") == name:
            return item
    return None


def main() -> int:
    store = GraphStore()
    for old, new in RENAMES.items():
        node = find_by_name(store, old)
        if not node:
            # already renamed?
            if find_by_name(store, new):
                print(f"= skip (already) {new}")
                continue
            print(f"! missing {old}")
            continue
        store.update_vertex(node["vid"], {"name": new})
        print(f"* {old} -> {new}")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
