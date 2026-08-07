"""
情报收集管道 — 从外部资讯源抓取技术情报，AI 分析后写入知识图谱。
适配新层级模型：domain/subdomain/tech_point/material + belongs_to/supports
"""
import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from backend.services.graph_store import get_store
from backend.services.extractor import save_extracted_knowledge

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

kb = get_store()


async def fetch_news(keywords: str) -> list:
    """从资讯源抓取新闻（需配置 NEWS_API_KEY，否则返回空）。"""
    news_key = os.getenv("NEWS_API_KEY", "")
    if not news_key:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://newsapi.org/v2/everything",
                params={"q": keywords, "pageSize": 5, "language": "zh", "apiKey": news_key},
            )
            if resp.status_code == 200:
                return resp.json().get("articles", [])
    except Exception:
        pass
    return []


def analyze_intelligence(text: str, title: str) -> dict:
    """调用 LLM 分析情报，输出可直接入库的结构化 JSON。"""
    if not LLM_API_KEY or LLM_API_KEY == "your_deepseek_api_key_here":
        return {"error": "LLM_API_KEY 未配置"}

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
    prompt = f"""你是汽车技术情报分析专家。分析以下情报并输出结构化 JSON，用于更新汽车创新技术知识图谱。

情报标题: {title}
情报内容:
{text[:4000]}

请输出 JSON（只返回 JSON）:
{{
  "domain": "顶层领域（≤8字）",
  "subdomain": "子领域（≤8字）",
  "tech_points": [
    {{"name": "技术点（≤8字）", "description": "一句话描述"}}
  ],
  "materials": [
    {{"name": "材料简称（≤14字）", "type": "paper|patent|news|doc", "title": "完整标题", "summary": "摘要100字"}}
  ],
  "tech_material_links": [
    {{"tech": "技术点名称", "material": "材料简称"}}
  ],
  "summary": "情报摘要50字",
  "impact": "对汽车创新技术的影响"
}}
"""
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"error": "LLM 返回解析失败", "raw": resp.choices[0].message.content}


async def run_intelligence_update(keywords: str) -> dict:
    """从资讯源抓取 → AI 分析 → 入库。"""
    news_items = await fetch_news(keywords)

    if not news_items:
        return {
            "status": "no_source",
            "message": "未配置 NEWS_API_KEY 或未抓取到资讯。可改为直接调用 POST /api/extract 传入文本。",
            "keywords": keywords,
        }

    results = []
    for item in news_items[:5]:
        title = item.get("title", "")
        text = item.get("description") or item.get("content") or ""
        analysis = analyze_intelligence(text, title)
        results.append({"title": title, "analysis": analysis})

        # 入库
        if "domain" in analysis:
            try:
                save_result = save_extracted_knowledge(analysis)
                results[-1]["saved"] = save_result
            except Exception as e:
                results[-1]["save_error"] = str(e)

    return {"total": len(results), "keywords": keywords, "items": results}
