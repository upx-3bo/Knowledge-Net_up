from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth import issue_token, require_write_token, verify_token
from backend.history import get_history
from backend.services.extractor import assist_text, commit_extraction, extract_from_text
from backend.services.fetch_url import FetchError, fetch_text
from backend.services.import_review import ai_review_extraction, normalize_extraction, rule_check
from backend.services.llm import LLMNotConfigured, llm_ready
from backend.store import GraphStore

router = APIRouter(prefix="/ai", tags=["ai"])


class ExtractBody(BaseModel):
    text: str = Field(min_length=1)
    title: str = ""
    translate: bool = False
    save: bool = False


class CommitBody(BaseModel):
    payload: dict


class AssistBody(BaseModel):
    text: str = Field(min_length=1)
    mode: str = Field(default="refine", description="translate | refine")


class FetchBody(BaseModel):
    url: str = Field(min_length=1)


class LoginBody(BaseModel):
    password: str = Field(min_length=1)


class ReviewBody(BaseModel):
    payload: dict
    source: dict = Field(default_factory=dict)
    rules_only: bool = False
    existing_names: dict | None = None


class MatchBody(BaseModel):
    payload: dict


def _ensure_write_token(authorization: str) -> str:
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="需要写入口令（登录后可写入）")
    return token


def _store_for(x_client_id: str, request: Request = None) -> GraphStore:
    s = GraphStore(history=get_history())
    raw = (request.headers.get("x-user-id") if request else "") or (x_client_id or "").strip()
    try:
        raw = __import__("urllib.parse", fromlist=["unquote"]).unquote(raw)
    except Exception:
        pass
    s.user = raw
    if request is not None:
        try:
            s.ip = (request.client.host if request.client else "") or ""
        except Exception:
            s.ip = ""
    return s


@router.get("/status")
def ai_status():
    return {"llm_ready": llm_ready()}


@router.post("/login")
def ai_login(body: LoginBody):
    """校验写入口令，返回可写入用的 token。"""
    token = issue_token(body.password)
    if not token:
        raise HTTPException(status_code=401, detail="写入口令错误")
    return {"token": token, "ok": True}


@router.post("/fetch")
def ai_fetch(body: FetchBody):
    """抓取网页并提取正文，供 AI 抽取/入库。不直接写库（先预览确认）。"""
    try:
        return fetch_text(body.url)
    except FetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"fetch failed: {exc}") from exc


@router.post("/extract")
def ai_extract(body: ExtractBody, authorization: str = Header(default=""), x_client_id: str = Header(default=""), request: Request = None):
    try:
        data = extract_from_text(body.text, title=body.title, translate=body.translate)
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM extract failed: {exc}") from exc

    if body.save:
        _ensure_write_token(authorization)
        try:
            store = _store_for(x_client_id, request)
            written = commit_extraction(data, store=store)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"extracted": data, "written": written}
    return {"extracted": data, "written": None}


@router.post("/match")
def ai_match(body: MatchBody):
    """标注抽取结果中每个技术点/文档是否已存在于图谱（可复用/将新建）。"""
    try:
        return match_extraction(body.payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"match failed: {exc}") from exc


@router.post("/commit")
def ai_commit(body: CommitBody, _token: str = Depends(require_write_token), x_client_id: str = Header(default=""), request: Request = None):
    try:
        store = _store_for(x_client_id, request)
        return commit_extraction(body.payload, store=store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/assist")
def ai_assist(body: AssistBody):
    try:
        return assist_text(body.text, mode=body.mode)
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM assist failed: {exc}") from exc


@router.post("/review-import")
def ai_review_import(body: ReviewBody):
    """Second-pass QA on human-reviewed extract JSON (does not write graph)."""
    payload = normalize_extraction(body.payload)
    if body.rules_only:
        issues = rule_check(payload)
        approved = not any(i.get("severity") == "error" for i in issues)
        return {
            "approved": approved,
            "score": 100 if approved else 40,
            "summary": "仅规则检查",
            "issues": issues,
            "revised": payload,
            "original": payload,
        }
    try:
        return ai_review_extraction(
            payload,
            source_meta=body.source or {},
            existing_names=body.existing_names or {},
        )
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM review failed: {exc}") from exc
