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
        """整体撤回同一个 batch 的所有操作。

        同一 HTTP 请求内的批量写（如一次导入 = 1 个 batch）会在一次点击里全部回退。
        批次内撤销顺序按 id 倒序执行（先撤后发生的，保证删点前其关联边已撤）。
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
        # 先撤 insert_edge（后执行/记录），再撤 insert_vertex —— 逆序执行已满足（边记录靠后）
        for _id, undo_data in ops:
            try:
                self._apply_runner(undo_data)
            except Exception as exc:
                return {"ok": False, "reason": f"撤回失败(op {_id}): {exc}"}
        with self._lock:
            for _id, _ in ops:
                self._conn.execute("UPDATE ops SET done=0 WHERE id=?", (_id,))
            self._conn.commit()
        first = ops[-1][0] if ops else op_id
        return {
            "ok": True,
            "op": {"id": first, "action": "batch_undo", "payload": {"batch": batch, "ops": len(ops)}},
            "undone": {"kind": "batch", "batch": batch, "ops": len(ops)},
        }

    def _undo_delete_streak(self, op_id: int, user: str = "") -> dict | None:
        """把以最新 delete_vertex 为终点、向更早连续出现的 delete_vertex 合并成一次撤回。

        只有“连续”（中间没有其它类型的 done=1 操作隔开）的 delete_vertex 才会被合并，
        避免误伤不同时刻的独立删除。
        """
        with self._lock:
            user_cond = " AND user=?" if user else ""
            rows = self._conn.execute(
                "SELECT id, undo FROM ops WHERE done=1" + user_cond
                + " ORDER BY id DESC LIMIT 500;",
                (user,) if user else (),
            ).fetchall()
        ids: list[int] = []
        undos: list[dict] = []
        stop = False
        for r in rows:
            _id = r[0]
            try:
                u = json.loads(r[1])
            except (TypeError, ValueError):
                u = {}
            if _id == op_id:
                stop = True  # 从最新一条开始，遇到它即进入“连续”段
            if not stop:
                continue
            # delete_vertex 的 undo 有两种形态：单独删点=vertex_delete；级联删点=vertex_with_edges
            act = u.get("kind")
            if act in ("vertex_delete", "vertex_with_edges"):
                if ids and (r[0] < ids[-1] - 1):
                    # 有缺口（中间插入过其它成功操作）则不再往前扩展
                    break
                ids.append(_id)
                undos.append(u)
                continue
            break
        if len(ids) <= 1:
            return None
        # 执行撤销：按 id 升序（先恢复最早被删的节点）。级联删除是“子先父后”，
        # 最早被删的是最下层叶子。先恢复叶子再恢复上层，避免中途出现无父节点。
        ordered = sorted(zip(ids, undos), key=lambda t: t[0])
        for _id, u in ordered:
            try:
                self._apply_runner(u)
            except Exception as exc:
                return {"ok": False, "reason": f"撤回失败(op {_id}): {exc}"}
        with self._lock:
            for _id in ids:
                self._conn.execute("UPDATE ops SET done=0 WHERE id=?", (_id,))
            self._conn.commit()
        return {
            "ok": True,
            "op": {"id": op_id, "action": "batch_undo",
                   "payload": {"delete_streak": True, "ops": len(ids)}},
            "undone": {"kind": "delete_streak", "ops": len(ids)},
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

    def _redo_delete_streak(self, op_id: int, user: str = "") -> dict | None:
        """与 _undo_delete_streak 对称：把一段连续被撤销的 delete_vertex 一起重做。

        以最新一条 undone(done=0) delete_vertex 为终点，向更早合并连续 done=0 的
        delete_vertex（中间不能有其它 done=0 操作隔开）。重做顺序为“父先子后”，
        与原始删除方向相反，保证建父再建子。
        """
        with self._lock:
            user_cond = " AND user=?" if user else ""
            rows = self._conn.execute(
                "SELECT id, payload FROM ops WHERE done=0" + user_cond
                + " ORDER BY id DESC LIMIT 500;",
                (user,) if user else (),
            ).fetchall()
        ids: list[int] = []
        payloads: list[dict] = []
        stop = False
        for r in rows:
            _id = r[0]
            try:
                p = json.loads(r[1])
            except (TypeError, ValueError):
                p = {}
            if _id == op_id:
                stop = True
            if not stop:
                continue
            # 仅合并 delete_vertex（payload.kind=vertex_delete）
            if p.get("kind") == "vertex_delete":
                if ids and (r[0] < ids[-1] - 1):
                    break
                ids.append(_id)
                payloads.append(p)
                continue
            break
        if len(ids) <= 1:
            return None
        # 重做顺序：id 倒序（先重做最后被撤销的=最早被删除的根？）
        # 原始删除：叶子先删、根后删 → 撤销时叶子先恢复。重做应把删除重新做一遍：
        # 因此重做应“先删根场景”不可取——毕竟目标是恢复“已撤销”状态。
        # 重做 = 重新执行删除，即把 nodes 再删一次。顺序对删除影响小，用 id 倒序即可。
        ordered = sorted(zip(ids, payloads), key=lambda t: t[0], reverse=True)
        for _id, p in ordered:
            try:
                self._apply_runner(p)
            except Exception as exc:
                return {"ok": False, "reason": f"重做失败(op {_id}): {exc}"}
        with self._lock:
            for _id in ids:
                self._conn.execute("UPDATE ops SET done=1 WHERE id=?", (_id,))
            self._conn.commit()
        return {
            "ok": True,
            "op": {"id": op_id, "action": "batch_redo",
                   "payload": {"delete_streak": True, "ops": len(ids)}},
            "undone": {"kind": "delete_streak", "ops": len(ids)},
        }

    def undo(self, store, user: str = "") -> dict:
        """Undo the most recent done op belonging to this client (if user given) or any.

        优先按“批次”整体撤回：同一次批量写入（batch 非空且未撤销的最近一组）一键全撤；
        无 batch（历史单点操作）则回退单条 op，保持兼容。
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
        # 无 batch 的单条删除：向前合并“同一用户 + 连续 delete_vertex”一起撤回，
        # 兼容早期“逐条 DELETE”记录的级联删除（一次点击恢复一整片）。
        if action == "delete_vertex":
            streak = self._undo_delete_streak(op_id, user)
            if streak:
                return streak
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
        """Redo the most recent undone op belonging to this client (if user given) or any.

        与 undo 对称：最近被整体撤销的 batch 一键重做；无 batch 则重做单条 op。
        """
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
        # 对称处理：连续被整体撤销的 delete_vertex 段，一起重做（与 _undo_delete_streak 对应）
        if action == "delete_vertex":
            streak = self._redo_delete_streak(op_id, user)
            if streak:
                return streak
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
