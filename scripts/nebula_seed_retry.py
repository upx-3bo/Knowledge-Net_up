#!/usr/bin/env python3
import time
from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool


def main() -> None:
    cfg = Config()
    cfg.max_connection_pool_size = 2
    pool = ConnectionPool()
    assert pool.init([("127.0.0.1", 9669)], cfg)
    s = pool.get_session("root", "")

    def run_retry(nql: str, times: int = 8) -> None:
        for i in range(times):
            r = s.execute(nql)
            if r.is_succeeded():
                print("OK", nql[:90])
                return
            print("retry", i, r.error_msg())
            time.sleep(2)
        raise SystemExit("failed: " + nql)

    run_retry("USE auto_innovation_kg;")
    time.sleep(5)
    stmts = [
        "INSERT VERTEX IF NOT EXISTS subdomain(name, description) VALUES 'sub_demo': ('示例子域', 'smoke');",
        "INSERT VERTEX IF NOT EXISTS technology(name, description, keywords, status) VALUES 'tech_demo': ('示例技术点', '连通性验证', 'demo', 'draft');",
        "INSERT VERTEX IF NOT EXISTS material(name, material_type, title, summary, source_url, published_at) VALUES 'mat_demo': ('示例材料', 'doc', 'Smoke Test', '可删除', '', '2026-08-07');",
        "INSERT EDGE IF NOT EXISTS belongs_to(weight) VALUES 'sub_demo' -> 'dom_demo': (1.0);",
        "INSERT EDGE IF NOT EXISTS belongs_to(weight) VALUES 'tech_demo' -> 'sub_demo': (1.0);",
        "INSERT EDGE IF NOT EXISTS supports(weight) VALUES 'mat_demo' -> 'tech_demo': (1.0);",
    ]
    for st in stmts:
        run_retry(st)
        time.sleep(0.5)

    for tag in ["domain", "subdomain", "technology", "material"]:
        r = s.execute(f"MATCH (v:{tag}) RETURN count(v) AS c;")
        if r.is_succeeded():
            print(f"count({tag})=", r.row_values(0)[0].as_int())
        else:
            print(tag, r.error_msg())
    s.release()
    pool.close()
    print("SEED OK")


if __name__ == "__main__":
    main()
