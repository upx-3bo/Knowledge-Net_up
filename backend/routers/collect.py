from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from backend.auth import require_write_token
from backend.services.collector import get_collector

router = APIRouter(prefix="/collect", tags=["collect"])


@router.get("/status")
def collect_status():
    return get_collector().status()


@router.get("/candidates")
def collect_candidates(
    status: str = Query(default="pending"),
    limit: int = Query(default=200, ge=1, le=500),
):
    return {"items": get_collector().list_candidates(status=status, limit=limit)}


@router.post("/candidates/{cand_id}/commit")
def commit_candidate(
    cand_id: int,
    _token: str = Depends(require_write_token),
    x_client_id: str = Header(default=""),
):
    try:
        return get_collector().commit_candidate(cand_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"入库失败: {exc}") from exc


@router.post("/candidates/{cand_id}/reject")
def reject_candidate(
    cand_id: int,
    _token: str = Depends(require_write_token),
):
    return get_collector().reject_candidate(cand_id)


@router.post("/run")
def run_collect(_token: str = Depends(require_write_token)):
    """手动触发一次后台采集（立即返回，轮询 /collect/status 看进度）。"""
    return get_collector().start_async()
