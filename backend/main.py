import json
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi_offline import FastAPIOffline

from backend.routers import knowledge, search, classification, graph_viz, about
from backend.services import intelligence, extractor

app = FastAPIOffline(
    title="汽车创新技术库 · AI 知识图谱平台",
    description="""
基于图数据库的汽车创新技术知识图谱平台。

## 主要功能
- **图谱可视化** (`/graph`)：力导向网络图，拖拽/缩放/编辑/连线/折叠
- **AI 提取** (`/api/extract`)：粘贴技术资讯，LLM 自动提取知识入库
- **智能搜索** (`/search/*`)：关键词搜索、路径查找、全文检索
- **知识管理** (`/knowledge/*`)：技术/标准/专利/资源/文档 CRUD
- **工具介绍** (`/about`)：平台功能介绍

## 访问入口
| 路径 | 说明 |
|------|------|
| `/graph` | 图谱可视化页面（主工作台） |
| `/about` | 工具介绍页 |
| `/docs` | API 文档（Swagger，可交互） |
| `/redoc` | API 文档（ReDoc，适合阅读） |
| `/stats` | 数据库统计 |
""",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knowledge.router)
app.include_router(search.router)
app.include_router(classification.router)
app.include_router(graph_viz.router)
app.include_router(about.router)


@app.get("/", summary="根路径（重定向到 /about）")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/about")


@app.get("/health", summary="健康检查")
def health():
    return {"status": "ok"}


@app.post("/intelligence/update", summary="触发情报自动收集与更新")
async def trigger_intelligence(keywords: str = "汽车创新技术 电池 SiC 自动驾驶"):
    result = await intelligence.run_intelligence_update(keywords)
    return result


# ===== AI 提取管道 =====
class ExtractRequest(BaseModel):
    text: str
    title: str = ""
    save: bool = True  # 是否直接写入数据库
    translate: bool = False  # 是否翻译为中文


@app.post("/api/extract", summary="AI 提取知识（从文本提取技术点/支撑材料并入库）")
async def api_extract(req: ExtractRequest):
    """从文本中 AI 提取结构化知识，可选写入数据库。translate=True 时翻译为中文。"""
    extracted = extractor.extract_knowledge_from_text(req.text, req.title, req.translate)
    if "error" in extracted:
        return extracted
    saved = None
    if req.save and "domain" in extracted:
        try:
            saved = extractor.save_extracted_knowledge(extracted)
        except Exception as e:
            saved = {"error": str(e)}
    return {"extracted": extracted, "saved": saved}


class RelateRequest(BaseModel):
    vid: str


@app.post("/api/relate", summary="AI 分析节点并自动建立与现有节点的关联")
async def api_relate(req: RelateRequest):
    """AI 读取指定节点的名称/备注/层级，在知识库中找到相关节点并自动建立连线。"""
    kb = get_store()
    node = kb.get_vertex(req.vid)
    if not node:
        return {"error": "节点不存在"}
    props = node.get("props", {})
    label = props.get("name", "")
    level = props.get("level", 2)
    notes = kb.get_notes(req.vid) if hasattr(kb, "get_notes") else {"remarks": "", "links": ""}
    remarks = notes.get("remarks", "")
    if not LLM_API_KEY or LLM_API_KEY == "your_deepseek_api_key_here":
        return {"error": "LLM_API_KEY 未配置"}
    import httpx
    client = OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_API_URL,
        http_client=httpx.Client(verify=False, timeout=120),
    )
    # 获取所有节点的名称和 vid（排除自身），供 LLM 选择
    all_nodes = kb.query_vertices(limit=1000)
    candidates = []
    for n in all_nodes:
        if n["vid"] == req.vid:
            continue
        nname = n["props"].get("name") or n["props"].get("title") or n["vid"]
        nlevel = n["props"].get("level", 0)
        candidates.append({"vid": n["vid"], "name": nname, "level": nlevel})
    candidate_str = "\n".join([f"{c['vid']} | {c['name']} | L{c['level']}" for c in candidates[:300]])
    prompt = f"""你是汽车技术知识图谱专家。现在有一个新节点，请分析它应该与哪些现有节点建立关联。

新节点信息：
- 名称: {label}
- 层级: L{level}
- 备注: {remarks[:500]}

现有节点列表（vid | 名称 | 层级）：
{candidate_str}

请输出 JSON，推荐建立关联的节点（最多 5 个）：
{{
  "relations": [
    {{"vid": "目标节点vid", "edge_type": "belongs_to|supports", "reason": "关联理由"}}
  ]
}}

规则：
- 如果新节点是 L3 技术点，优先 belongs_to 到 L2 子领域
- 如果新节点是 L0 支撑材料，优先 supports 到 L3 技术点
- 如果新节点是 L2 子领域，优先 belongs_to 到 L1 领域
- 只推荐确实相关的节点，不要强行关联
"""
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
    except Exception as e:
        return {"error": f"AI 分析失败：{type(e).__name__}: {e}"}
    # 建立连线
    created = []
    for rel in result.get("relations", []):
        target_vid = rel.get("vid", "")
        edge_type = rel.get("edge_type", "belongs_to")
        reason = rel.get("reason", "")
        if not target_vid:
            continue
        target = kb.get_vertex(target_vid)
        if not target:
            continue
        # 确定边方向：子→父
        target_level = target["props"].get("level", 0)
        if edge_type == "supports":
            # supports: L0 → L3
            if level <= 0 and target_level >= 1:
                src, dst = req.vid, target_vid
            elif target_level <= 0 and level >= 1:
                src, dst = target_vid, req.vid
            else:
                src, dst = req.vid, target_vid
        else:
            # belongs_to: 子→父（层级数字大的指向层级数字小的）
            if level > target_level:
                src, dst = req.vid, target_vid
            else:
                src, dst = target_vid, req.vid
        try:
            kb.insert_edge(edge_type, src, dst, {"remark": reason})
            created.append({"vid": target_vid, "name": target["props"].get("name", ""), "edge_type": edge_type, "reason": reason})
        except Exception:
            pass
    return {"ok": True, "node": label, "relations_created": created}


@app.get("/api/extract/preview", summary="AI 提取预览（只提取不入库）")
async def api_extract_preview(text: str, title: str = ""):
    """预览模式：只提取不写入。"""
    return extractor.extract_knowledge_from_text(text, title)


@app.get("/stats", summary="数据库统计（各类型节点数量）")
def stats():
    from backend.services.graph_store import get_store
    kb = get_store()
    return {
        "technologies": kb.get_count("technology"),
        "categories": kb.get_count("category"),
        "standards": kb.get_count("standard"),
        "patents": kb.get_count("patent"),
        "resources": kb.get_count("resource"),
        "components": kb.get_count("component"),
        "documents": kb.get_count("document"),
    }
