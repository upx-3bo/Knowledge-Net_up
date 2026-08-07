from fastapi import APIRouter, Query
from backend.services.graph_store import get_store

router = APIRouter(prefix="/classification", tags=["技术分类与标准化"])
kb = get_store()


@router.get("/tree", summary="获取分类树")
def get_classification_tree():
    edges = kb.query_edges(edge_type="contains")
    parent_children = {}
    for e in edges:
        parent = kb.get_vertex(e["src_vid"])
        child = kb.get_vertex(e["dst_vid"])
        if parent and child:
            pname = parent["props"].get("name", e["src_vid"])
            cname = child["props"].get("name", e["dst_vid"])
            if pname not in parent_children:
                parent_children[pname] = []
            parent_children[pname].append(cname)
    return [{"parent": k, "children": v} for k, v in parent_children.items()]


@router.get("/technology-standards", summary="查询某技术相关的标准")
def get_technology_standards(tech_name: str = Query(...)):
    edges = kb.query_edges(edge_type="has_standard")
    results = []
    tech_vid = tech_name.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
    for e in edges:
        if e["src_vid"] == tech_vid:
            std = kb.get_vertex(e["dst_vid"])
            if std:
                p = std["props"]
                results.append({
                    "code": p.get("code", ""),
                    "name": p.get("name", ""),
                    "org": p.get("organization", ""),
                })
    return results


@router.get("/standard-analysis", summary="标准分析（某标准关联的技术）")
def standard_analysis(standard_code: str = Query(...)):
    edges = kb.query_edges(edge_type="has_standard")
    results = []
    for e in edges:
        dst = kb.get_vertex(e["dst_vid"])
        if dst and dst["props"].get("code") == standard_code:
            src = kb.get_vertex(e["src_vid"])
            if src:
                p = src["props"]
                results.append({
                    "technology": p.get("name", ""),
                    "trl": p.get("trl", 0),
                })
    return results


@router.get("/resource-pool", summary="获取资源池（可选按技术过滤）")
def get_resource_pool(tech_name: str = Query(default="")):
    if tech_name:
        tech_vid = tech_name.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
        edges = kb.query_edges(edge_type="references")
        results = []
        for e in edges:
            if e["src_vid"] == tech_vid:
                res = kb.get_vertex(e["dst_vid"])
                if res:
                    p = res["props"]
                    results.append({
                        "name": p.get("name", ""),
                        "type": p.get("type", ""),
                        "department": p.get("department", ""),
                        "contact": p.get("contact", ""),
                    })
        return results
    else:
        results = kb.query_vertices(tag="resource")
        return [r["props"] for r in results]
