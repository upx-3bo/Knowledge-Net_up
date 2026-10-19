from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request

from backend import architecture
from backend.auth import require_write_token
from backend.history import get_history
from backend.models import EdgeCreate, EdgeDelete, VertexCreate, VertexUpdate
from backend.store import EDGES, TAGS, GraphStore, make_vid

router = APIRouter(tags=["graph"])


def _store() -> GraphStore:
    return GraphStore(history=get_history())


def _store_for(x_client_id: str = "", request: Request = None, user_id: str = "") -> GraphStore:
    s = GraphStore(history=get_history())
    # 编辑者身份：优先登录时登记的 X-User-Id；其次请求带的 client id；都没有则为空
    uid = (user_id or "").strip()
    if not uid and request is not None:
        uid = (request.headers.get("x-user-id") or "").strip()
        try:
            uid = __import__("urllib.parse", fromlist=["unquote"]).unquote(uid)
        except Exception:
            pass
    if not uid:
        uid = (x_client_id or "").strip()
    s.user = uid
    if request is not None:
        try:
            s.ip = (request.client.host if request.client else "") or ""
        except Exception:
            s.ip = ""
    return s


@router.get("/vertices")
def list_vertices(
    tag: str | None = Query(default=None, description=f"可选: {', '.join(TAGS)}"),
    keyword: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=500),
):
    try:
        return {"items": _store().list_vertices(tag=tag, keyword=keyword, limit=limit)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/vertices/{vid}")
def get_vertex(vid: str):
    node = _store().get_vertex(vid)
    if not node:
        raise HTTPException(status_code=404, detail="vertex not found")
    return node


@router.get("/vertices/{vid}/detail")
def get_vertex_detail(vid: str):
    data = _store().vertex_detail(vid)
    if not data:
        raise HTTPException(status_code=404, detail="vertex not found")
    return data


@router.get("/vertices/{vid}/cascade")
def get_cascade(vid: str):
    """级联删除候选集：本节点 + 下层只归本节点管控的全部节点。

    返回 { root, nodes: [...], count }，供前端删除前预览/确认。
    """
    return _store().cascade_owned(vid)


@router.post("/vertices", status_code=201)
def create_vertex(body: VertexCreate, _token: str = Depends(require_write_token), x_client_id: str = Header(default=""), request: Request = None):
    vid = body.vid or make_vid(architecture.VID_PREFIX[body.tag])
    store = _store_for(x_client_id, request)
    try:
        return store.insert_vertex(body.tag, vid, body.props)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/vertices/{vid}")
def update_vertex(vid: str, body: VertexUpdate, _token: str = Depends(require_write_token), x_client_id: str = Header(default=""), request: Request = None):
    store = _store_for(x_client_id, request)
    try:
        node = store.update_vertex(vid, body.props)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not node:
        raise HTTPException(status_code=404, detail="vertex not found")
    return node


@router.delete("/vertices/{vid}")
def delete_vertex(vid: str, _token: str = Depends(require_write_token), x_client_id: str = Header(default=""), request: Request = None):
    ok = _store_for(x_client_id, request).delete_vertex(vid)
    if not ok:
        raise HTTPException(status_code=404, detail="vertex not found")
    return {"deleted": True, "vid": vid}


@router.post("/vertices/batch-delete")
def batch_delete_vertices(
    body: dict = Body(..., description='{"vids": [...]}'),
    _token: str = Depends(require_write_token),
    x_client_id: str = Header(default=""),
    request: Request = None,
):
    """一次请求内删除多个节点 → 归为同一个 batch，可被「撤回」整体恢复。

    子先父后删除，减少中途失败留下孤儿节点的概率（与前端级联删除一致）。
    """
    from pydantic import BaseModel, Field

    class BatchDeleteBody(BaseModel):
        vids: list[str] = Field(default_factory=list)

    parsed = BatchDeleteBody(**body)
    vids = [v.strip() for v in parsed.vids if v and v.strip()]
    if not vids:
        raise HTTPException(status_code=400, detail="vids 为空")

    store = _store_for(x_client_id, request)
    deleted, missing, failures = [], [], []
    # 子先父后：vids 顺序由调用方给定（前端已按 cascade 反序），这里再保险地先删叶子
    for vid in vids:
        try:
            if store.delete_vertex(vid):
                deleted.append(vid)
            else:
                missing.append(vid)
        except Exception as exc:  # noqa: BLE001
            failures.append({"vid": vid, "error": str(exc)})
    return {"deleted": deleted, "missing": missing, "failures": failures,
            "batch": store.batch}


@router.post("/edges", status_code=201)
def create_edge(body: EdgeCreate, _token: str = Depends(require_write_token), x_client_id: str = Header(default=""), request: Request = None):
    store = _store_for(x_client_id, request)
    try:
        return store.insert_edge(body.edge_type, body.src_vid, body.dst_vid, body.props)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/edges")
def delete_edge(body: EdgeDelete, _token: str = Depends(require_write_token), x_client_id: str = Header(default=""), request: Request = None):
    ok = _store_for(x_client_id, request).delete_edge(body.edge_type, body.src_vid, body.dst_vid)
    if not ok:
        raise HTTPException(status_code=404, detail="edge not found or delete failed")
    return {"deleted": True, **body.model_dump()}


@router.get("/overview")
def overview(
    limit_nodes: int = Query(default=3000, ge=1, le=10000),
    limit_edges: int = Query(default=8000, ge=1, le=20000),
    layer_cap: str = Query(default="", description="可选：只返回该层及上层（vehicle/domain/subdomain/module/technology/material），留空=全部"),
):
    try:
        return _store().overview(
            limit_nodes=limit_nodes,
            limit_edges=limit_edges,
            layer_cap=layer_cap or "",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/subgraph/{vid}")
def subgraph(vid: str, depth: int = Query(default=1, ge=1, le=3)):
    data = _store().neighbors(vid, depth=depth)
    if not data["nodes"]:
        raise HTTPException(status_code=404, detail="vertex not found")
    return data


@router.get("/path")
def shortest_path(
    src: str = Query(..., description="起点 vid"),
    dst: str = Query(..., description="终点 vid"),
):
    paths = _store().find_path(src, dst)
    best = paths[0] if paths else None
    return {
        "src": src,
        "dst": dst,
        "found": bool(best and best.get("nodes")),
        "path": best,
        "paths": paths,
    }


@router.get("/history")
def history_list(limit: int = Query(default=30, ge=1, le=200)):
    hist = get_history()
    return {"items": hist.list(limit=limit)}


@router.get("/activity/recent")
def activity_recent(limit: int = Query(default=10, ge=1, le=50)):
    """最近修改记录：轻量只读，纯读 history.db，不含段落审阅语义。"""
    items = []
    for op in get_history().recent(limit=limit):
        p = op.get("payload") or {}
        label, vids = _describe_op(op.get("action", ""), p)
        items.append({
            "id": op["id"],
            "time": op["time"],
            "action": op["action"],
            "user": op.get("user", ""),
            "ip": op.get("ip", ""),
            "batch": op.get("batch", ""),
            "label": label,
            "vids": vids,
        })
    return {"items": items}


@router.get("/activity/pending")
def activity_pending(limit: int = Query(default=2000, ge=1, le=5000)):
    """未审阅变更：checkpoint 之后、未撤销的全部操作，按批次归并成组。

    返回:
      checkpoint: 当前已审阅到的 op id
      groups: [{ id, batch, user, ip, time, ops: [...], vids: [新增/修改节点], label }]，时间正序
      items_count / groups_count 便于前端判断有无更新
    """
    hist = get_history()
    rows = hist.pending_rows(limit=limit)
    cp = hist.get_checkpoint()
    groups = []
    grouped = {}  # batch -> group
    order = []     # 保持批次首次出现顺序（时间正序）
    for op in rows:
        batch = op.get("batch") or f"op-{op['id']}"
        if batch not in grouped:
            grouped[batch] = {
                "id": batch,
                "batch": batch,
                "user": op.get("user", ""),
                "ip": op.get("ip", ""),
                "time_start": op["time"],
                "time_end": op["time"],
                "ops": [],
                "vids": [],
                "label": "",
            }
            order.append(batch)
        g = grouped[batch]
        g["time_start"] = min(g["time_start"], op["time"])
        g["time_end"] = max(g["time_end"], op["time"])
        g["ops"].append({"id": op["id"], "time": op["time"], "action": op["action"]})
        p = op.get("payload") or {}
        label, vids = _describe_op(op.get("action", ""), p)
        g["ops"][-1]["label"] = label
        g["vids"].extend(vids)
        if len(g["ops"]) == 1:
            g["label"] = label
    for b in order:
        g = grouped[b]
        n = len(g["ops"])
        if n > 1:
            # 人类可读的批量摘要：按 tag 统计新增，列出前几个名称
            tag_cnt: dict[str, int] = {}
            names: list[str] = []
            for o in g["ops"]:
                if o["action"] == "insert_vertex":
                    tag_cnt["vertex"] = tag_cnt.get("vertex", 0) + 1
                elif o["action"] == "insert_edge":
                    tag_cnt["edge"] = tag_cnt.get("edge", 0) + 1
                elif o["action"] == "delete_vertex":
                    tag_cnt["delete"] = tag_cnt.get("delete", 0) + 1
                nm = (o.get("label") or "").replace("新增节点「", "").replace("新增「", "")
                if "新增" in (o.get("label") or ""):
                    nm2 = nm.split("」", 1)[0]
                    if nm2 and len(names) < 8:
                        names.append(nm2)
            parts = []
            if tag_cnt.get("vertex"):
                parts.append(f"新增节点×{tag_cnt['vertex']}")
            if tag_cnt.get("edge"):
                parts.append(f"新增关联×{tag_cnt['edge']}")
            if tag_cnt.get("delete"):
                parts.append(f"删除×{tag_cnt['delete']}")
            label = "批量："
            if parts:
                label += "、".join(parts)
            if names:
                label += "（" + "、".join(names) + "…）"
            g["label"] = label
        g["vids"] = sorted(set(v for v in g["vids"] if v))
        g["max_op_id"] = max(o["id"] for o in g["ops"])
        groups.append(g)
    return {
        "checkpoint": cp,
        "groups_count": len(groups),
        "items_count": len(rows),
        "groups": groups,
    }


@router.post("/activity/reviewed")
def activity_reviewed(
    _token: str = Depends(require_write_token),
    until: int | None = Body(default=None, embed=True, description="确认审阅到哪个 op id（含该 id）。缺省=全部推进到最新。"),
):
    """把审阅基线推进到指定 op id（或最新）。

    - 不带 until：一次确认全部待审变更。
    - 带 until：只确认到该 op id 为止（用于分批审阅）。
    """
    hist = get_history()
    if until is not None:
        # 校验 not 超过当前最大已操作 id
        top = hist.max_done_id()
        if until < 1 or until > top:
            return {"checkpoint": hist.get_checkpoint(), "reviewed_until": hist.get_checkpoint(),
                    "ok": False, "reason": f"until 越界（当前最大 {top}）"}
        return {"checkpoint": hist.set_checkpoint(until), "reviewed_until": until, "ok": True}
    top = hist.max_done_id()
    return {"checkpoint": hist.set_checkpoint(top), "reviewed_until": top, "ok": True}


@router.get("/history/export")
def history_export(
    start_ts: float | None = Query(default=None, description="起始 Unix 秒"),
    end_ts: float | None = Query(default=None, description="结束 Unix 秒"),
    limit: int = Query(default=2000, ge=1, le=20000),
):
    """按时间区间导出操作记录（JSON）。start/end 省略表示不限。"""
    items = get_history().list_range(start_ts=start_ts, end_ts=end_ts, limit=limit)
    out = []
    for op in items:
        p = op.get("payload") or {}
        label, vids = _describe_op(op.get("action", ""), p)
        out.append({
            "id": op["id"],
            "time": op["time"],
            "datetime": __import__("datetime").datetime.fromtimestamp(op["time"]).strftime("%Y-%m-%d %H:%M:%S"),
            "action": op["action"],
            "user": op.get("user", ""),
            "ip": op.get("ip", ""),
            "label": label,
            "vids": vids,
        })
    from fastapi.responses import JSONResponse

    return JSONResponse(
        {"start_ts": start_ts, "end_ts": end_ts, "count": len(out), "items": out},
        headers={"Content-Disposition": 'attachment; filename="knowledge_ops_history.json"'},
    )


def _describe_op(action: str, p: dict) -> tuple[str, list[str]]:
    if action == "insert_vertex":
        n = _display_name(p.get("props"), p.get("vid"))
        return f"新增节点「{n}」({p.get('tag', '')})", [p.get("vid", "")] if p.get("vid") else []
    if action == "update_vertex":
        n = _display_name(p.get("props"), p.get("vid"))
        keys = "、".join(list((p.get("props") or {}).keys())) or "属性"
        return f"修改节点「{n}」：{keys}", [p.get("vid", "")] if p.get("vid") else []
    if action == "delete_vertex":
        undo = p.get("undo") or {}
        vertex = undo.get("vertex") or {}
        n = _display_name(vertex.get("props"), vertex.get("vid") or p.get("vid"))
        d = f"删除节点「{n}」({vertex.get('tag') or p.get('tag', '')})"
        edges = undo.get("edges") or []
        if edges:
            d += "（含 " + str(len(edges)) + " 条关联边）"
        return d, []
    if action == "insert_edge":
        et = _edge_label(p.get("edge_type", ""))
        s = _display_name(p.get("s_props"), p.get("src")) or str(p.get("src", ""))
        d = _display_name(p.get("d_props"), p.get("dst")) or str(p.get("dst", ""))
        return f"新增「{et}」：{s} → {d}", []
    if action == "delete_edge":
        et = _edge_label(p.get("edge_type", ""))
        s = _display_name(p.get("s_props"), p.get("src")) or str(p.get("src", ""))
        d = _display_name(p.get("d_props"), p.get("dst")) or str(p.get("dst", ""))
        return f"移除「{et}」：{s} → {d}", []
    return f"操作：{action}", []


def _edge_label(et: str) -> str:
    return {"belongs_to": "归属", "supports": "支撑", "relates_to": "关联"}.get(et, et)


def _display_name(props, vid) -> str:
    props = props or {}
    name = str(props.get("name") or "").strip()
    title = str(props.get("title") or "").strip()
    if name and not _looks_opaque(name):
        return name
    if title:
        return title if len(title) <= 40 else title[:40] + "…"
    return str(vid or "")


def _looks_opaque(s: str) -> bool:
    return len(s) >= 20 or any(ch in s for ch in "．·")
@router.post("/history/undo")
def history_undo(_token: str = Depends(require_write_token), x_client_id: str = Header(default=""), request: Request = None):
    store = _store_for(x_client_id, request)
    return get_history().undo(store, user=x_client_id)


@router.post("/history/redo")
def history_redo(_token: str = Depends(require_write_token), x_client_id: str = Header(default=""), request: Request = None):
    store = _store_for(x_client_id, request)
    return get_history().redo(store, user=x_client_id)


@router.get("/meta/schema")
def schema_meta():
    return {
        "tags": list(TAGS),
        "edges": list(EDGES),
        "architecture": architecture.ARCH_SCHEMA,
    }
