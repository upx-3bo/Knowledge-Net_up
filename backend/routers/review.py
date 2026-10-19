from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from backend.auth import require_write_token
from backend.history import get_history
from backend.services import review as rv
from backend.store import GraphStore

router = APIRouter(prefix="/review", tags=["review"])


def _store() -> GraphStore:
    return GraphStore(history=get_history())


@router.get("/pending")
def review_pending(limit: int = 500):
    """待校核清单（自基线以来未审阅/未撤销的操作）。"""
    return rv.pending(_store(), get_history(), limit=limit)


class AcceptBody(BaseModel):
    up_to_op_id: int | None = None


@router.post("/accept")
def review_accept(body: AcceptBody, _token: str = Depends(require_write_token)):
    """接受（推进校核基线）。不留 body = 接受全部待校核。"""
    hist = get_history()
    if body.up_to_op_id:
        hist.set_checkpoint(min(int(body.up_to_op_id), hist.max_done_id()))
    else:
        hist.set_checkpoint(hist.max_done_id())
    return rv.pending(_store(), hist)


class UndoBody(BaseModel):
    op_ids: list[int]


@router.post("/undo-ops")
def review_undo_ops(body: UndoBody, _token: str = Depends(require_write_token)):
    """按操作 id 逆向撤销指定待校核项。已接受（id<基线）的不会处理。"""
    if not body.op_ids:
        raise HTTPException(status_code=400, detail="op_ids 不能为空")
    hist = get_history()
    cp = hist.get_checkpoint()
    store = _store()
    rows = hist.pending_rows(limit=10000)
    by_id = {r["id"]: r for r in rows}
    results: list[dict] = []
    for op_id in sorted(set(body.op_ids), reverse=True):
        op = by_id.get(op_id)
        if not op:
            results.append({"id": op_id, "ok": False, "reason": "不在待校核范围内（已接受或已撤销）"})
            continue
        results.append(rv.revert(store, hist, op))
    return {"results": results, "pending": rv.pending(_store(), hist)}
