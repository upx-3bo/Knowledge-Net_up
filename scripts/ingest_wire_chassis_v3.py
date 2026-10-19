#!/usr/bin/env python3
"""Ingest research/c2_wire_chassis_ingest_v3.json into Nebula."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.store import GraphStore, make_vid  # noqa: E402

DATA = ROOT / "research" / "c2_wire_chassis_ingest_v3.json"


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
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    store = GraphStore()
    before = store.stats()
    print("before:", before)
    if any(before.values()):
        print("ERROR: graph not empty; abort to avoid mixed taxonomy")
        return 1

    name_to_tech: dict[str, dict] = {}
    child_names = {e["child"] for e in payload.get("hierarchy_edges", [])}

    # Special: 驱制一体 hangs under 线控驱动 + 线控制动 (not domain)
    multi_parent_subs = payload.get("subdomain_parents", {})

    for t in payload["technologies"]:
        domain = ensure_named(store, "domain", t["domain_name"])
        subdomain = ensure_named(store, "subdomain", t["subdomain_name"])

        parents = multi_parent_subs.get(t["subdomain_name"])
        if parents:
            for pname in parents:
                pnode = ensure_named(store, "subdomain", pname)
                # ensure parent subdomain under domain first
                store.insert_edge("belongs_to", pnode["vid"], domain["vid"], {"weight": 1.0})
                store.insert_edge("belongs_to", subdomain["vid"], pnode["vid"], {"weight": 1.0})
        else:
            store.insert_edge("belongs_to", subdomain["vid"], domain["vid"], {"weight": 1.0})

        existing = find_by_name(store, t["name"], tag="technology")
        if existing:
            tech = existing
        else:
            tech = store.insert_vertex(
                "technology",
                make_vid("tech"),
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "keywords": t.get("keywords", ""),
                    "status": t.get("status") or "active",
                },
            )
        # Leaf with tech parent: only attach to parent later (direct edge only)
        if t["name"] not in child_names:
            store.insert_edge("belongs_to", tech["vid"], subdomain["vid"], {"weight": 1.0})
            print(f"+ tech {t['name']} -> {subdomain['props']['name']}")
        else:
            print(f"+ tech {t['name']} (defer parent; skip subdomain edge)")
        name_to_tech[t["name"]] = tech

    for e in payload["hierarchy_edges"]:
        child = name_to_tech[e["child"]]
        parent = name_to_tech[e["parent"]]
        store.insert_edge(
            "belongs_to",
            child["vid"],
            parent["vid"],
            {"weight": float(e.get("weight", 1.0))},
        )
        print(f"+ belongs_to {e['child']} -> {e['parent']}")

    mats: dict[str, dict] = {}
    for m in payload["materials"]:
        mats[m["name"]] = ensure_named(
            store,
            "material",
            m["name"],
            {
                "material_type": m.get("material_type", "doc"),
                "title": m.get("title") or m["name"],
                "summary": m.get("summary", ""),
                "source_url": m.get("source_url", ""),
                "published_at": m.get("published_at", ""),
            },
        )
        print(f"+ material {m['name']}")

    for link in payload["material_supports"]:
        mat = mats[link["material"]]
        tech = name_to_tech[link["tech"]]
        store.insert_edge("supports", mat["vid"], tech["vid"], {"weight": 1.0})
        print(f"+ supports {link['material']} -> {link['tech']}")

    for r in payload["relations"]:
        src = name_to_tech[r["src_name"]]
        dst = name_to_tech[r["dst_name"]]
        props = {"weight": float(r.get("weight", 0.8))}
        if r.get("edge_type", "relates_to") == "relates_to":
            props["relation_type"] = r.get("relation_type", "related")
        store.insert_edge(r.get("edge_type", "relates_to"), src["vid"], dst["vid"], props)
        print(f"+ {r.get('edge_type', 'relates_to')} {r['src_name']} -> {r['dst_name']}")

    after = store.stats()
    print("after:", after)
    print("done. claims intentionally not ingested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
