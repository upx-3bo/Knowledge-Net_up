"""
MCP Server — 汽车创新技术知识图谱的 MCP 工具集。
适配新层级模型：domain(L1)/subdomain(L2)/tech_point(L3)/material(L0)
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
from dotenv import load_dotenv
from backend.services.graph_store import get_store

load_dotenv()

server = Server("auto-knowledge-mcp")
kb = get_store()


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_tech",
            description="按关键词搜索技术点（L3）或任意节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词（模糊匹配节点名称）"}
                },
                "required": ["keyword"],
            },
        ),
        types.Tool(
            name="get_node_detail",
            description="获取某节点的详情及其关联子图",
            inputSchema={
                "type": "object",
                "properties": {
                    "vid": {"type": "string", "description": "节点 ID"},
                    "depth": {"type": "integer", "description": "关联深度（默认1）", "default": 1},
                },
                "required": ["vid"],
            },
        ),
        types.Tool(
            name="list_by_domain",
            description="列出某顶层领域下的所有技术点",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain_name": {"type": "string", "description": "领域名称（如"动力电池"）"}
                },
                "required": ["domain_name"],
            },
        ),
        types.Tool(
            name="add_tech_point",
            description="添加一个新的技术点节点（L3），并关联到子领域",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技术点名称（≤8字）"},
                    "subdomain_name": {"type": "string", "description": "所属子领域名称"},
                    "domain_name": {"type": "string", "description": "所属顶层领域名称"},
                    "description": {"type": "string", "description": "技术描述", "default": ""},
                },
                "required": ["name", "subdomain_name", "domain_name"],
            },
        ),
        types.Tool(
            name="add_relation",
            description="在两个节点之间添加一条边",
            inputSchema={
                "type": "object",
                "properties": {
                    "src_name": {"type": "string", "description": "源节点名称"},
                    "dst_name": {"type": "string", "description": "目标节点名称"},
                    "edge_type": {"type": "string", "description": "边类型: belongs_to | supports", "default": "belongs_to"},
                },
                "required": ["src_name", "dst_name", "edge_type"],
            },
        ),
        types.Tool(
            name="get_stats",
            description="获取知识图谱统计信息",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="extract_from_text",
            description="用 AI 从技术资讯文本中提取结构化知识并入库（需配置 LLM_API_KEY）",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "资讯文本内容"},
                    "title": {"type": "string", "description": "资讯标题", "default": ""},
                },
                "required": ["text"],
            },
        ),
    ]


def _find_by_name(name: str):
    results = kb.query_vertices(keyword=name, limit=50)
    for r in results:
        if r["props"].get("name") == name:
            return r
    return None


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "search_tech":
        keyword = arguments["keyword"]
        results = kb.query_vertices(keyword=keyword, limit=20)
        return [types.TextContent(type="text", text=json.dumps([{"vid": r["vid"], "tag": r["tag"], "name": r["props"].get("name", ""), "level": r["props"].get("level", "")} for r in results], ensure_ascii=False, indent=2))]

    elif name == "get_node_detail":
        vid = arguments["vid"]
        depth = arguments.get("depth", 1)
        node = kb.get_vertex(vid)
        neighbors = kb.get_neighbors(vid, depth=depth)
        return [types.TextContent(type="text", text=json.dumps({"node": node, "neighbors": neighbors}, ensure_ascii=False, indent=2))]

    elif name == "list_by_domain":
        domain_name = arguments["domain_name"]
        domain_node = _find_by_name(domain_name)
        if not domain_node:
            return [types.TextContent(type="text", text=json.dumps({"error": f"领域 '{domain_name}' 未找到"}, ensure_ascii=False))]
        # 找所有 belongs_to 指向 domain 的 subdomain
        edges = kb.query_edges(edge_type="belongs_to")
        tech_list = []
        for e in edges:
            if e["dst_vid"] == domain_node["vid"]:
                child = kb.get_vertex(e["src_vid"])
                if child and child["tag"] == "subdomain":
                    # 再找该 subdomain 下的技术点
                    sub_edges = kb.query_edges(edge_type="belongs_to")
                    for se in sub_edges:
                        if se["dst_vid"] == child["vid"]:
                            tech = kb.get_vertex(se["src_vid"])
                            if tech and tech["tag"] == "technology":
                                tech_list.append({"vid": tech["vid"], "name": tech["props"].get("name", "")})
        return [types.TextContent(type="text", text=json.dumps({"domain": domain_name, "tech_count": len(tech_list), "tech_points": tech_list}, ensure_ascii=False, indent=2))]

    elif name == "add_tech_point":
        import uuid as uuid_mod
        tp_name = arguments["name"]
        sub_name = arguments["subdomain_name"]
        dom_name = arguments["domain_name"]
        desc = arguments.get("description", "")
        # 查找/创建 domain
        dom_node = _find_by_name(dom_name)
        if not dom_node:
            dom_vid = "node_" + uuid_mod.uuid4().hex[:10]
            kb.insert_vertex("domain", dom_vid, {"name": dom_name, "level": 1})
        else:
            dom_vid = dom_node["vid"]
        # 查找/创建 subdomain
        sub_node = _find_by_name(sub_name)
        if not sub_node:
            sub_vid = "node_" + uuid_mod.uuid4().hex[:10]
            kb.insert_vertex("subdomain", sub_vid, {"name": sub_name, "level": 2})
            kb.insert_edge("belongs_to", sub_vid, dom_vid)
        else:
            sub_vid = sub_node["vid"]
        # 创建技术点
        tp_vid = "node_" + uuid_mod.uuid4().hex[:10]
        kb.insert_vertex("technology", tp_vid, {"name": tp_name, "level": 3, "description": desc})
        kb.insert_edge("belongs_to", tp_vid, sub_vid)
        return [types.TextContent(type="text", text=json.dumps({"ok": True, "vid": tp_vid, "name": tp_name, "subdomain": sub_name, "domain": dom_name}, ensure_ascii=False))]

    elif name == "add_relation":
        src_name = arguments["src_name"]
        dst_name = arguments["dst_name"]
        edge_type = arguments["edge_type"]
        src_node = _find_by_name(src_name)
        dst_node = _find_by_name(dst_name)
        if not src_node:
            return [types.TextContent(type="text", text=json.dumps({"error": f"源节点 '{src_name}' 未找到"}, ensure_ascii=False))]
        if not dst_node:
            return [types.TextContent(type="text", text=json.dumps({"error": f"目标节点 '{dst_name}' 未找到"}, ensure_ascii=False))]
        eid = kb.insert_edge(edge_type, src_node["vid"], dst_node["vid"])
        return [types.TextContent(type="text", text=json.dumps({"ok": True, "edge_id": eid, "edge": f"{src_name} -[{edge_type}]-> {dst_name}"}, ensure_ascii=False))]

    elif name == "get_stats":
        all_nodes = kb.query_vertices(limit=10000)
        tag_count = {}
        level_count = {}
        for n in all_nodes:
            tag_count[n["tag"]] = tag_count.get(n["tag"], 0) + 1
            lv = n["props"].get("level", "?")
            level_count[lv] = level_count.get(lv, 0) + 1
        all_edges = kb.query_edges()
        edge_count = {}
        for e in all_edges:
            edge_count[e["edge_type"]] = edge_count.get(e["edge_type"], 0) + 1
        return [types.TextContent(type="text", text=json.dumps({"total_nodes": len(all_nodes), "by_tag": tag_count, "by_level": level_count, "total_edges": len(all_edges), "by_edge_type": edge_count}, ensure_ascii=False, indent=2))]

    elif name == "extract_from_text":
        from backend.services.extractor import extract_knowledge_from_text, save_extracted_knowledge
        text = arguments["text"]
        title = arguments.get("title", "")
        extracted = extract_knowledge_from_text(text, title)
        if "error" in extracted:
            return [types.TextContent(type="text", text=json.dumps(extracted, ensure_ascii=False))]
        saved = save_extracted_knowledge(extracted)
        return [types.TextContent(type="text", text=json.dumps({"extracted": extracted, "saved": saved}, ensure_ascii=False, indent=2))]

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="auto-knowledge-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
