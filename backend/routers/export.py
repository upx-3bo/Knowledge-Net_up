from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.history import get_history
from backend.services import export_knowledge as exp
from backend.store import GraphStore

router = APIRouter(prefix="/export", tags=["export"])


def _store() -> GraphStore:
    return GraphStore(history=get_history())


@router.get("/knowledge")
def export_knowledge(
    root: str = Query(..., description="根节点 vid，如 veh_chassis 或某领域 vid"),
    from_level: str = Query("vehicle", description="导出包含的最低层"),
    to_level: str = Query("technology", description="导出包含的最高层"),
    fmt: str = Query("json", description="json | md"),
):
    try:
        data = exp.export_data(_store(), root, from_level, to_level)
    except exp.ExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"export failed: {exc}") from exc

    if fmt == "md":
        from fastapi.responses import PlainTextResponse

        filename = f"knowledge_{root}_{from_level}_{to_level}.md"
        return PlainTextResponse(
            exp.to_markdown(data),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return data
