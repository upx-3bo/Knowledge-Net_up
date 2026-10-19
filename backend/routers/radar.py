from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from backend.radar.collector import get_radar

router = APIRouter(prefix="/radar", tags=["radar"])


@router.get("/status")
def radar_status():
    return {**get_radar().status(), "counts": get_radar().item_count()}


@router.post("/sync")
def radar_sync():
    return get_radar().sync_sources()


@router.get("/sources")
def radar_sources():
    return {"items": get_radar().list_sources()}


@router.post("/sources/{source_id}/toggle")
def radar_toggle(source_id: str, enabled: bool = True):
    return get_radar().set_enabled(source_id, enabled)


@router.post("/probe")
def radar_probe():
    return get_radar().probe()


@router.post("/run")
def radar_run():
    return get_radar().start_async()


@router.get("/items")
def radar_items(
    source_id: str = Query(default=""),
    keyword: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=1000),
):
    return {"items": get_radar().list_items(source_id=source_id, keyword=keyword, limit=limit)}


@router.get("/export")
def radar_export(fmt: str = "json"):
    return PlainTextResponse(get_radar().export(fmt=fmt), media_type="application/json" if fmt == "json" else "text/csv")


@router.post("/clear")
def radar_clear():
    return get_radar().clear_all()
