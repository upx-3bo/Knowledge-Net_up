"""LLM extract / assist / commit into Nebula graph."""
from __future__ import annotations

from typing import Any

from backend import architecture
from backend.services.llm import chat_json, chat_text
from backend.store import GraphStore, make_vid

KNOWN_DOMAINS = [
    "底盘结构",
    "底盘控制架构",
    "车辆感知",
    "动力电池",
    "电驱与功率电子",
    "热管理",
    "智能座舱",
    "安全技术",
    "软件与E/E架构",
    "制造工艺",
    "轻量化材料",
]


def extract_from_text(text: str, title: str = "", translate: bool = False) -> dict[str, Any]:
    domains_hint = "、".join(KNOWN_DOMAINS)
    translate_instr = (
        "\n重要：请将所有提取结果（名称、描述、摘要等）翻译为中文。" if translate else ""
    )
    prompt = f"""你是汽车工程领域的知识抽取专家。从以下技术资料中抽取结构化知识，只返回 JSON。{translate_instr}

尽量复用已知顶层领域（不匹配可新建）: {domains_hint}

标题: {title}
正文:
{text[:8000]}

JSON 格式:
{{
  "domain": "上一层技术簇（≤12字，必填）",
  "subdomain": "中间层技术簇（≤12字，可空字符串；最小技术点无需中间层）",
  "tech_points": [
    {{"name": "技术点名称（≤16字）", "description": "一句话描述"}}
  ],
  "materials": [
    {{
      "name": "文档简称（≤20字）",
      "type": "paper|patent|news|doc|standard",
      "title": "原始标题",
      "summary": "摘要（≤100字）",
      "source_url": ""
    }}
  ],
  "tech_material_links": [
    {{"tech": "技术点名称", "material": "文档简称"}}
  ],
  "notes": "可选：交叉技术或不确定处说明"
}}

说明:
- 网络可多分支向下；一条资料可对应多个技术点
- 一个文档可支撑多个技术点（在 links 中写多条）
- type: paper=论文 patent=专利 news=资讯 doc=文档 standard=标准
"""
    result = chat_json(prompt)
    if "error" in result and len(result) == 1:
        return result
    result.setdefault("domain", "")
    result.setdefault("subdomain", "")
    result.setdefault("tech_points", [])
    result.setdefault("materials", [])
    result.setdefault("tech_material_links", [])
    return result


def assist_text(text: str, mode: str = "refine") -> dict[str, Any]:
    """Short-text help for manual form: translate | refine."""
    text = (text or "").strip()
    if not text:
        raise ValueError("text is empty")
    if mode == "translate":
        prompt = (
            "将下列汽车技术相关文本翻译为简洁中文。"
            "只返回 JSON：{\"text\":\"...\"}\n\n" + text[:4000]
        )
    elif mode == "refine":
        prompt = (
            "你是汽车创新技术编辑。将下列文本提炼为更清晰的技术点描述（一两句），"
            "保留关键术语。只返回 JSON：{\"text\":\"...\",\"keywords\":\"逗号分隔关键词\"}\n\n"
            + text[:4000]
        )
    else:
        raise ValueError("mode must be translate or refine")
    out = chat_json(prompt)
    if mode == "translate":
        return {"mode": mode, "text": str(out.get("text") or chat_text(prompt))}
    return {
        "mode": mode,
        "text": str(out.get("text") or ""),
        "keywords": str(out.get("keywords") or ""),
    }


def _find_by_name(store: GraphStore, tag: str, name: str) -> dict[str, Any] | None:
    for item in store.list_vertices(tag=tag, keyword=name, limit=50):
        if (item.get("props") or {}).get("name") == name:
            return item
    return None


def _find_child_by_name(store: GraphStore, tag: str, name: str, parent_vid: str) -> dict[str, Any] | None:
    """Find a node by name restricted to the given parent's subtree (domain isolation)."""
    for item in store.children(parent_vid=parent_vid, tag=tag):
        if (item.get("props") or {}).get("name") == name:
            return item
    return None


def _match_scope(store: GraphStore, domain_name: str, subdomain_name: str):
    """Resolve the parent to scope existence checks under (domain isolation)."""
    if domain_name:
        d = _find_by_name(store, "domain", domain_name)
        if d:
            if subdomain_name:
                s = _find_child_by_name(store, "subdomain", subdomain_name, d["vid"])
                if s:
                    return s
            return d
    return None


