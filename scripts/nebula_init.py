"""Create Nebula space + schema + tiny seed for smoke test."""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.config import NEBULA_SPACE  # noqa: E402
from backend.nebula_client import get_client  # noqa: E402
from backend.store import GraphStore  # noqa: E402


TAG_DDL = [
    "CREATE TAG IF NOT EXISTS domain(name string, description string);",
    "CREATE TAG IF NOT EXISTS subdomain(name string, description string);",
    "CREATE TAG IF NOT EXISTS technology(name string, description string, keywords string, status string);",
    "CREATE TAG IF NOT EXISTS material(name string, material_type string, title string, summary string, source_url string, published_at string);",
]

EDGE_DDL = [
    "CREATE EDGE IF NOT EXISTS belongs_to(weight double);",
    "CREATE EDGE IF NOT EXISTS supports(weight double);",
    "CREATE EDGE IF NOT EXISTS relates_to(relation_type string, weight double);",
]

INDEX_DDL = [
    "CREATE TAG INDEX IF NOT EXISTS idx_domain_name ON domain(name(64));",
    "CREATE TAG INDEX IF NOT EXISTS idx_subdomain_name ON subdomain(name(64));",
    "CREATE TAG INDEX IF NOT EXISTS idx_technology_name ON technology(name(64));",
    "CREATE TAG INDEX IF NOT EXISTS idx_material_name ON material(name(64));",
]


def main() -> None:
    client = get_client()
    print(f"[1] CREATE SPACE {NEBULA_SPACE}")
    client.execute(
        f"CREATE SPACE IF NOT EXISTS {NEBULA_SPACE}"
        f"(vid_type=FIXED_STRING(64), partition_num=10, replica_factor=1);",
        use_space=False,
    )
    time.sleep(8)

    print("[2] USE space + ADD HOSTS (storaged)")
    # Single-node compose uses storaged0:9779
    try:
        client.execute('ADD HOSTS "storaged0":9779;', use_space=False)
    except Exception as exc:
        print(f"  ADD HOSTS skipped/info: {exc}")

    client.execute(f"USE {NEBULA_SPACE};", use_space=False)

    print("[3] Tags")
    for ddl in TAG_DDL:
        client.execute(ddl)

    print("[4] Edges")
    for ddl in EDGE_DDL:
        client.execute(ddl)

    print("[5] Indexes")
    for ddl in INDEX_DDL:
        try:
            client.execute(ddl)
        except Exception as exc:
            print(f"  index info: {exc}")
    time.sleep(5)
    try:
        client.execute("REBUILD TAG INDEX;")
    except Exception:
        pass

    print("[6] Tiny seed (smoke)")
    store = GraphStore(client)
    store.insert_vertex("domain", "dom_demo", {"name": "示例领域", "description": "smoke"})
    store.insert_vertex("subdomain", "sub_demo", {"name": "示例子域", "description": "smoke"})
    store.insert_vertex(
        "technology",
        "tech_demo",
        {
            "name": "示例技术点",
            "description": "用于连通性验证",
            "keywords": "demo",
            "status": "draft",
        },
    )
    store.insert_vertex(
        "material",
        "mat_demo",
        {
            "name": "示例材料",
            "material_type": "doc",
            "title": "Smoke Test Material",
            "summary": "可删除",
            "source_url": "",
            "published_at": "2026-08-07",
        },
    )
    store.insert_edge("belongs_to", "sub_demo", "dom_demo", {"weight": 1.0})
    store.insert_edge("belongs_to", "tech_demo", "sub_demo", {"weight": 1.0})
    store.insert_edge("supports", "mat_demo", "tech_demo", {"weight": 1.0})

    print("[7] Stats:", store.stats())
    print("Done.")


if __name__ == "__main__":
    main()
