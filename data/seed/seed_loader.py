import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from backend.services.graph_store import get_store


def load_seed_data():
    path = os.path.join(os.path.dirname(__file__), "init_data.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    kb = get_store()

    def vid(name):
        return name.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")

    print("导入分类...")
    for cat in data["categories"]:
        kb.insert_vertex("category", vid(cat["name"]), cat)
    for rel in data["category_relations"]:
        kb.insert_edge("contains", vid(rel["parent"]), vid(rel["child"]), {"weight": 1.0})

    print("导入技术节点...")
    for tech in data["technologies"]:
        kb.insert_vertex("technology", vid(tech["name"]), tech)
    for tc in data["technology_categories"]:
        kb.insert_edge("belongs_to", vid(tc["tech"]), vid(tc["cat"]), {"weight": 1.0})

    print("导入标准...")
    for std in data["standards"]:
        kb.insert_vertex("standard", vid(std["code"]), std)
    for ts in data["technology_standards"]:
        kb.insert_edge("has_standard", vid(ts["tech"]), vid(ts["std_code"]), {"compliance_level": ts.get("compliance", "")})

    print("导入专利...")
    for pat in data["patents"]:
        kb.insert_vertex("patent", vid(pat["number"]), pat)
    for tp in data["technology_patents"]:
        kb.insert_edge("has_patent", vid(tp["tech"]), vid(tp["patent_num"]), {"relevance": 1.0})

    print("导入资源...")
    for res in data["resources"]:
        kb.insert_vertex("resource", vid(res["name"]), res)
    for tr in data["technology_resources"]:
        kb.insert_edge("references", vid(tr["tech"]), vid(tr["resource_name"]), {"relevance": 1.0})

    print("导入技术间关系...")
    for rel in data["technology_relations"]:
        if rel["type"] == "belongs_to":
            kb.insert_edge("belongs_to", vid(rel["from"]), vid(rel["to"]), {"weight": 1.0})
        elif rel["type"] == "relates_to":
            kb.insert_edge("relates_to", vid(rel["from"]), vid(rel["to"]), {"relation_type": "相关", "weight": 0.8})

    print(f"完成！导入 {len(data['categories'])} 分类、{len(data['technologies'])} 技术、{len(data['standards'])} 标准、{len(data['patents'])} 专利、{len(data['resources'])} 资源")


if __name__ == "__main__":
    load_seed_data()