def match_extraction(payload: dict[str, Any], store: GraphStore | None = None) -> dict[str, Any]:
    """Annotate each tech/material with whether it already exists in the graph
    (reuse on commit) or will be created, scoped to the target domain/subdomain."""
    store = store or GraphStore()
    domain_name = str(payload.get("domain") or "").strip()
    subdomain_name = str(payload.get("subdomain") or "").strip()

    dom_node = _find_by_name(store, "domain", domain_name) if domain_name else None
    scope = _match_scope(store, domain_name, subdomain_name)

    tech_result = []
    for tp in payload.get("tech_points") or []:
        name = str(tp.get("name") or "").strip()
        if not name:
            continue
        found = None
        if scope:
            found = _find_child_by_name(store, "technology", name, scope["vid"])
        else:
            found = _find_by_name(store, "technology", name)
        tech_result.append({
            "name": name,
            "description": str(tp.get("description") or ""),
            "exists": bool(found),
            "vid": (found or {}).get("vid", ""),
        })

    mat_result = []
    for m in payload.get("materials") or []:
        name = str(m.get("name") or "").strip()
        if not name:
            continue
        found = _find_by_name(store, "material", name)
        mat_result.append({
            "name": name,
            "exists": bool(found),
            "vid": (found or {}).get("vid", ""),
        })

    return {
        "domain": domain_name,
        "domain_exists": bool(dom_node),
        "subdomain": subdomain_name,
        "tech_points": tech_result,
        "materials": mat_result,
    }


def _ensure(
    store: GraphStore,
    tag: str,
    name: str,
    props: dict[str, Any] | None = None,
    parent_vid: str | None = None,
) -> dict[str, Any]:
    """Ensure a vertex exists. When `parent_vid` is given (subdomain/technology),
    matching is scoped to the parent's subtree so same-named nodes in other
    domains are never reused (prevents cross-domain merge on import)."""
    if parent_vid:
        found = _find_child_by_name(store, tag, name, parent_vid)
    else:
        found = _find_by_name(store, tag, name)
    if found:
        return found
    prefix = architecture.VID_PREFIX[tag]
    base = {"name": name}
    if props:
        base.update(props)
    return store.insert_vertex(tag, make_vid(prefix), base)


def commit_extraction(payload: dict[str, Any], store: GraphStore | None = None) -> dict[str, Any]:
    """Write extract JSON into Nebula (idempotent-ish by exact name).

    subdomain 可空：最小技术点可直接挂在 domain（上一层技术簇）下。
    """
    store = store or GraphStore()
    domain_name = str(payload.get("domain") or "").strip()
    subdomain_name = str(payload.get("subdomain") or "").strip()
    if not domain_name:
        raise ValueError("domain（上一层技术簇）不能为空")

    domain = _ensure(store, "domain", domain_name, {"description": ""})
    parent = domain
    subdomain = None
    if subdomain_name:
        subdomain = _ensure(store, "subdomain", subdomain_name, {"description": ""}, parent_vid=domain["vid"])
        store.insert_edge("belongs_to", subdomain["vid"], domain["vid"], {"weight": 1.0})
        parent = subdomain

    tech_by_name: dict[str, dict[str, Any]] = {}
    created_tech: list[dict[str, Any]] = []
    for tp in payload.get("tech_points") or []:
        name = str(tp.get("name") or "").strip()
        if not name:
            continue
        node = _ensure(
            store,
            "technology",
            name,
            {
                "description": str(tp.get("description") or ""),
                "keywords": str(tp.get("keywords") or ""),
                "status": "active",
            },
            parent_vid=parent["vid"],
        )
        store.insert_edge("belongs_to", node["vid"], parent["vid"], {"weight": 1.0})
        tech_by_name[name] = node
        created_tech.append(node)

    mat_by_name: dict[str, dict[str, Any]] = {}
    created_mat: list[dict[str, Any]] = []
    for mat in payload.get("materials") or []:
        name = str(mat.get("name") or "").strip()
        if not name:
            continue
        node = _ensure(
            store,
            "material",
            name,
            {
                "material_type": str(mat.get("type") or mat.get("material_type") or "doc"),
                "title": str(mat.get("title") or name),
                "summary": str(mat.get("summary") or ""),
                "source_url": str(mat.get("source_url") or ""),
                "published_at": str(mat.get("published_at") or ""),
            },
        )
        mat_by_name[name] = node
        created_mat.append(node)

    links = 0
    for link in payload.get("tech_material_links") or []:
        tname = str(link.get("tech") or "").strip()
        mname = str(link.get("material") or "").strip()
        tech = tech_by_name.get(tname) or _find_by_name(store, "technology", tname)
        mat = mat_by_name.get(mname) or _find_by_name(store, "material", mname)
        if not tech or not mat:
            continue
        # schema: material -supports-> technology
        store.insert_edge("supports", mat["vid"], tech["vid"], {"weight": 1.0})
        links += 1

    return {
        "domain": domain,
        "subdomain": subdomain,
        "technologies": created_tech,
        "materials": created_mat,
        "supports_links": links,
    }
