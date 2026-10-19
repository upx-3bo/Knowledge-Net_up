"""安全校核（协作变更审阅）：基线 + 待校核清单 + 单项撤销。

模型：
- 所有写操作已实时入库，并记入 ops 历史（含 undo 载荷、作者 x-client-id、时间）。
- 校核基线 = 最近一次「接受」的 op id。id>基线且未撤销(done=1) 的操作视为「待校核」。
- 负责人可：刷新查看（GET /review/pending）→ 接受全部（推进基线）或 单项撤销（反向回滚该操作）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend import architecture
from backend.history import HistoryRecorder
from backend.store import GraphStore

CHANGE_LABEL = {
    "insert_vertex": "新增节点",
    "update_vertex": "修改属性",
    "delete_vertex": "删除节点",
    "insert_edge": "新增连接",
    "delete_edge": "删除连接",
}
EDGE_LABEL = {"belongs_to": "归属", "supports": "支撑", "relates_to": "关联"}
TAG_LABELS = architecture.LEVEL_LABEL


def _ts_iso(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return ""


def _endpoint_names(names: dict[str, str], et: str, src: str, dst: str) -> tuple[str, str]:
    """返回可读的 源→目标 名称。supports 由文档指向技术点/模块。"""
    s = names.get(src, src)
    d = names.get(dst, dst)
    if et == "supports":
        return d, s  # supports 是 文档→上层，展示为 上层 ← 文档
    return s, d


def _op_vids(op: dict[str, Any]) -> list[str]:
    action = op.get("action")
    p = op.get("payload") or {}
    if action in ("insert_vertex", "update_vertex", "delete_vertex"):
        v = str(p.get("vid") or "")
        return [v] if v else []
    if action in ("insert_edge", "delete_edge"):
        out = []
        for k in ("src", "dst"):
            v = str(p.get(k) or "")
            if v:
                out.append(v)
        return out
    return []


def batch_names(store: GraphStore, vids: list[str]) -> dict[str, str]:
    """批量取节点可读名（cur 图上存在则取现名；缺失的给 vid 兜底）。"""
    uniq = sorted({v for v in vids if v})
    found = store._get_vertices_in(uniq) if uniq else {}
    out: dict[str, str] = {}
    for v in uniq:
        n = found.get(v)
        if n:
            p = n.get("props") or {}
            out[v] = str(p.get("name") or p.get("title") or v)
        else:
            out[v] = v
    return out


def describe(op: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    action = op.get("action")
    p = op.get("payload") or {}
    u = op.get("undo") or {}
    label = CHANGE_LABEL.get(action, action)
    vids: list[str] = []
    edges: list[dict[str, str]] = []
    text = ""
    snap_name = ""

    if action == "insert_vertex":
        vid = str(p.get("vid") or "")
        vids = [vid]
        text = f"新增{TAG_LABELS.get(p.get('tag', ''), p.get('tag', ''))}「{names.get(vid, vid)}」"
    elif action == "update_vertex":
        vid = str(p.get("vid") or "")
        vids = [vid]
        prev = u.get("props") or {}
        parts = []
        for k, v in (p.get("props") or {}).items():
            old = prev.get(k, "")
            parts.append(f"{k}: {old or '空'} → {v or '空'}")
        text = f"修改{TAG_LABELS.get(p.get('tag', ''), p.get('tag', ''))}「{names.get(vid, vid)}」的属性（{', '.join(parts)}）"
    elif action == "delete_vertex":
        vid = str(p.get("vid") or "")
        vids = [vid]
        sv = u.get("vertex") or {}
        pv = (sv.get("props") or {}) if isinstance(sv, dict) else {}
        snap_name = str(pv.get("name") or pv.get("title") or "") or names.get(vid, vid)
        text = f"删除{TAG_LABELS.get(sv.get('tag', ''), '节点')}「{snap_name}」"
    elif action == "insert_edge":
        et = str(p.get("edge_type") or "")
        src, dst = str(p.get("src") or ""), str(p.get("dst") or "")
        edges = [{"edge_type": et, "src_vid": src, "dst_vid": dst}]
        s, d = _endpoint_names(names, et, src, dst)
        text = f"新增{EDGE_LABEL.get(et, et)}连接：{s} → {d}"
        vids = [src, dst]
    elif action == "delete_edge":
        et = str(p.get("edge_type") or "")
        src, dst = str(p.get("src") or ""), str(p.get("dst") or "")
        edges = [{"edge_type": et, "src_vid": src, "dst_vid": dst}]
        s, d = _endpoint_names(names, et, src, dst)
        text = f"删除{EDGE_LABEL.get(et, et)}连接：{s} → {d}"
        vids = [src, dst]
    else:
        text = f"{action} {p}"

    return {
        "id": op.get("id"),
        "time": _ts_iso(op.get("time") or 0),
        "actor": op.get("user") or "",
        "action": action,
        "label": label,
        "text": text,
        "vids": [v for v in vids if v],
        "edges": edges,
    }


def pending(store: GraphStore, hist: HistoryRecorder, limit: int = 500) -> dict[str, Any]:
    rows = hist.pending_rows(limit=limit)
    all_vids = [v for op in rows for v in _op_vids(op)]
    names = batch_names(store, all_vids)
    items = [describe(op, names) for op in rows]
    nodes: set[str] = set()
    edges: list[dict[str, str]] = []
    for it in items:
        for v in it["vids"]:
            nodes.add(v)
        for e in it["edges"]:
            edges.append(e)
    return {
        "checkpoint": hist.get_checkpoint(),
        "count": len(items),
        "items": items,
        "affected": {"nodes": sorted(nodes), "edges": edges},
    }


def revert(store: GraphStore, hist: HistoryRecorder, op: dict[str, Any]) -> dict[str, Any]:
    action = op.get("action")
    p = op.get("payload") or {}
    u = op.get("undo") or {}
    try:
        if action == "insert_vertex":
            store.delete_vertex(str(p.get("vid") or ""))
        elif action == "update_vertex":
            vid = str(p.get("vid") or "")
            prev = u.get("props") or {}
            store.update_vertex(vid, prev)
        elif action == "delete_vertex":
            store.vertex_with_edges(u)
        elif action == "insert_edge":
            ok = store.delete_edge(str(u.get("edge_type") or ""), str(u.get("src") or ""), str(u.get("dst") or ""))
            if not ok:
                return {"id": op.get("id"), "ok": False, "reason": "该连接已不存在（可能已被后续操作处理）"}
        elif action == "delete_edge":
            store.insert_edge(str(u.get("edge_type") or ""), str(u.get("src") or ""), str(u.get("dst") or ""), u.get("props"))
        else:
            return {"id": op.get("id"), "ok": False, "reason": f"不支持撤销操作: {action}"}
    except Exception as exc:  # noqa: BLE001
        return {"id": op.get("id"), "ok": False, "reason": f"{exc}"}
    hist.mark_undone(op["id"])
    return {"id": op.get("id"), "ok": True}
