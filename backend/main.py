import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import ai, collect, export, graph, imports, radar
from backend.store import GraphStore

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="AI4KnowledgeNet",
    description="汽车创新设计知识库 · NebulaGraph（技术点网络）",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graph.router)
app.include_router(ai.router)
app.include_router(export.router)
app.include_router(imports.router)
app.include_router(collect.router)
app.include_router(radar.router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
# 公开文档（功能清单、演进与维护工作流等 html/md），供所有用户网页访问
app.mount("/wiki", StaticFiles(directory=Path(__file__).resolve().parent.parent / "docs"), name="wiki")


@app.get("/radar")
def radar_home():
    return FileResponse(FRONTEND_DIR / "radar.html")


def _start_collector_scheduler() -> None:
    """固定周期自动采集（周期小时数由 COLLECT_INTERVAL_HOURS 控制，默认 24h）。"""
    import threading
    import time

    from backend.services.collector import get_collector

    if os.getenv("COLLECT_ENABLED", "1") != "1":
        return
    interval_h = float(os.getenv("COLLECT_INTERVAL_HOURS", "24") or 24)
    if interval_h <= 0:
        return

    def loop():
        while True:
            time.sleep(interval_h * 3600)
            try:
                get_collector().run()
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=loop, daemon=True).start()


@app.on_event("startup")
def _startup() -> None:
    try:
        from backend.radar.collector import get_radar
        get_radar().sync_sources()
    except Exception:  # noqa: BLE001
        pass
    _start_collector_scheduler()


@app.get("/")
def ui_home():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health():
    try:
        return GraphStore().ping()
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.get("/stats")
def stats():
    try:
        return GraphStore().stats()
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
