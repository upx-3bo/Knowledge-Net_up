import json
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "knowledge.db")


class KnowledgeBase:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS vertices (
                vid TEXT PRIMARY KEY,
                tag TEXT NOT NULL,
                props TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                edge_type TEXT NOT NULL,
                src_vid TEXT NOT NULL,
                dst_vid TEXT NOT NULL,
                props TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_vid)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_vid)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_vertices_tag ON vertices(tag)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS node_notes (
                vid TEXT PRIMARY KEY,
                remarks TEXT DEFAULT '',
                links TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def get_notes(self, vid):
        c = self.conn.cursor()
        c.execute("SELECT remarks, links, updated_at FROM node_notes WHERE vid = ?", (vid,))
        row = c.fetchone()
        if row:
            return {"remarks": row["remarks"] or "", "links": row["links"] or "", "updated_at": row["updated_at"]}
        return {"remarks": "", "links": "", "updated_at": None}

    def update_notes(self, vid, remarks, links):
        c = self.conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO node_notes (vid, remarks, links, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (vid, remarks or "", links or "")
        )
        self.conn.commit()
        return self.get_notes(vid)

    def insert_vertex(self, tag, vid, props):
        c = self.conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO vertices (vid, tag, props) VALUES (?, ?, ?)",
            (vid, tag, json.dumps(props, ensure_ascii=False))
        )
        self.conn.commit()

    def update_vertex(self, vid, tag=None, props=None):
        """更新节点 tag 和/或 props。props 为 dict 时整体覆盖。"""
        c = self.conn.cursor()
        c.execute("SELECT tag, props FROM vertices WHERE vid = ?", (vid,))
        row = c.fetchone()
        if not row:
            return False
        new_tag = tag if tag else row["tag"]
        new_props = json.dumps(props, ensure_ascii=False) if props is not None else row["props"]
        c.execute("UPDATE vertices SET tag = ?, props = ? WHERE vid = ?", (new_tag, new_props, vid))
        self.conn.commit()
        return True

    def insert_edge(self, edge_type, src, dst, props=None):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO edges (edge_type, src_vid, dst_vid, props) VALUES (?, ?, ?, ?)",
            (edge_type, src, dst, json.dumps(props or {}, ensure_ascii=False))
        )
        self.conn.commit()
        return c.lastrowid

    def delete_edge(self, edge_type, src, dst):
        c = self.conn.cursor()
        c.execute(
            "DELETE FROM edges WHERE edge_type = ? AND src_vid = ? AND dst_vid = ?",
            (edge_type, src, dst)
        )
        self.conn.commit()
        return c.rowcount > 0

    def delete_vertex(self, vid):
        c = self.conn.cursor()
        # 删除所有相关的边（作为源或目标）
        c.execute("DELETE FROM edges WHERE src_vid = ? OR dst_vid = ?", (vid, vid))
        # 删除备注
        c.execute("DELETE FROM node_notes WHERE vid = ?", (vid,))
        # 删除节点
        c.execute("DELETE FROM vertices WHERE vid = ?", (vid,))
        self.conn.commit()
        return c.rowcount > 0

    def update_edge(self, edge_type, src, dst, props):
        c = self.conn.cursor()
        c.execute(
            "UPDATE edges SET props = ? WHERE edge_type = ? AND src_vid = ? AND dst_vid = ?",
            (json.dumps(props or {}, ensure_ascii=False), edge_type, src, dst)
        )
        self.conn.commit()
        return c.rowcount > 0

    def get_vertex(self, vid):
        c = self.conn.cursor()
        c.execute("SELECT * FROM vertices WHERE vid = ?", (vid,))
        row = c.fetchone()
        if row:
            return {"vid": row["vid"], "tag": row["tag"], "props": json.loads(row["props"])}
        return None

    def query_vertices(self, tag=None, keyword="", limit=500):
        c = self.conn.cursor()
        if tag and keyword:
            c.execute(
                "SELECT * FROM vertices WHERE tag = ? AND props LIKE ? LIMIT ?",
                (tag, f"%{keyword}%", limit)
            )
        elif tag:
            c.execute("SELECT * FROM vertices WHERE tag = ? LIMIT ?", (tag, limit))
        elif keyword:
            c.execute("SELECT * FROM vertices WHERE props LIKE ? LIMIT ?", (f"%{keyword}%", limit))
        else:
            c.execute("SELECT * FROM vertices LIMIT ?", (limit,))
        return [{"vid": r["vid"], "tag": r["tag"], "props": json.loads(r["props"])} for r in c.fetchall()]

    def query_edges(self, src_vid=None, edge_type=None):
        c = self.conn.cursor()
        conditions = []
        params = []
        if src_vid:
            conditions.append("(src_vid = ? OR dst_vid = ?)")
            params.extend([src_vid, src_vid])
        if edge_type:
            conditions.append("edge_type = ?")
            params.append(edge_type)
        where = " AND ".join(conditions) if conditions else "1=1"
        c.execute(f"SELECT * FROM edges WHERE {where} LIMIT 1000", params)
        return [{"id": r["id"], "edge_type": r["edge_type"], "src_vid": r["src_vid"], "dst_vid": r["dst_vid"], "props": json.loads(r["props"])} for r in c.fetchall()]

    def get_neighbors(self, vid, depth=1):
        visited = set()
        result_nodes = {}
        result_edges = []

        def dfs(current_vid, d):
            if d > depth or current_vid in visited:
                return
            visited.add(current_vid)
            node = self.get_vertex(current_vid)
            if node:
                result_nodes[current_vid] = node
            if d < depth:
                for e in self.query_edges(src_vid=current_vid):
                    eid = (e["src_vid"], e["edge_type"], e["dst_vid"])
                    if eid not in result_edges:
                        result_edges.append(eid)
                    other = e["dst_vid"] if e["src_vid"] == current_vid else e["src_vid"]
                    if other not in visited:
                        dfs(other, d + 1)

        dfs(vid, 0)
        return {"nodes": list(result_nodes.values()), "edges": result_edges}

    def full_text_search(self, query):
        results = []
        for v in self.query_vertices(keyword=query):
            v["_tag"] = v["tag"]
            v["name"] = v["props"].get("name", "")
            results.append(v)
        return results

    def find_path(self, src, dst):
        visited = set()
        queue = [[src]]
        while queue:
            path = queue.pop(0)
            node = path[-1]
            if node == dst:
                return path
            if node in visited:
                continue
            visited.add(node)
            for e in self.query_edges(src_vid=node):
                neighbor = e["dst_vid"] if e["src_vid"] == node else e["src_vid"]
                if neighbor not in visited:
                    queue.append(path + [neighbor])
        return []

    def get_count(self, tag):
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM vertices WHERE tag = ?", (tag,))
        r = c.fetchone()
        return r["cnt"] if r else 0

    def clear(self):
        c = self.conn.cursor()
        c.execute("DELETE FROM vertices")
        c.execute("DELETE FROM edges")
        self.conn.commit()
