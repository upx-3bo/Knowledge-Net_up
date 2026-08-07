from fastapi import APIRouter, HTTPException
from backend.models.schemas import (
    TechnologyCreate, CategoryCreate, StandardCreate,
    PatentCreate, ResourceCreate, DocumentUpload, RelationCreate
)
from backend.services.graph_store import get_store
from datetime import datetime

router = APIRouter(prefix="/knowledge", tags=["知识管理"])
kb = get_store()


def vid(name):
    return name.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")


@router.post("/technology", summary="创建技术节点")
def create_technology(t: TechnologyCreate):
    kb.insert_vertex("technology", vid(t.name), {
        "name": t.name,
        "description": t.description,
        "trl": t.trl,
        "status": t.status,
        "keywords": t.keywords,
    })
    if t.category:
        kb.insert_edge("belongs_to", vid(t.name), vid(t.category), {"weight": 1.0})
    return {"status": "ok", "vid": vid(t.name)}


@router.get("/technology", summary="列出技术节点（支持关键词搜索）")
def list_technologies(keyword: str = ""):
    results = kb.query_vertices(tag="technology", keyword=keyword)
    return [r["props"] for r in results]


@router.get("/technology/{vid}", summary="获取单个技术节点详情")
def get_technology(vid: str):
    node = kb.get_vertex(vid)
    if not node:
        raise HTTPException(404, "Technology not found")
    neighbors = kb.get_neighbors(vid, depth=1)
    return {"node": node, "neighbors": neighbors}


@router.post("/category", summary="创建分类节点")
def create_category(c: CategoryCreate):
    kb.insert_vertex("category", vid(c.name), {
        "name": c.name, "level": c.level, "description": c.description,
    })
    if c.parent:
        kb.insert_edge("contains", vid(c.parent), vid(c.name), {"weight": 1.0})
    return {"status": "ok", "vid": vid(c.name)}


@router.get("/category", summary="列出所有分类")
def list_categories():
    results = kb.query_vertices(tag="category")
    return [r["props"] for r in sorted(results, key=lambda x: x["props"].get("level", 0))]


@router.post("/standard", summary="创建标准节点")
def create_standard(s: StandardCreate):
    kb.insert_vertex("standard", vid(s.code), {
        "name": s.name, "code": s.code, "organization": s.organization,
        "type": s.type, "publish_year": s.publish_year or 0, "description": s.description,
    })
    return {"status": "ok", "vid": vid(s.code)}


@router.get("/standard", summary="列出所有标准")
def list_standards():
    results = kb.query_vertices(tag="standard")
    return [r["props"] for r in results]


@router.post("/patent", summary="创建专利节点")
def create_patent(p: PatentCreate):
    kb.insert_vertex("patent", vid(p.number or p.title), {
        "title": p.title, "number": p.number, "applicant": p.applicant,
        "inventors": p.inventors, "abstract": p.abstract,
        "apply_date": p.apply_date, "status": p.status,
    })
    return {"status": "ok", "vid": vid(p.number or p.title)}


@router.post("/resource", summary="创建资源节点")
def create_resource(r: ResourceCreate):
    kb.insert_vertex("resource", vid(r.name), {
        "name": r.name, "type": r.type, "description": r.description,
        "contact": r.contact, "link": r.link, "department": r.department,
    })
    return {"status": "ok", "vid": vid(r.name)}


@router.post("/document", summary="上传文档（可触发AI提取）")
def upload_document(d: DocumentUpload):
    kb.insert_vertex("document", vid(d.title), {
        "title": d.title, "file_type": d.file_type, "summary": d.summary,
        "content": d.content, "source": d.source,
    })
    if d.target_technology:
        kb.insert_edge("derived_from", vid(d.title), vid(d.target_technology), {"source_type": "document"})
    return {"status": "ok", "vid": vid(d.title)}


@router.post("/relation", summary="创建关系（边）")
def create_relation(r: RelationCreate):
    kb.insert_edge(r.edge_type, r.src_vid, r.dst_vid, r.props or None)
    return {"status": "ok"}
