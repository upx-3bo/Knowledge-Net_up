from __future__ import annotations

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request

from backend.auth import verify_token
from backend.history import get_history
from backend.services import import_knowledge as imp
from backend.store import GraphStore

router = APIRouter(prefix="/import", tags=["import"])


def _store(x_client_id: str, request: Request) -> GraphStore:
    s = GraphStore(history=get_history())
    raw = (request.headers.get("x-user-id") or "").strip() or x_client_id or ""
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


@router.get("/template")
def import_template():
    """下载 6 层架构批量入库模板（自说明 + 可导入 JSON）。"""
    from fastapi.responses import JSONResponse

    data = imp.build_template()
    return JSONResponse(
        data,
        headers={
            "Content-Disposition": 'attachment; filename="knowledge_import_template.json"'
        },
    )


@router.post("/knowledge")
def import_knowledge(
    body: dict = Body(..., description="6 层导出同构文件（tree/nodes/edges）"),
    dry_run: bool = Query(False, description="true=只校验出计划，不写库"),
    authorization: str = Header(default=""),
    x_client_id: str = Header(default=""),
    request: Request = None,
):
    if not dry_run:
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not token or not verify_token(token):
            raise HTTPException(status_code=401, detail="需要写入口令（登录后可写入）")
    try:
        importer = imp.Importer(_store(x_client_id, request))
        plan = importer.plan(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"import plan failed: {exc}") from exc

    if dry_run:
        return {"dry_run": True, **plan}

    if not plan.get("valid"):
        return {
            "ok": False,
            "message": "存在校验 error，拒绝写入",
            "summary": plan.get("summary", {}),
            "issues": plan.get("issues", []),
        }
    result = importer.apply(plan)
    result["issues"] = plan.get("issues", [])
    return result
