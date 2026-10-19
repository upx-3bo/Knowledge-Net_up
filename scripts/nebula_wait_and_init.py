#!/usr/bin/env python3
from __future__ import annotations

import time
from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool

HOST, PORT = "127.0.0.1", 9669
USER, PWD = "root", ""
SPACE = "auto_innovation_kg"


def run(session, nql: str, fatal: bool = True):
    resp = session.execute(nql)
    ok = resp.is_succeeded()
    print(("OK  " if ok else "FAIL"), nql[:140].replace("\n", " "))
    if not ok:
        print("   ", resp.error_msg())
        if fatal:
            raise SystemExit(1)
    return resp


def hosts_online(session) -> bool:
    resp = session.execute("SHOW HOSTS;")
    if not resp.is_succeeded():
        print("SHOW HOSTS fail:", resp.error_msg())
        return False
    # print raw-ish
    try:
        rows = resp.row_size()
        print(f"SHOW HOSTS rows={rows}")
        for i in range(rows):
            vals = [str(v) for v in resp.row_values(i)]
            print(" ", vals)
            joined = " ".join(vals).upper()
            if "ONLINE" in joined and "STORAGE" in joined:
                return True
            if "ONLINE" in joined:
                return True
    except Exception as exc:
        print("parse hosts:", exc)
    return False


def main() -> None:
    cfg = Config()
    cfg.max_connection_pool_size = 4
    pool = ConnectionPool()
    assert pool.init([(HOST, PORT)], cfg)
    session = pool.get_session(USER, PWD)
    try:
        run(session, 'ADD HOSTS "127.0.0.1":9779;', fatal=False)
        for i in range(30):
            if hosts_online(session):
                print("storage online")
                break
            print(f"waiting hosts... {i}")
            time.sleep(3)
        else:
            print("WARN: hosts not clearly ONLINE, continue anyway")

        run(
            session,
            f"CREATE SPACE IF NOT EXISTS {SPACE}"
            f"(vid_type=FIXED_STRING(64), partition_num=10, replica_factor=1);",
        )
        # wait for space ready
        for i in range(20):
            resp = session.execute(f"USE {SPACE};")
            if resp.is_succeeded():
                print("USE ok at try", i)
                break
            print("USE wait", i, resp.error_msg())
            time.sleep(2)
        else:
            raise SystemExit("USE space failed")

        # drop & recreate tags if needed for clean state
        for obj in [
            "DROP TAG INDEX IF EXISTS idx_domain_name;",
            "DROP TAG INDEX IF EXISTS idx_subdomain_name;",
            "DROP TAG INDEX IF EXISTS idx_technology_name;",
            "DROP TAG INDEX IF EXISTS idx_material_name;",
            "DROP TAG IF EXISTS domain;",
            "DROP TAG IF EXISTS subdomain;",
            "DROP TAG IF EXISTS technology;",
            "DROP TAG IF EXISTS material;",
            "DROP EDGE IF EXISTS belongs_to;",
            "DROP EDGE IF EXISTS supports;",
            "DROP EDGE IF EXISTS relates_to;",
        ]:
            run(session, obj, fatal=False)
        time.sleep(3)

        for nql in [
            "CREATE TAG IF NOT EXISTS domain(name string, description string);",
            "CREATE TAG IF NOT EXISTS subdomain(name string, description string);",
            "CREATE TAG IF NOT EXISTS technology(name string, description string, keywords string, status string);",
            "CREATE TAG IF NOT EXISTS material(name string, material_type string, title string, summary string, source_url string, published_at string);",
            "CREATE EDGE IF NOT EXISTS belongs_to(weight double);",
            "CREATE EDGE IF NOT EXISTS supports(weight double);",
            "CREATE EDGE IF NOT EXISTS relates_to(relation_type string, weight double);",
        ]:
            run(session, nql)
        time.sleep(3)
        run(session, "SHOW TAGS;")
        run(session, "SHOW EDGES;")

        for nql in [
            "CREATE TAG INDEX IF NOT EXISTS idx_domain_name ON domain(name(64));",
            "CREATE TAG INDEX IF NOT EXISTS idx_subdomain_name ON subdomain(name(64));",
            "CREATE TAG INDEX IF NOT EXISTS idx_technology_name ON technology(name(64));",
            "CREATE TAG INDEX IF NOT EXISTS idx_material_name ON material(name(64));",
        ]:
            run(session, nql, fatal=False)
        time.sleep(8)
        run(session, "REBUILD TAG INDEX;", fatal=False)

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
                print(f"count({tag})=", resp.row_values(0)[0].as_int())
            except Exception as exc:
                print("count parse", tag, exc)
        print("INIT DONE")
    finally:
        session.release()
        pool.close()


if __name__ == "__main__":
    main()
