"""SQLite-backed operation history: record, undo, redo for graph writes.

Every successful write op is logged with an inverse action. Undo replays the
inverse; redo replays the original. Log is persistent across restarts.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

_env_db = os.getenv("HISTORY_DB", "").strip()
if _env_db:
    _HISTORY_DB = Path(_env_db).resolve()
else:
    _HISTORY_DB = Path(__file__).resolve().parent.parent / "data" / "history.db"
_HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    action TEXT NOT NULL,          -- insert_vertex | update_vertex | delete_vertex | insert_edge | delete_edge
    payload TEXT NOT NULL,         -- json of the operation context
    undo TEXT NOT NULL,            -- json of the inverse action
    done INTEGER NOT NULL DEFAULT 1,
    user TEXT NOT NULL DEFAULT ''
);
"""
SCHEMA_REVIEW = """
CREATE TABLE IF NOT EXISTS review_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    checkpoint INTEGER NOT NULL DEFAULT 0
);
"""


# 后加列（幂等）：batch=同一请求内的批量写归为一组；ip=发起请求的客户端地址
_EXTRA_COLS = (
    ("batch", "TEXT NOT NULL DEFAULT ''"),
    ("ip", "TEXT NOT NULL DEFAULT ''"),
)


def _add_column(conn, table: str, name: str, ddl: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        conn.commit()
    except Exception:
        pass  # duplicate column 已存在


class HistoryRecorder:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _HISTORY_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + 互斥锁：解决 FastAPI 线程池下跨线程使用同一连接的报错
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        with self._lock:
            self._conn.execute(SCHEMA)
            self._conn.execute(SCHEMA_REVIEW)
            self._conn.execute("INSERT OR IGNORE INTO review_state(id, checkpoint) VALUES (1, 0)")
            for _name, _ddl in _EXTRA_COLS:
                _add_column(self._conn, "ops", _name, _ddl)
            self._conn.commit()

    def close(self) -> None:
        try:
            with self._lock:
                self._conn.close()
        except Exception:
            pass

    def record(self, action: str, payload: dict, undo: dict, *, user: str = "", batch: str = "", ip: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO ops(ts, action, payload, undo, done, user, batch, ip) VALUES (?,?,?,?,1,?,?,?)",
                (time.time(), action, json.dumps(payload, ensure_ascii=False),
                 json.dumps(undo, ensure_ascii=False), user, batch or "", ip or ""),
            )
            self._conn.commit()
            return cur.lastrowid

    def _undo_batch(self, op_id: int, batch: str) -> dict:
        """整体撤回同一个 batch 的所有操作（= 一次用户操作）。

        同一 HTTP 请求内的批量写（如一次级联删除、一次导入）会在一次点击里全部回退。
        恢复节点时采用两阶段：先把批次内所有顶点按 id 升序（叶子先于父）重建，
        再统一补边，避免“父/子还未恢复导致边插入失败”。
        """
        if not batch:
            return None
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, undo FROM ops WHERE batch=? AND done=1 ORDER BY id DESC", (batch,)
            ).fetchall()
        if not rows:
            return None
        ops = []
        for r in rows:
            try:
                ops.append((r[0], json.loads(r[1])))
            except (TypeError, ValueError):
                continue
        from backend.store import GraphStore

        store = GraphStore()  # 非记录型实例：撤回本身不再写入历史
        restores = [(i, u) for i, u in ops if u.get("kind") == "vertex_with_edges"]
        others = [(i, u) for i, u in ops if u.get("kind") != "vertex_with_edges"]
        # 1) 其它逆操作按 id 倒序（先撤后发生的，例如先撤边再撤点）
        for _id, u in others:
            try:
                self._apply(store, u)
            except Exception as exc:
                return {"ok": False, "reason": f"撤回失败(op {_id}): {exc}"}
        # 2) 恢复被删顶点：先全部顶点（叶子先于父），再统一补边
        for _id, u in sorted(restores, key=lambda t: t[0]):
            v = u.get("vertex") or {}
            if not v.get("vid"):
                continue
            try:
                store.insert_vertex(v.get("tag"), v["vid"], v.get("props") or {})
            except Exception as exc:
                return {"ok": False, "reason": f"撤回失败(op {_id}): {exc}"}
        edge_fail = 0
        for _id, u in sorted(restores, key=lambda t: t[0]):
            for e in u.get("edges") or []:
                if not (e.get("src_vid") and e.get("dst_vid") and e.get("edge_type")):
                    continue
                try:
                    store.insert_edge(e["edge_type"], e["src_vid"], e["dst_vid"], e.get("props") or {})
                except Exception:
                    edge_fail += 1  # 边端点已不存在等：不阻断整批撤回
        with self._lock:
            for _id, _ in ops:
                self._conn.execute("UPDATE ops SET done=0 WHERE id=?", (_id,))
            self._conn.commit()
        first = ops[-1][0] if ops else op_id
        return {
            "ok": True,
            "op": {"id": first, "action": "batch_undo", "payload": {"batch": batch, "ops": len(ops)}},
            "undone": {"kind": "batch", "batch": batch, "ops": len(ops), "edge_fail": edge_fail},
        }

    def _redo_batch(self, batch: str) -> dict:
        """整体重做同一个 batch（该批次所有 done=0 的操作）。"""
        if not batch:
            return None
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, payload FROM ops WHERE batch=? AND done=0 ORDER BY id DESC", (batch,)
            ).fetchall()
        if not rows:
            return None
        ops = []
        for r in rows:
            try:
                ops.append((r[0], json.loads(r[1])))
            except (TypeError, ValueError):
                continue
        for _id, payload in reversed(ops):  # 重做按原顺序（先建点再连边）
            try:
                self._apply_runner(payload)
            except Exception as exc:
                return {"ok": False, "reason": f"重做失败(op {_id}): {exc}"}
        with self._lock:
            for _id, _ in ops:
                self._conn.execute("UPDATE ops SET done=1 WHERE id=?", (_id,))
            self._conn.commit()
        return {
            "ok": True,
            "op": {"id": ops[0][0], "action": "batch_redo", "payload": {"batch": batch, "ops": len(ops)}},
            "undone": {"kind": "batch", "batch": batch, "ops": len(ops)},
        }

    def undo(self, store, user: str = "") -> dict:
        """撤回该用户最近的一次操作（一次用户动作 = 一个 batch）。

        每次只回退“最近一次操作”：若是批量写（如级联删除/导入）则整批回退，
        单条写则只回退该条。不再把多次独立删除合并成一次撤回。
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT id, action, payload, undo, batch FROM ops WHERE done=1"
                + (" AND user=?" if user else "")
                + " ORDER BY id DESC LIMIT 1;",
                (user,) if user else (),
            ).fetchone()
        if not row:
            return {"ok": False, "reason": "无可撤回操作"}
        op_id, action, payload, undo, batch = row
        batch_res = self._undo_batch(op_id, batch)
        if batch_res:
            return batch_res
        undo_data = json.loads(undo)
        try:
            self._apply_runner(undo_data)
        except Exception as exc:
            return {"ok": False, "reason": f"撤回失败: {exc}"}
        with self._lock:
            self._conn.execute("UPDATE ops SET done=0 WHERE id=?", (op_id,))
            self._conn.commit()
        return {"ok": True, "op": {"id": op_id, "action": action, "payload": json.loads(payload)}, "undone": undo_data}

    def redo(self, store, user: str = "") -> dict:
        """重做该用户最近一次被撤回的操作（与 undo 对称：一次操作一个 batch）。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, action, payload, batch FROM ops WHERE done=0"
                + (" AND user=?" if user else "")
                + " ORDER BY id DESC LIMIT 1;",
                (user,) if user else (),
            ).fetchone()
        if not row:
            return {"ok": False, "reason": "无可重做操作"}
        op_id, action, payload, batch = row
        batch_res = self._redo_batch(batch)
        if batch_res:
            return batch_res
        try:
            self._apply_runner(json.loads(payload))
        except Exception as exc:
            return {"ok": False, "reason": f"重做失败: {exc}"}
        with self._lock:
            self._conn.execute("UPDATE ops SET done=1 WHERE id=?", (op_id,))
            self._conn.commit()
        return {"ok": True, "op": {"id": op_id, "action": action, "payload": json.loads(payload)}}

    def _apply_runner(self, act: dict) -> None:
        """Execute an action with a throwaway (non-recording) store so an undo/redo
        does not itself append to the history."""
        from backend.store import GraphStore
        self._apply(GraphStore(), act)

    def list(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, action, done, user FROM ops ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [
            {"id": r[0], "time": r[1], "action": r[2], "done": bool(r[3]), "user": r[4]}
            for r in rows
        ]

    def recent(self, limit: int = 10) -> list[dict]:
        """最近写操作（含 payload 上下文），供前端轻量只读展示，不触发任何图库查询。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, action, done, user, payload, batch, ip FROM ops ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        items = []
        for r in rows:
            try:
                payload = json.loads(r[5])
            except Exception:
                payload = {}
            items.append({
                "id": r[0], "time": r[1], "action": r[2], "done": bool(r[3]), "user": r[4],
                "payload": payload, "batch": r[6] or "", "ip": r[7] or "",
            })
        return items

    def list_range(self, start_ts: float | None = None, end_ts: float | None = None, limit: int = 2000) -> list[dict]:
        """按时间区间导出写操作（含 payload）。start/end 为 Unix 秒，None 表示不限。"""
        q = "SELECT id, ts, action, done, user, payload, batch, ip FROM ops"
        conds, args = [], []
        if start_ts is not None:
            conds.append("ts >= ?"); args.append(float(start_ts))
        if end_ts is not None:
            conds.append("ts <= ?"); args.append(float(end_ts))
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY id ASC LIMIT ?"
        args.append(int(limit))
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            try:
                payload = json.loads(r[5])
            except Exception:
                payload = {}
            out.append({
                "id": r[0], "time": r[1], "action": r[2], "done": bool(r[3]), "user": r[4],
                "payload": payload, "batch": r[6] or "", "ip": r[7] or "",
            })
        return out

    # ---------- 安全校核：基线 + 待校核清单 ----------
    def get_checkpoint(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT checkpoint FROM review_state WHERE id=1").fetchone()
        return int(row[0] if row else 0)

    def set_checkpoint(self, cp: int) -> int:
        cp = int(cp)
        with self._lock:
            self._conn.execute("UPDATE review_state SET checkpoint=? WHERE id=1", (cp,))
            self._conn.commit()
        return cp

    def max_done_id(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(MAX(id), 0) FROM ops WHERE done=1").fetchone()
        return int(row[0] if row else 0)

    def pending_rows(self, limit: int = 5000) -> list[dict]:
        """自校核基线以来、且未撤销（done=1）的操作，按时间正序。"""
        with self._lock:
            cp_row = self._conn.execute("SELECT checkpoint FROM review_state WHERE id=1").fetchone()
            cp = int(cp_row[0] if cp_row else 0)
            rows = self._conn.execute(
                "SELECT id, ts, action, payload, undo, user, batch, ip FROM ops "
                "WHERE done=1 AND id>? ORDER BY id ASC LIMIT ?",
                (cp, int(limit)),
            ).fetchall()
        out = []
        for r in rows:
            try:
                payload = json.loads(r[3])
                undo = json.loads(r[4])
            except (TypeError, ValueError):
                payload, undo = {}, {}
            out.append(
                {
                    "id": r[0],
                    "time": r[1],
                    "action": r[2],
                    "payload": payload,
                    "undo": undo,
                    "user": r[5] or "",
                    "batch": r[6] or "",
                    "ip": r[7] or "",
                }
            )
        return out

    def mark_undone(self, op_id: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE ops SET done=0 WHERE id=?", (int(op_id),))
            self._conn.commit()

    def _apply(self, store, act: dict) -> None:
        """Execute a stored action against the GraphStore (undo or redo body)."""
        kind = act.get("kind")
        if kind == "vertex_with_edges":         # undo(delete): rebuild node + its edges
            store.vertex_with_edges(act)
        elif kind == "vertex_set" or kind == "vertex":       # create/overwrite node with given props
            store.insert_vertex(act["tag"], act["vid"], act.get("props") or {})
        elif kind == "vertex_delete":
            store.delete_vertex(act["vid"])
        elif kind == "edge_set":
            store.insert_edge(act["edge_type"], act["src"], act["dst"], act.get("props"))
        elif kind == "edge_delete":
            store.delete_edge(act["edge_type"], act["src"], act["dst"])
        else:
            raise ValueError(f"未知操作种类: {kind}")


_history: HistoryRecorder | None = None


def get_history() -> HistoryRecorder:
    global _history
    if _history is None:
        _history = HistoryRecorder()
    return _history
