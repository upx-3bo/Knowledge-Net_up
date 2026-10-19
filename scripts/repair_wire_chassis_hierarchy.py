#!/usr/bin/env python3
"""Repair wire-chassis DAG: direct parents only + suspension branch."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.store import GraphStore, make_vid  # noqa: E402

# leaf tech -> keep only this tech parent (drop subdomain belongs_to)
LEAF_PARENTS = {
    "轮毂电机热管理": "轮毂电机驱动",
    "EMB夹紧力估计": "电子机械制动EMB",
    "EMB安全冗余": "电子机械制动EMB",
    "EMB与IWM集成": "轮端驱制集成",
    "湿式多片制动器": "桥端驱制集成",
    "电驱桥制动集成": "桥端驱制集成",
    "再生摩擦制动协调": "驱制协同控制",
}


def find_by_name(store: GraphStore, name: str, tag: str | None = None):
    for item in store.list_vertices(tag=tag, keyword=name, limit=50):
        if item.get("props", {}).get("name") == name:
            return item
    return None


def ensure_named(store: GraphStore, tag: str, name: str, extra: dict | None = None):
    found = find_by_name(store, name, tag=tag)
    if found:
        return found
    prefix = {"domain": "dom", "subdomain": "sub", "technology": "tech", "material": "mat"}[tag]
    props = {"name": name}
    if extra:
        props.update(extra)
    return store.insert_vertex(tag, make_vid(prefix), props)


def main() -> int:
    store = GraphStore()

    # 1) Drop redundant leaf -> subdomain belongs_to (keep leaf -> parent tech)
    for leaf_name, parent_name in LEAF_PARENTS.items():
        leaf = find_by_name(store, leaf_name, tag="technology")
        parent = find_by_name(store, parent_name, tag="technology")
        if not leaf or not parent:
            print(f"! missing {leaf_name} or {parent_name}")
            continue
        # ensure parent edge
        store.insert_edge("belongs_to", leaf["vid"], parent["vid"], {"weight": 1.0})
        # find subdomain edges via 1-hop and delete leaf->subdomain
        nb = store.neighbors(leaf["vid"], depth=1)
        for e in nb["edges"]:
            if e["edge_type"] != "belongs_to":
                continue
            if e["src_vid"] != leaf["vid"]:
                continue
            dst = store.get_vertex(e["dst_vid"])
            if not dst:
                continue
            if dst["tag"] == "subdomain":
                store.delete_edge("belongs_to", leaf["vid"], dst["vid"])
                print(f"- belongs_to {leaf_name} -> {dst['props'].get('name')} (subdomain)")
            elif dst["tag"] == "technology" and dst["vid"] != parent["vid"]:
                # unexpected extra tech parent
                store.delete_edge("belongs_to", leaf["vid"], dst["vid"])
                print(f"- belongs_to {leaf_name} -> {dst['props'].get('name')} (extra tech)")
        print(f"= {leaf_name} belongs_to {parent_name}")

    # 2) 驱制一体: belong to 线控驱动 + 线控制动, not domain
    integ = find_by_name(store, "驱制一体", tag="subdomain")
    drive = find_by_name(store, "线控驱动", tag="subdomain")
    brake = find_by_name(store, "线控制动", tag="subdomain")
    domain = find_by_name(store, "线控底盘", tag="domain")
    if not all([integ, drive, brake, domain]):
        print("! missing 驱制一体 / 线控驱动 / 线控制动 / 线控底盘")
        return 1

    store.delete_edge("belongs_to", integ["vid"], domain["vid"])
    print("- belongs_to 驱制一体 -> 线控底盘")
    store.insert_edge("belongs_to", integ["vid"], drive["vid"], {"weight": 1.0})
    store.insert_edge("belongs_to", integ["vid"], brake["vid"], {"weight": 1.0})
    print("+ belongs_to 驱制一体 -> 线控驱动")
    print("+ belongs_to 驱制一体 -> 线控制动")

    # Also drop mid-level children that incorrectly only needed subdomain —
    # already handled leaves. Mid nodes 轮端/桥端/协同 keep subdomain.

    # 3) Add 线控悬架 + 主动悬架
    sus_sub = ensure_named(store, "subdomain", "线控悬架", {"description": "线控/电控悬架执行子系统"})
    store.insert_edge("belongs_to", sus_sub["vid"], domain["vid"], {"weight": 1.0})
    active = ensure_named(
        store,
        "technology",
        "主动悬架",
        {
            "description": "通过电控连续调节阻尼/刚度/高度以改善操控与舒适性的悬架执行技术",
            "keywords": "主动悬架,CDC,空气悬架,线控悬架",
            "status": "active",
        },
    )
    store.insert_edge("belongs_to", active["vid"], sus_sub["vid"], {"weight": 1.0})
    print("+ subdomain 线控悬架 -> 线控底盘")
    print("+ tech 主动悬架 -> 线控悬架")

    print("stats:", store.stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
