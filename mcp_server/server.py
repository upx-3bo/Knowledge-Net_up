"""MCP Server — expose Nebula L0–L3 graph tools to AI clients."""

import json
import os
import sys
from typing import Any, Dict, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mcp.server.fastmcp import FastMCP

from backend.store import EDGES, TAGS, GraphStore, make_vid

mcp = FastMCP("ai4knowledge-net")


def _store():
    return GraphStore()


def _json(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


def _find_by_name(name, tag=None):
    # type: (str, Optional[str]) -> Optional[Dict[str, Any]]
    items = _store().list_vertices(tag=tag, keyword=name, limit=50)
    for item in items:
        if item.get("props", {}).get("name") == name:
            return item
    return None


def _ensure_named(tag, name, extra=None):
    # type: (str, str, Optional[Dict[str, Any]]) -> Dict[str, Any]
    found = _find_by_name(name, tag=tag)
    if found:
        return found
    prefix = {"domain": "dom", "subdomain": "sub", "technology": "tech", "material": "mat"}[tag]
    props = {"name": name}
    if extra:
        props.update(extra)
    return _store().insert_vertex(tag, make_vid(prefix), props)


@mcp.tool()
def kg_stats() -> str:
    """获取知识库各层节点数量统计。"""
    return _json(_store().stats())


@mcp.tool()
def kg_schema() -> str:
    """查看当前图 Schema（Tag / Edge 清单）。"""
    return _json({"tags": list(TAGS), "edges": list(EDGES)})


@mcp.tool()
def kg_search(keyword: str, tag: str = "", limit: int = 20) -> str:
    """按关键词搜索节点。tag 可选：domain/subdomain/technology/material，空表示全类型。"""
    tag_arg = tag.strip() or None
    if tag_arg and tag_arg not in TAGS:
        return _json({"error": f"unsupported tag: {tag_arg}", "allow": list(TAGS)})
    items = _store().list_vertices(tag=tag_arg, keyword=keyword, limit=limit)
    return _json({"count": len(items), "items": items})


@mcp.tool()
def kg_get_node(vid: str = "", name: str = "") -> str:
    """按 vid 或精确 name 获取节点详情。二者至少提供一个。"""
    store = _store()
    if vid:
        node = store.get_vertex(vid)
    elif name:
        node = _find_by_name(name)
    else:
        return _json({"error": "vid or name required"})
    if not node:
        return _json({"error": "not found", "vid": vid, "name": name})
    return _json(node)


@mcp.tool()
def kg_subgraph(vid: str = "", name: str = "", depth: int = 1) -> str:
    """获取节点子图（默认 1 跳，最大 3）。可用 vid 或精确 name。"""
    store = _store()
    if not vid and name:
        node = _find_by_name(name)
        if not node:
            return _json({"error": "name not found", "name": name})
        vid = node["vid"]
    if not vid:
        return _json({"error": "vid or name required"})
    depth = max(1, min(int(depth), 3))
    data = store.neighbors(vid, depth=depth)
    if not data["nodes"]:
        return _json({"error": "vertex not found", "vid": vid})
    return _json(data)


@mcp.tool()
def kg_add_technology(
    name: str,
    domain_name: str,
    subdomain_name: str,
    description: str = "",
    keywords: str = "",
    status: str = "active",
) -> str:
    """添加技术点(L3)，并自动确保领域(L1)/子领域(L2)存在且用 belongs_to 连接。"""
    store = _store()
    domain = _ensure_named("domain", domain_name)
    subdomain = _ensure_named("subdomain", subdomain_name)
    store.insert_edge("belongs_to", subdomain["vid"], domain["vid"], {"weight": 1.0})

    existing = _find_by_name(name, tag="technology")
    if existing:
        tech = existing
    else:
        tech = store.insert_vertex(
            "technology",
            make_vid("tech"),
            {
                "name": name,
                "description": description,
                "keywords": keywords,
                "status": status or "active",
            },
        )
    store.insert_edge("belongs_to", tech["vid"], subdomain["vid"], {"weight": 1.0})
    return _json(
        {
            "technology": tech,
            "subdomain": subdomain,
            "domain": domain,
            "edges": [
                f"{subdomain['vid']} -belongs_to-> {domain['vid']}",
                f"{tech['vid']} -belongs_to-> {subdomain['vid']}",
            ],
        }
    )


@mcp.tool()
def kg_add_material(
    name: str,
    tech_name: str,
    material_type: str = "doc",
    title: str = "",
    summary: str = "",
    source_url: str = "",
    published_at: str = "",
) -> str:
    """添加支撑材料(L0)，并用 supports 连到已有技术点(按名称)。"""
    tech = _find_by_name(tech_name, tag="technology")
    if not tech:
        return _json({"error": f"technology not found: {tech_name}"})
    mat = _ensure_named(
        "material",
        name,
        {
            "material_type": material_type,
            "title": title or name,
            "summary": summary,
            "source_url": source_url,
            "published_at": published_at,
        },
    )
    edge = _store().insert_edge("supports", mat["vid"], tech["vid"], {"weight": 1.0})
    return _json({"material": mat, "technology": tech, "edge": edge})


@mcp.tool()
def kg_add_relation(
    src_vid: str = "",
    dst_vid: str = "",
    src_name: str = "",
    dst_name: str = "",
    edge_type: str = "relates_to",
    relation_type: str = "related",
    weight: float = 0.8,
) -> str:
    """在两节点间加边。可用 vid 或 name；edge_type: belongs_to|supports|relates_to。"""
    if edge_type not in EDGES:
        return _json({"error": f"unsupported edge: {edge_type}", "allow": list(EDGES)})
    store = _store()
    if not src_vid and src_name:
        src = _find_by_name(src_name)
        if not src:
            return _json({"error": f"src not found: {src_name}"})
        src_vid = src["vid"]
    if not dst_vid and dst_name:
        dst = _find_by_name(dst_name)
        if not dst:
            return _json({"error": f"dst not found: {dst_name}"})
        dst_vid = dst["vid"]
    if not src_vid or not dst_vid:
        return _json({"error": "src/dst vid or name required"})
    props: dict[str, Any] = {"weight": weight}
    if edge_type == "relates_to":
        props["relation_type"] = relation_type
    edge = store.insert_edge(edge_type, src_vid, dst_vid, props)
    return _json(edge)


@mcp.tool()
def kg_delete_node(vid: str) -> str:
    """按 vid 删除节点及其关联边。"""
    ok = _store().delete_vertex(vid)
    return _json({"deleted": ok, "vid": vid})


@mcp.tool()
def kg_extract_from_text(
    text: str,
    title: str = "",
    translate: bool = True,
    save: bool = False,
) -> str:
    """从文本 AI 抽取技术点/材料；save=True 时写入图谱。需配置 LLM_API_KEY。"""
    from backend.services.extractor import commit_extraction, extract_from_text
    from backend.services.llm import LLMNotConfigured

    try:
        data = extract_from_text(text, title=title, translate=translate)
    except LLMNotConfigured as exc:
        return _json({"error": str(exc)})
    except Exception as exc:
        return _json({"error": f"extract failed: {exc}"})
    if not save:
        return _json({"extracted": data, "written": None})
    try:
        written = commit_extraction(data)
    except Exception as exc:
        return _json({"extracted": data, "error": f"commit failed: {exc}"})
    return _json({"extracted": data, "written": written})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
