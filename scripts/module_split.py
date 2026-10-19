import sys
import json
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config
from backend.config import (
    NEBULA_HOST, NEBULA_PORT, NEBULA_USER, NEBULA_PASSWORD, NEBULA_SPACE,
)

DRY = "--apply" not in sys.argv

DDL = [
    "CREATE TAG IF NOT EXISTS module(name string, description string, keywords string, status string);",
    "CREATE TAG IF NOT EXISTS vehicle(name string, description string);",
]


def connect():
    pool = ConnectionPool()
    pool.init([(str(NEBULA_HOST), NEBULA_PORT)], Config())
    sess = pool.get_session(NEBULA_USER, NEBULA_PASSWORD)
    sess.execute(f"USE {NEBULA_SPACE};")
    return pool, sess


def esc(v):
    if v is None:
        return ""
    return str(v).replace("\\", "\\\\").replace("'", "\\'")


def fixed_weight(p):
    w = p.get("weight", 1)
    return w


def main():
    pool, sess = connect()
    try:
        if DRY:
            print("[dry-run] skip DDL")
        else:
            for d in DDL:
                r = sess.execute(d)
                print("DDL ok:", r.is_succeeded(), d.strip().rstrip(';'), r.error_msg() or "")
                time.sleep(0.2)

        all_v = []
        for tag in ("domain", "subdomain", "technology", "material", "module", "vehicle"):
            r = sess.execute(f"MATCH (v:{tag}) RETURN id(v) AS vid, v LIMIT 100000")
            for row in r.as_primitive():
                vid = row["vid"]
                tags = row["v"].get("tags", {})
                rec = {"vid": vid, "tag": tag, "props": tags.get(tag, {})}
                all_v.append(rec)
        print("loaded vertices:", len(all_v))

        rows = []
        for et in ("belongs_to", "supports", "relates_to"):
            r = sess.execute(f"MATCH ()-[e:{et}]->() RETURN e LIMIT 100000")
            for row in r.as_primitive():
                er = row["e"]
                rows.append({"type": er["type"], "s": er["src"], "d": er["dst"], "props": er.get("props") or {}})
        print("loaded edges:", len(rows))

        vmap = {x["vid"]: x for x in all_v}
        by_s = {}
        by_d = {}
        for e in rows:
            by_s.setdefault(e["s"], []).append(e)
            by_d.setdefault(e["d"], []).append(e)

        tech_keys = [k for k, x in vmap.items() if x["tag"] == "technology"]
        cands = []
        for k in tech_keys:
            pars = [e for e in by_s.get(k, []) if e["type"] == "belongs_to"]
            nested = any(vmap.get(e["d"], {}).get("tag") == "technology" for e in pars)
            if not nested:
                cands.append(k)
        print("module candidates:", len(cands))

        if DRY:
            for k in cands[:8]:
                print("  cand:", k, vmap[k]["props"].get("name", ""))
            print("[dry-run] done, nothing written")
            return

        new_ids = set(x["vid"] for x in all_v)
        ok = 0
        for k in cands:
            parts = k.split("_", 1)
            new_vid = "mod_" + (parts[1] if len(parts) > 1 else parts[0])
            n = 1
            while new_vid in new_ids:
                new_vid = f"mod_{k}_{n}"
                n += 1
            new_ids.add(new_vid)

            node = vmap[k]
            p = node["props"]
            ins = sess.execute(
                f"INSERT VERTEX module(name, description, keywords, status) VALUES '{new_vid}':( "
                f"'{esc(p.get('name',''))}','{esc(p.get('description',''))}','{esc(p.get('keywords',''))}','{esc(p.get('status',''))}');"
            )
            if not ins.is_succeeded():
                print("INSERT VERTEX fail", k, ins.error_msg())
                continue

            def run(q, label):
                rr = sess.execute(q)
                if not rr.is_succeeded():
                    print(f"{label} fail for {k}:", rr.error_msg())

            for e in by_s.get(k, []):
                if e["type"] == "belongs_to":
                    run(f"INSERT EDGE belongs_to(weight) VALUES '{new_vid}'->'{e['d']}':({fixed_weight(e['props'])})", "edge")
            for e in by_d.get(k, []):
                if e["type"] == "belongs_to":
                    run(f"INSERT EDGE belongs_to(weight) VALUES '{e['s']}'->'{new_vid}':({fixed_weight(e['props'])})", "edge")
                elif e["type"] == "supports":
                    run(f"INSERT EDGE supports(weight) VALUES '{e['s']}'->'{new_vid}':({fixed_weight(e['props'])})", "edge")
                elif e["type"] == "relates_to":
                    pass

            check = sess.execute(f"MATCH (v:module)-[:belongs_to]->(p) WHERE id(v)=='{new_vid}' RETURN count(*) AS c").as_primitive()
            has_parent = check and check[0]["c"] > 0
            if not has_parent:
                dom = "[orphan]"
            else:
                dom = ""

            rv = sess.execute(f"DELETE VERTEX '{k}' WITH EDGE;")
            if not rv.is_succeeded():
                print("DELETE VERTEX fail", k, rv.error_msg())
            else:
                ok += 1
                print(f"  migrated {k} -> {new_vid} ({p.get('name','')[:20]}) {dom}")

        print("migrated:", ok, "/", len(cands))

        r = sess.execute("MATCH (v) RETURN tags(v)[0] AS t, count(*) AS c")
        for row in r.as_primitive():
            print("distribution:", row)
        r = sess.execute("MATCH ()-[e]->() RETURN type(e) AS t, count(*) AS c")
        for row in r.as_primitive():
            print("edge distribution:", row)
    finally:
        sess.release()
        pool.close()


if __name__ == "__main__":
    main()
