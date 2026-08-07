import os
import json
from datetime import datetime
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config

NEBULA_HOST = os.getenv("NEBULA_HOST", "127.0.0.1")
NEBULA_PORT = int(os.getenv("NEBULA_PORT", "9669"))
NEBULA_USER = os.getenv("NEBULA_USER", "root")
NEBULA_PASSWORD = os.getenv("NEBULA_PASSWORD", "nebula")
NEBULA_SPACE = os.getenv("NEBULA_SPACE", "auto_knowledge")


class NebulaKnowledgeStore:
    """NebulaGraph 图存储，实现与 SQLite KnowledgeBase 相同的接口"""

    def __init__(self):
        self._pool = None
        self._session = None
        self._connected = False

    def connect(self):
        config = Config()
        config.max_connection_pool_size = 10
        self._pool = ConnectionPool()
        addr = (NEBULA_HOST, NEBULA_PORT)
        self._pool.init([addr], config)
        self._session = self._pool.get_session(NEBULA_USER, NEBULA_PASSWORD)
        self.execute(f"USE {NEBULA_SPACE};")
        self._connected = True
        return self

    def _vid(self, text):
        return str(text).replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")

    def _val(self, v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return str(v)
        return repr(str(v))

    def execute(self, nql):
        resp = self._session.execute(nql)
        if not resp.is_succeeded():
            raise RuntimeError(f"nGQL failed: {nql}\n{resp.error_msg()}")
        return resp

    def execute_json(self, nql):
        return self._session.execute_json(nql)

    # ---- write ----
    def insert_vertex(self, tag, vid, props):
        props_str = ", ".join(f"{k}: {self._val(v)}" for k, v in props.items())
        nql = f"INSERT VERTEX {tag} IF NOT EXISTS ({', '.join(props.keys())}) VALUES '{self._vid(vid)}': ({props_str});"
        self.execute(nql)

    def update_vertex(self, vid, tag=None, props=None):
        node = self.get_vertex(vid)
        if not node:
            return False
        new_tag = tag if tag else node.get("tag", "technology")
        merged = dict(node.get("props", {}))
        if props is not None:
            merged.update(props)
        # re-insert overwrites existing vertex
        cols = ", ".join(self._quote_col(k) for k in merged.keys())
        vals = ", ".join(self._val(v) for v in merged.values())
        try:
            self.execute(f"DELETE VERTEX '{self._vid(vid)}' WITH EDGE; INSERT VERTEX {new_tag} ({cols}) VALUES '{self._vid(vid)}': ({vals});")
        except Exception:
            try:
                sets = ", ".join(f"{self._quote_col(k)}={self._val(v)}" for k, v in (props or {}).items())
                if sets:
                    self.execute(f"UPDATE VERTEX ON {new_tag} '{self._vid(vid)}' SET {sets};")
            except Exception:
                pass
        return True

    def insert_edge(self, edge_type, src, dst, props=None):
        src_v, dst_v = self._vid(src), self._vid(dst)
        if props:
            props_str = ", ".join(f"{k}: {self._val(v)}" for k, v in props.items())
            nql = f"INSERT EDGE IF NOT EXISTS {edge_type}({', '.join(props.keys())}) VALUES '{src_v}' -> '{dst_v}': ({props_str});"
        else:
            nql = f"INSERT EDGE IF NOT EXISTS {edge_type}() VALUES '{src_v}' -> '{dst_v}': ();"
        self.execute(nql)

    def delete_edge(self, edge_type, src, dst):
        src_v, dst_v = self._vid(src), self._vid(dst)
        try:
            self.execute(f"DELETE EDGE {edge_type} '{src_v}' -> '{dst_v}';")
            return True
        except Exception:
            return False

    def delete_vertex(self, vid):
        v = self._vid(vid)
        try:
            self.execute(f"DELETE VERTEX '{v}' WITH EDGE;")
            return True
        except Exception:
            return False

    def update_edge(self, edge_type, src, dst, props):
        src_v, dst_v = self._vid(src), self._vid(dst)
        if not props:
            return True
        sets = ", ".join(f"{k}={self._val(v)}" for k, v in props.items())
        try:
            self.execute(f"UPDATE EDGE ON {edge_type} '{src_v}' -> '{dst_v}' SET {sets};")
            return True
        except Exception:
            return False

    # ---- read ----
    def get_vertex(self, vid):
        _vid = self._vid(vid)
        nql = f"MATCH (v) WHERE id(v) == '{_vid}' RETURN id(v) AS vid, tags(v) AS tags, properties(v) AS props;"
        data = self.execute_json(nql)
        rows = data if isinstance(data, list) else []
        if not rows:
            return None
        row = rows[0]
        props = row.get("props", {}) or {}
        tags = row.get("tags") or []
        tag = tags[0] if tags else "unknown"
        return {"vid": row.get("vid") or _vid, "tag": tag, "props": props}

    def query_vertices(self, tag=None, keyword="", limit=100):
        results = []
        tags = [tag] if tag else ["technology", "category", "standard", "patent", "resource", "component", "document"]
        for t in tags:
            try:
                nql = f"MATCH (v:{t}) RETURN id(v) AS vid, properties(v) AS props;"
                data = self.execute_json(nql)
                for row in (data if isinstance(data, list) else []):
                    props = row.get("props", {}) or {}
                    if keyword and keyword not in json.dumps(props, ensure_ascii=False):
                        continue
                    results.append({"vid": row.get("vid"), "tag": t, "props": props})
                    if len(results) >= limit:
                        return results
            except Exception:
                continue
        return results

    def query_edges(self, src_vid=None, edge_type=None):
        if src_vid:
            _vid = self._vid(src_vid)
            if edge_type:
                nql = f"MATCH (a)-[e:{edge_type}]-(b) WHERE id(a) == '{_vid}' OR id(b) == '{_vid}' RETURN id(e) AS id, type(e) AS edge_type, id(a) AS src, id(b) AS dst, properties(e) AS props;"
            else:
                nql = f"MATCH (a)-[e]-(b) WHERE id(a) == '{_vid}' OR id(b) == '{_vid}' RETURN id(e) AS id, type(e) AS edge_type, id(a) AS src, id(b) AS dst, properties(e) AS props;"
        else:
            if edge_type:
                nql = f"MATCH (a)-[e:{edge_type}]-(b) RETURN id(e) AS id, type(e) AS edge_type, id(a) AS src, id(b) AS dst, properties(e) AS props LIMIT 200;"
            else:
                nql = "MATCH (a)-[e]-(b) RETURN id(e) AS id, type(e) AS edge_type, id(a) AS src, id(b) AS dst, properties(e) AS props LIMIT 200;"
        data = self.execute_json(nql)
        edges = []
        for row in (data if isinstance(data, list) else []):
            edges.append({
                "id": row.get("id"),
                "edge_type": row.get("edge_type"),
                "src_vid": row.get("src"),
                "dst_vid": row.get("dst"),
                "props": row.get("props", {}) or {},
            })
        return edges

    def get_neighbors(self, vid, depth=1):
        _vid = self._vid(vid)
        node_map = {}
        edge_set = set()

        node = self.get_vertex(vid)
        if node:
            node_map[node["vid"]] = node

        # 逐层获取邻居
        visited = set()
        frontier = {_vid}
        visited.add(_vid)
        for _ in range(depth):
            next_frontier = set()
            for cur in list(frontier):
                try:
                    nql = f"MATCH (a)-[e]->(b) WHERE id(a) == '{cur}' RETURN id(b) AS nid, type(e) AS et, properties(b) AS nprops, tags(b) AS ntags;"
                    data = self.execute_json(nql)
                except Exception:
                    continue
                for row in (data if isinstance(data, list) else []):
                    nid = str(row.get("nid"))
                    if nid not in node_map:
                        nprops = row.get("nprops") or {}
                        nprops = _cvt_node({"properties": nprops})
                        ntags = row.get("ntags") or []
                        node_map[nid] = {"vid": nid, "tag": ntags[0] if ntags else "unknown", "props": nprops}
                    edge_set.add((cur, row.get("et"), nid))
                    if nid not in visited:
                        visited.add(nid)
                        next_frontier.add(nid)
            frontier = next_frontier

        return {"nodes": list(node_map.values()), "edges": list(edge_set)}

    def full_text_search(self, query):
        results = []
        for r in self.query_vertices(keyword=query):
            r["_tag"] = r["tag"]
            r["name"] = r["props"].get("name", "") or r["props"].get("title", "") or r["props"].get("code", "")
            results.append(r)
        return results

    def find_path(self, src, dst):
        _src, _dst = self._vid(src), self._vid(dst)
        try:
            nql = f"FIND SHORTEST PATH FROM '{_src}' TO '{_dst}' OVER * YIELD path AS p;"
            data = self.execute_json(nql)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def get_count(self, tag):
        try:
            nql = f"MATCH (v:{tag}) RETURN count(v) AS cnt;"
            data = self.execute_json(nql)
            if isinstance(data, list) and data:
                return int(data[0].get("cnt", 0))
        except Exception:
            pass
        return 0

    def get_notes(self, vid):
        node = self.get_vertex(vid)
        props = node.get("props", {}) if node else {}
        return {
            "remarks": props.get("remarks", "") or "",
            "links": props.get("links", "") or "",
            "updated_at": props.get("notes_updated_at", None),
        }

    def update_notes(self, vid, remarks, links):
        node = self.get_vertex(vid)
        if not node:
            return {"remarks": "", "links": "", "updated_at": None}
        props = dict(node.get("props", {}))
        props["remarks"] = remarks or ""
        props["links"] = links or ""
        from datetime import datetime
        props["notes_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # upsert: re-insert overwrites existing vertex
        tag = node.get("tag", "technology")
        nql = f"DELETE VERTEX '{self._vid(vid)}' WITH EDGE; INSERT VERTEX {tag} ({', '.join(self._quote_col(k) for k in props.keys())}) VALUES '{self._vid(vid)}': ({', '.join(self._val(v) for v in props.values())});"
        try:
            self.execute(nql)
        except Exception:
            # fallback: simple UPDATE on known columns
            try:
                self.execute(f"UPDATE VERTEX ON {tag} '{self._vid(vid)}' SET remarks={self._val(remarks or '')}, links={self._val(links or '')};")
            except Exception:
                pass
        return self.get_notes(vid)

    def _quote_col(self, k):
        return str(k)

    def close(self):
        if self._session:
            self._session.release()
        if self._pool:
            self._pool.close()


def _cvt_node(n):
    """Convert nebula execute_json node dict to props"""
    if not isinstance(n, dict):
        return {}
    props = n.get("properties", n)
    if isinstance(props, dict):
        out = {}
        for k, v in props.items():
            if hasattr(v, "as_string"):
                try:
                    out[k] = v.as_string()
                except Exception:
                    out[k] = str(v)
            else:
                out[k] = v
        return out
    return {}


def vid(name):
    return str(name).replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
