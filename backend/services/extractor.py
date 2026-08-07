"""
AI 知识提取管道 — 从技术资讯文本提取结构化知识并写入图数据库。
适配新层级模型：
  - domain (L1, tag="domain")
  - subdomain (L2, tag="subdomain")
  - tech_point (L3, tag="technology")
  - material (L0, tag="material")
  - 边: belongs_to (子→父), supports (tech_point→material)
"""
import json
import os
import uuid
from dotenv import load_dotenv
from openai import OpenAI
from backend.services.graph_store import get_store

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

kb = get_store()

KNOWN_DOMAINS = [
    "轻量化材料", "动力电池", "机器人与具身智能", "感知与自动驾驶",
    "制造工艺", "智能座舱", "车身与涂层", "热管理",
    "电驱与功率电子", "底盘与悬架", "安全技术", "软件与E/E架构",
]


def _call_llm(prompt: str) -> dict:
    if not LLM_API_KEY or LLM_API_KEY == "your_deepseek_api_key_here":
        return {"error": "LLM_API_KEY 未配置，请在 .env 文件中填入你的 API Key"}
    import httpx
    client = OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_API_URL,
        http_client=httpx.Client(verify=False, timeout=120),
    )
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
    except Exception as e:
        return {"error": f"LLM 调用失败：{type(e).__name__}: {e}"}
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"error": "LLM 返回解析失败", "raw": resp.choices[0].message.content}


def extract_knowledge_from_text(text: str, title: str = "", translate: bool = False) -> dict:
    """调用 LLM 从技术资讯文本中提取结构化知识。translate=True 时将结果翻译为中文。"""
    domains_hint = "、".join(KNOWN_DOMAINS)
    translate_instr = "\n重要：请将所有提取结果（技术点名称、材料名称、描述等）翻译为中文。" if translate else ""
    prompt = f"""你是汽车工程领域的知识抽取专家。从以下技术资讯中抽取结构化知识，输出 JSON。{translate_instr}

已知顶层领域（尽量复用，如不匹配可新建）: {domains_hint}

资讯标题: {title}
资讯内容:
{text[:8000]}

请输出以下 JSON 格式（只返回 JSON，不要其他文字）:
{{
  "domain": "顶层领域名称（≤8字，优先从已知领域中选择）",
  "subdomain": "子领域名称（≤8字）",
  "tech_points": [
    {{"name": "技术点名称（≤8字）", "description": "一句话描述"}}
  ],
  "materials": [
    {{"name": "支撑材料简称（≤14字，从内容提炼有意义名称，非日期数字）", "type": "paper|patent|news|doc", "title": "原始完整标题", "summary": "内容摘要（100字以内）"}}
  ],
  "tech_material_links": [
    {{"tech": "技术点名称", "material": "支撑材料简称"}}
  ]
}}

说明:
- type 含义: paper=论文, patent=专利, news=新闻资讯, doc=公司技术文件
- tech_material_links 表示哪个技术点由哪个支撑材料支撑
- 如果一条资讯涉及多个技术点，都在 tech_points 中列出
"""
    return _call_llm(prompt)


def _find_node_by_name(tag: str, name: str):
    """按 name 在指定 tag 中查找节点，返回 dict 或 None。"""
    results = kb.query_vertices(tag=tag, keyword=name, limit=50)
    for r in results:
        if r["props"].get("name") == name:
            return r
    return None


def _create_node(tag: str, name: str, level: int, extra_props: dict = None) -> str:
    """创建节点，返回 vid。"""
    vid = "node_" + uuid.uuid4().hex[:10]
    props = {"name": name, "level": level}
    if extra_props:
        props.update(extra_props)
    kb.insert_vertex(tag, vid, props)
    return vid


def _find_or_create(tag: str, name: str, level: int, extra_props: dict = None) -> str:
    """查找或创建节点，返回 vid。"""
    existing = _find_node_by_name(tag, name)
    if existing:
        return existing["vid"]
    return _create_node(tag, name, level, extra_props)


def _find_or_create_edge(edge_type: str, src_vid: str, dst_vid: str, props: dict = None):
    """查找或创建边（避免重复）。"""
    edges = kb.query_edges(src_vid=src_vid, edge_type=edge_type)
    for e in edges:
        if e["src_vid"] == src_vid and e["dst_vid"] == dst_vid:
            return e["id"]
    return kb.insert_edge(edge_type, src_vid, dst_vid, props)


def save_extracted_knowledge(data: dict) -> dict:
    """将 LLM 提取的结构化知识写入图数据库。"""
    results = {"domain": "", "subdomain": "", "tech_points": [], "materials": [], "edges": [], "errors": []}

    domain_name = data.get("domain", "").strip()
    subdomain_name = data.get("subdomain", "").strip()
    tech_points = data.get("tech_points", [])
    materials = data.get("materials", [])
    links = data.get("tech_material_links", [])

    if not domain_name:
        results["errors"].append("缺少 domain")
        return results

    # 1. 领域 (L1)
    domain_vid = _find_or_create("domain", domain_name, 1)
    results["domain"] = domain_name

    # 2. 子领域 (L2) → belongs_to domain
    if subdomain_name:
        sub_vid = _find_or_create("subdomain", subdomain_name, 2)
        _find_or_create_edge("belongs_to", sub_vid, domain_vid)
        results["subdomain"] = subdomain_name
    else:
        sub_vid = None

    # 3. 技术点 (L3) → belongs_to subdomain
    tech_vid_map = {}  # name -> vid
    for tp in tech_points:
        tp_name = tp.get("name", "").strip()
        if not tp_name:
            continue
        tp_vid = _find_or_create("technology", tp_name, 3, {"description": tp.get("description", "")})
        tech_vid_map[tp_name] = tp_vid
        if sub_vid:
            _find_or_create_edge("belongs_to", tp_vid, sub_vid)
        results["tech_points"].append(tp_name)

    # 4. 支撑材料 (L0)
    mat_vid_map = {}  # name -> vid
    for mat in materials:
        mat_name = mat.get("name", "").strip()
        if not mat_name:
            continue
        mat_type = mat.get("type", "news").strip()
        mat_vid = _find_or_create("material", mat_name, 0, {
            "material_type": mat_type,
            "title": mat.get("title", ""),
            "summary": mat.get("summary", ""),
        })
        mat_vid_map[mat_name] = mat_vid
        # 写入备注（完整标题+摘要）
        if hasattr(kb, "update_notes"):
            remarks = f"{mat.get('title', '')}\n{mat.get('summary', '')}".strip()
            kb.update_notes(mat_vid, remarks, "")
        results["materials"].append(f"[{mat_type}] {mat_name}")

    # 5. 支撑材料 → 技术点 (supports 边，方向：material→tech_point)
    for link in links:
        tech_name = link.get("tech", "").strip()
        mat_name = link.get("material", "").strip()
        tech_vid = tech_vid_map.get(tech_name)
        mat_vid = mat_vid_map.get(mat_name)
        if tech_vid and mat_vid:
            _find_or_create_edge("supports", mat_vid, tech_vid)
            results["edges"].append(f"{mat_name} -[supports]-> {tech_name}")

    # 如果没有显式 link 但只有一个技术点和一个材料，自动连接
    if not links and len(tech_vid_map) == 1 and len(mat_vid_map) == 1:
        tech_vid = list(tech_vid_map.values())[0]
        mat_vid = list(mat_vid_map.values())[0]
        _find_or_create_edge("supports", mat_vid, tech_vid)
        results["edges"].append("自动关联: material→tech")

    return results
