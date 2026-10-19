#!/usr/bin/env python3
"""Register storage host, create space/schema/seed via nebula3-python (WSL)."""
from __future__ import annotations

import sys
import time

from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool

HOST, PORT = "127.0.0.1", 9669
USER, PWD = "root", ""
SPACE = "auto_innovation_kg"


def run(session, nql: str, fatal: bool = True):
    resp = session.execute(nql)
    ok = resp.is_succeeded()
    print(("OK  " if ok else "FAIL"), nql[:120].replace("\n", " "))
    if not ok:
        print("   ", resp.error_msg())
        if fatal:
            raise SystemExit(1)
    return resp


def main() -> None:
    cfg = Config()
    cfg.max_connection_pool_size = 4
    pool = ConnectionPool()
    assert pool.init([(HOST, PORT)], cfg), "connect failed"
    session = pool.get_session(USER, PWD)
    try:
        run(session, 'ADD HOSTS "127.0.0.1":9779;', fatal=False)
        time.sleep(8)
        run(session, "SHOW HOSTS;")

        run(
            session,
            f"CREATE SPACE IF NOT EXISTS {SPACE}"
            f"(vid_type=FIXED_STRING(64), partition_num=10, replica_factor=1);",
        )
        time.sleep(10)
        run(session, f"USE {SPACE};")

        tags = [
            "CREATE TAG IF NOT EXISTS domain(name string, description string);",
            "CREATE TAG IF NOT EXISTS subdomain(name string, description string);",
            "CREATE TAG IF NOT EXISTS technology(name string, description string, keywords string, status string);",
            "CREATE TAG IF NOT EXISTS material(name string, material_type string, title string, summary string, source_url string, published_at string);",
        ]
        edges = [
            "CREATE EDGE IF NOT EXISTS belongs_to(weight double);",
            "CREATE EDGE IF NOT EXISTS supports(weight double);",
            "CREATE EDGE IF NOT EXISTS relates_to(relation_type string, weight double);",
        ]
        for nql in tags + edges:
            run(session, nql)

        indexes = [
            "CREATE TAG INDEX IF NOT EXISTS idx_domain_name ON domain(name(64));",
            "CREATE TAG INDEX IF NOT EXISTS idx_subdomain_name ON subdomain(name(64));",
            "CREATE TAG INDEX IF NOT EXISTS idx_technology_name ON technology(name(64));",
            "CREATE TAG INDEX IF NOT EXISTS idx_material_name ON material(name(64));",
        ]
        for nql in indexes:
            run(session, nql, fatal=False)
        time.sleep(5)
        run(session, "REBUILD TAG INDEX;", fatal=False)

        # smoke seed
        run(session, "INSERT VERTEX IF NOT EXISTS domain(name, description) VALUES 'dom_demo': ('示例领域', 'smoke');")
        run(session, "INSERT VERTEX IF NOT EXISTS subdomain(name, description) VALUES 'sub_demo': ('示例子域', 'smoke');")
        run(
            session,
            "INSERT VERTEX IF NOT EXISTS technology(name, description, keywords, status) "
            "VALUES 'tech_demo': ('示例技术点', '连通性验证', 'demo', 'draft');",
        )
        run(
            session,
            "INSERT VERTEX IF NOT EXISTS material(name, material_type, title, summary, source_url, published_at) "
            "VALUES 'mat_demo': ('示例材料', 'doc', 'Smoke Test', '可删除', '', '2026-08-07');",
        )
        run(session, "INSERT EDGE IF NOT EXISTS belongs_to(weight) VALUES 'sub_demo' -> 'dom_demo': (1.0);")
        run(session, "INSERT EDGE IF NOT EXISTS belongs_to(weight) VALUES 'tech_demo' -> 'sub_demo': (1.0);")
        run(session, "INSERT EDGE IF NOT EXISTS supports(weight) VALUES 'mat_demo' -> 'tech_demo': (1.0);")

        for tag in ["domain", "subdomain", "technology", "material"]:
            resp = run(session, f"MATCH (v:{tag}) RETURN count(v) AS c;")
            try:
                print(f"  count({tag}) =", resp.row_values(0)[0].as_int())
            except Exception as exc:
                print(f"  count({tag}) parse:", exc)

        print("BOOTSTRAP DONE")
    finally:
        session.release()
        pool.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
