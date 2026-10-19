"""Second-pass AI review before committing human-reviewed extractions into Nebula."""
from __future__ import annotations

import json
from typing import Any

from backend.services.llm import chat_json


def normalize_extraction(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize one extract-shaped payload."""
    out = {
        "domain": str(payload.get("domain") or "").strip(),
        "subdomain": str(payload.get("subdomain") or "").strip(),
        "tech_points": [],
        "materials": [],
        "tech_material_links": [],
        "notes": str(payload.get("notes") or "").strip(),
    }
    for tp in payload.get("tech_points") or []:
        name = str(tp.get("name") or "").strip()
        if not name:
            continue
        out["tech_points"].append(
            {
                "name": name,
                "description": str(tp.get("description") or "").strip(),
                "keywords": str(tp.get("keywords") or "").strip(),
            }
        )
    for mat in payload.get("materials") or []:
        name = str(mat.get("name") or "").strip()
        if not name:
            continue
        out["materials"].append(
            {
                "name": name,
                "type": str(mat.get("type") or mat.get("material_type") or "doc").strip() or "doc",
                "title": str(mat.get("title") or name).strip(),
                "summary": str(mat.get("summary") or "").strip(),
                "source_url": str(mat.get("source_url") or "").strip(),
                "published_at": str(mat.get("published_at") or "").strip(),
            }
        )
    for link in payload.get("tech_material_links") or []:
        tech = str(link.get("tech") or "").strip()
        material = str(link.get("material") or "").strip()
        if tech and material:
            out["tech_material_links"].append({"tech": tech, "material": material})
    return out


def rule_check(extraction: dict[str, Any]) -> list[dict[str, str]]:
    """Deterministic checks (no LLM). severity: error | warn."""
    issues: list[dict[str, str]] = []
    e = normalize_extraction(extraction)
    if not e["domain"]:
        issues.append(
            {
                "severity": "error",
                "field": "domain",
                "message": "缺少领域/上一层技术簇",
                "suggestion": "补上 domain，例如「线控底盘」",
            }
        )
    tech_names = [t["name"] for t in e["tech_points"]]
    mat_names = [m["name"] for m in e["materials"]]
    if not tech_names:
        issues.append(
            {
                "severity": "error",
                "field": "tech_points",
                "message": "没有技术点，图谱会缺少主体节点",
                "suggestion": "至少提炼 1 个技术点",
            }
        )
    seen_t: set[str] = set()
    for n in tech_names:
        if n in seen_t:
            issues.append(
                {
                    "severity": "warn",
                    "field": "tech_points",
                    "message": f"技术点重名：{n}",
                    "suggestion": "合并或改名区分",
                }
            )
        seen_t.add(n)
        if len(n) > 20:
            issues.append(
                {
                    "severity": "warn",
                    "field": "tech_points",
                    "message": f"技术点名称偏长：{n}",
                    "suggestion": "缩短到约 16 字以内，便于画布标注",
                }
            )
    for m in e["materials"]:
        if m["type"] not in {"paper", "patent", "news", "doc", "standard"}:
            issues.append(
                {
                    "severity": "warn",
                    "field": "materials",
                    "message": f"文档类型不规范：{m['name']} type={m['type']}",
                    "suggestion": "改为 paper|patent|news|doc|standard",
                }
            )
        if not m["summary"] and not m["title"]:
            issues.append(
                {
                    "severity": "warn",
                    "field": "materials",
                    "message": f"文档缺少摘要/标题：{m['name']}",
                    "suggestion": "补 summary，避免图谱上信息空洞",
                }
            )
    tset, mset = set(tech_names), set(mat_names)
    for link in e["tech_material_links"]:
        if link["tech"] not in tset:
            issues.append(
                {
                    "severity": "error",
                    "field": "tech_material_links",
                    "message": f"链接指向不存在的技术点：{link['tech']}",
                    "suggestion": "改名对齐 tech_points，或删掉该链接",
                }
            )
        if link["material"] not in mset:
            issues.append(
                {
                    "severity": "error",
                    "field": "tech_material_links",
                    "message": f"链接指向不存在的文档：{link['material']}",
                    "suggestion": "改名对齐 materials，或删掉该链接",
                }
            )
    if e["materials"] and not e["tech_material_links"]:
        issues.append(
            {
                "severity": "warn",
                "field": "tech_material_links",
                "message": "有文档但未挂到任何技术点",
                "suggestion": "补 tech_material_links，否则文档会孤立",
            }
        )
    return issues


def ai_review_extraction(
    extraction: dict[str, Any],
    *,
    source_meta: dict[str, Any] | None = None,
    existing_names: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """
    LLM second-pass review.

    Returns:
      approved: bool
      score: 0-100
      issues: [...]
      revised: extract payload (may equal input)
      summary: str
      rule_issues: deterministic issues
    """
    base = normalize_extraction(extraction)
    rule_issues = rule_check(base)
    existing_names = existing_names or {}
    source_meta = source_meta or {}

    prompt = f"""你是汽车创新知识图谱的「入库质检编辑」。输入已经过人工初审的结构化抽取结果。
请做第二轮严格审查，目标：入库后图谱清晰、层级合理、命名准确、文档挂接正确。

审查重点：
1. domain / subdomain / tech_points 层级是否合理（避免把文档当技术点、把系统名和技术点混层）
2. 名称是否过长、含糊、重复或与已知库内节点冲突（可建议合并到已有名称）
3. 技术点描述是否空泛；文档 type/title/summary 是否够用
4. tech_material_links 是否漏连、错连
5. 若需修正，在 revised 中给出可直接入库的完整 JSON（不要删掉合理内容）

来源信息（可参考）:
{json.dumps(source_meta, ensure_ascii=False)}

库内已有名称（避免重复建设，可建议复用）:
{json.dumps(existing_names, ensure_ascii=False)}

规则引擎已发现问题（请纳入判断，可修正后仍批准）:
{json.dumps(rule_issues, ensure_ascii=False)}

待审抽取:
{json.dumps(base, ensure_ascii=False)}

只返回 JSON:
{{
  "approved": true,
  "score": 0,
  "summary": "一两句总评",
  "issues": [
    {{"severity": "error|warn|info", "field": "字段", "message": "问题", "suggestion": "改法"}}
  ],
  "revised": {{
    "domain": "",
    "subdomain": "",
    "tech_points": [{{"name": "", "description": "", "keywords": ""}}],
    "materials": [{{"name": "", "type": "paper|patent|news|doc|standard", "title": "", "summary": "", "source_url": "", "published_at": ""}}],
    "tech_material_links": [{{"tech": "", "material": ""}}],
    "notes": ""
  }}
}}

判定：
- 存在会破坏图谱正确性的问题 → approved=false，score<70
- 仅文案优化/轻微告警 → approved=true，并在 revised 中给出优化版
- revised 必须结构完整，可直接 commit
"""
    llm_out = chat_json(prompt, timeout=180.0)
    revised = normalize_extraction(llm_out.get("revised") or base)
    # Re-run rules on revised
    post_rules = rule_check(revised)
    issues = list(llm_out.get("issues") or [])
    # merge rule issues not already covered
    seen = {(i.get("field"), i.get("message")) for i in issues if isinstance(i, dict)}
    for ri in post_rules:
        key = (ri.get("field"), ri.get("message"))
        if key not in seen:
            issues.append(ri)

    approved = bool(llm_out.get("approved"))
    if any(i.get("severity") == "error" for i in post_rules):
        approved = False
    try:
        score = int(llm_out.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    return {
        "approved": approved,
        "score": score,
        "summary": str(llm_out.get("summary") or "").strip(),
        "issues": issues,
        "revised": revised,
        "rule_issues": rule_issues,
        "original": base,
    }


def load_batch_file(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Accept:
      A) single extract payload
      B) { meta, items: [ {source, extraction}, ... ] }
    """
    if isinstance(data.get("items"), list):
        items = []
        for idx, it in enumerate(data["items"]):
            if not isinstance(it, dict):
                continue
            extraction = it.get("extraction") or it.get("payload") or it
            # if nested still looks like extract
            if "tech_points" not in extraction and "extraction" in it:
                extraction = it["extraction"]
            items.append(
                {
                    "id": str(it.get("id") or f"item_{idx+1}"),
                    "source": it.get("source") or {},
                    "extraction": normalize_extraction(extraction if isinstance(extraction, dict) else {}),
                    "human_review": it.get("human_review") or {},
                }
            )
        return items
    # single extract root
    if "domain" in data or "tech_points" in data:
        return [
            {
                "id": "item_1",
                "source": data.get("source") or {},
                "extraction": normalize_extraction(data),
                "human_review": data.get("human_review") or {},
            }
        ]
    raise ValueError("无法识别导入文件：需要 extract 结构，或 {items:[{extraction:...}]}")


def collect_existing_names(store: Any) -> dict[str, list[str]]:
    """Optional graph context for dedup hints."""
    out: dict[str, list[str]] = {"domain": [], "subdomain": [], "technology": [], "material": []}
    try:
        for tag in out:
            for n in store.list_vertices(tag=tag, limit=200):
                name = (n.get("props") or {}).get("name")
                if name:
                    out[tag].append(str(name))
    except Exception:
        pass
    return out
