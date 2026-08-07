from fastapi import APIRouter, Query
from backend.services.graph_store import get_store

router = APIRouter(prefix="/search", tags=["智能搜索"])
kb = get_store()


@router.get("/graph", summary="搜索图谱（以关键词为中心的子图）")
def search_graph(keyword: str = Query(...), depth: int = Query(1)):
    results = kb.full_text_search(keyword)
    all_nodes = {}
    all_edges = []
    for r in results:
        vid = r["vid"]
        all_nodes[vid] = r
        neighbors = kb.get_neighbors(vid, depth=depth)
        for n in neighbors.get("nodes", []):
            all_nodes[n["vid"]] = n
        for e in neighbors.get("edges", []):
            all_edges.append(e)
    return {"nodes": list(all_nodes.values()), "edges": all_edges}


@router.get("/path", summary="查找两节点间的路径")
def find_path(source: str = Query(...), target: str = Query(...)):
    path = kb.find_path(source, target)
    return {"path": path}


@router.get("/technology-by-category", summary="按分类查技术节点")
def get_technology_by_category(category: str = Query(...)):
    edges = kb.query_edges(edge_type="belongs_to")
    techs = []
    for e in edges:
        node = kb.get_vertex(e["dst_vid"])
        if node and node["props"].get("name") == category:
            src = kb.get_vertex(e["src_vid"])
            if src:
                techs.append(src["props"])
    return techs


@router.get("/full-text", summary="全文搜索")
def full_text_search(query: str = Query(...)):
    return kb.full_text_search(query)
