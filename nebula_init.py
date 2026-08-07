import os
import sys
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config

HOST = os.getenv("NEBULA_HOST", "127.0.0.1")
PORT = int(os.getenv("NEBULA_PORT", "9669"))
USER = os.getenv("NEBULA_USER", "root")
PWD = os.getenv("NEBULA_PASSWORD", "nebula")
SPACE = os.getenv("NEBULA_SPACE", "auto_knowledge")


def connect():
    config = Config()
    config.max_connection_pool_size = 10
    pool = ConnectionPool()
    pool.init([(HOST, PORT)], config)
    session = pool.get_session(USER, PWD)
    return pool, session


def run(session, nql):
    resp = session.execute(nql)
    if not resp.is_succeeded():
        raise RuntimeError(f"FAILED: {nql}\n  msg: {resp.error_msg()}")
    return resp


# 图 Schema：8 种 Tag + 9 种 Edge
TAGS = {
    "category": ["name string", "level int", "description string"],
    "technology": ["name string", "description string", "trl int", "status string", "keywords string"],
    "component": ["name string", "function string", "specifications string", "manufacturer string"],
    "standard": ["name string", "code string", "organization string", "type string", "publish_year int", "description string"],
    "patent": ["title string", "number string", "applicant string", "inventors string", "abstract string", "apply_date string", "status string"],
    "resource": ["name string", "type string", "description string", "contact string", "link string", "department string"],
    "document": ["title string", "file_type string", "summary string", "content string", "source string"],
}

EDGES = {
    "belongs_to": ["weight double"],
    "contains": ["weight double"],
    "relates_to": ["relation_type string", "weight double"],
    "has_standard": ["compliance_level string"],
    "has_patent": ["relevance double"],
    "references": ["relevance double"],
    "implements": ["status string"],
    "depends_on": ["description string"],
    "derived_from": ["source_type string"],
}


def init_schema(session):
    print(f"[1/3] 创建 Space: {SPACE} ...")
    run(session, f"CREATE SPACE IF NOT EXISTS {SPACE}(vid_type=FIXED_STRING(256), partition_num=10, replica_factor=1);")
    # 等待 space 生效
    import time
    time.sleep(2)
    run(session, f"USE {SPACE};")

    print(f"[2/3] 创建 Tag ...")
    for tag, props in TAGS.items():
        run(session, f"CREATE TAG IF NOT EXISTS {tag}({', '.join(props)});")

    print(f"[3/3] 创建 Edge ...")
    for edge, props in EDGES.items():
        run(session, f"CREATE EDGE IF NOT EXISTS {edge}({', '.join(props)});")
    print("Schema 初始化完成！")


def seed_data(session):
    path = os.path.join(os.path.dirname(__file__), "init_data.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    run(session, f"USE {SPACE};")

    def vid(name):
        return str(name).replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")

    def val(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return str(v)
        return repr(str(v))

    def ins_v(tag, vid_name, props):
        keys = ", ".join(props.keys())
        vals = ", ".join(val(x) for x in props.values())
        run(session, f"INSERT VERTEX IF NOT EXISTS {tag}({keys}) VALUES '{vid(vid_name)}': ({vals});")

    def ins_e(etype, src, dst, props=None):
        if props:
            keys = ", ".join(props.keys())
            vals = ", ".join(val(x) for x in props.values())
            run(session, f"INSERT EDGE IF NOT EXISTS {etype}({keys}) VALUES '{vid(src)}' -> '{vid(dst)}': ({vals});")
        else:
            run(session, f"INSERT EDGE IF NOT EXISTS {etype}() VALUES '{vid(src)}' -> '{vid(dst)}': ();")

    print("导入分类...")
    for cat in data["categories"]:
        ins_v("category", cat["name"], cat)
    for rel in data["category_relations"]:
        ins_e("contains", rel["parent"], rel["child"], {"weight": 1.0})

    print("导入技术...")
    for tech in data["technologies"]:
        ins_v("technology", tech["name"], tech)
    for tc in data["technology_categories"]:
        ins_e("belongs_to", tc["tech"], tc["cat"], {"weight": 1.0})

    print("导入标准...")
    for std in data["standards"]:
        ins_v("standard", std["code"], std)
    for ts in data["technology_standards"]:
        ins_e("has_standard", ts["tech"], ts["std_code"], {"compliance_level": ts.get("compliance", "")})

    print("导入专利...")
    for pat in data["patents"]:
        ins_v("patent", pat["number"], pat)
    for tp in data["technology_patents"]:
        ins_e("has_patent", tp["tech"], tp["patent_num"], {"relevance": 1.0})

    print("导入资源...")
    for res in data["resources"]:
        ins_v("resource", res["name"], res)
    for tr in data["technology_resources"]:
        ins_e("references", tr["tech"], tr["resource_name"], {"relevance": 1.0})

    print("导入技术关系...")
    for rel in data["technology_relations"]:
        if rel["type"] == "belongs_to":
            ins_e("belongs_to", rel["from"], rel["to"], {"weight": 1.0})
        elif rel["type"] == "relates_to":
            ins_e("relates_to", rel["from"], rel["to"], {"relation_type": "相关", "weight": 0.8})

    print(f"种子数据导入完成！")


if __name__ == "__main__":
    pool, session = connect()
    try:
        init_schema(session)
        seed_data(session)
        # 校验
        run(session, f"USE {SPACE};")
        for tag in ["technology", "category", "standard", "patent", "resource"]:
            r = run(session, f"MATCH (v:{tag}) RETURN count(v) AS c;")
            print(tag, r.values())
    finally:
        session.release()
        pool.close()
