"""Nebula-backed graph store for the L0–L3 tech network."""
from __future__ import annotations

import re
import uuid
from typing import Any

from backend import architecture
from backend.config import NEBULA_SPACE
from backend.nebula_client import NebulaClient, NebulaError, get_client
from backend.nebula_values import as_python, rows_as_dicts

TAGS = architecture.LEVELS
EDGES = ("belongs_to", "supports", "relates_to")

# tag → 层级序号（0=根 vehicle，越大越叶子），供按层动态加载与父链完整截断使用
_LAYER_POS: dict[str, int] = {name: i for i, name in enumerate(
    ("vehicle", "domain", "subdomain", "module", "technology", "material"))}

TAG_PROPS: dict[str, tuple[str, ...]] = {
    "vehicle": ("name", "description"),
    "domain": ("name", "description"),
    "subdomain": ("name", "description"),
    "module": ("name", "description", "keywords", "status"),
    "technology": ("name", "description", "keywords", "status"),
    "material": (
        "name",
        "material_type",
        "title",
        "summary",
        "source_url",
        "published_at",
    ),
}

EDGE_PROPS: dict[str, tuple[str, ...]] = {
    "belongs_to": ("weight",),
    "supports": ("weight",),
    "relates_to": ("relation_type", "weight"),
}


def _escape(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    s = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


def _sanitize_vid(vid: str) -> str:
    vid = vid.strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-:.]{1,64}", vid):
        raise ValueError(f"invalid vid: {vid}")
    return vid


def _sanitize_keyword(keyword: str) -> str:
    return keyword.replace("\\", "\\\\").replace("'", "\\'").replace('"', "")


def make_vid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class GraphStore:
    def __init__(self, client: NebulaClient | None = None, history=None, *, batch: str = "") -> None:
        self.client = client or get_client()
        self.history = history  # optional HistoryRecorder; capture writes if set
        self.user = ""  # client id for history attribution (set per-request by routers)
        self.batch = batch or uuid.uuid4().hex[:12]  # 一次请求内多次写归为一批，供审计/审阅合并
        self.ip = ""  # request client ip, set per-request by routers

    def _note(self, action: str, op_payload: dict) -> None:
        if self.history is not None:
            try:
                self.history.record(action, op_payload, op_payload.get("undo") or {"kind": "noop"},
                                    user=self.user, batch=self.batch, ip=self.ip)
            except Exception:
                pass

    def ping(self) -> dict[str, str]:
        self.client.execute("YIELD 1 AS ok;", use_space=False)
        self.client.execute(f"USE {NEBULA_SPACE}; YIELD 1 AS ok;")
        return {"status": "ok", "space": NEBULA_SPACE}

    def stats(self) -> dict[str, int]:
        # Tolerate per-tag failures instead of silently reporting 0 for all.
        out: dict[str, int] = {}
        failed: list[str] = []
        for t in TAGS:
            try:
                out[t] = self.count(t)
            except NebulaError as exc:
                out[t] = -1
                failed.append(f"{t}({exc})")
        if failed:
            out["error"] = "; ".join(failed)
        return out

    def count(self, tag: str) -> int:
        self._assert_tag(tag)
        resp = self.client.execute(f"MATCH (v:{tag}) RETURN count(v) AS c;")
        try:
            return int(resp.row_values(0)[0].as_int())
        except (IndexError, TypeError, ValueError) as exc:
            # A parsed-but-unreadable row is a real inconsistency; surface it.
            from backend.nebula_client import NebulaError as _NE
            raise _NE(f"count({tag}) could not parse result: {exc}") from exc

    def insert_vertex(self, tag: str, vid: str, props: dict[str, Any]) -> dict[str, Any]:
        if self.get_vertex(vid):
            return self.get_vertex(vid)
        self._assert_tag(tag)
        vid = _sanitize_vid(vid)
        clean = self._filter_props(TAG_PROPS[tag], props)
        if not clean:
            nql = f"INSERT VERTEX IF NOT EXISTS {tag}() VALUES '{vid}': ();"
        else:
            cols = ", ".join(clean.keys())
            vals = ", ".join(_escape(v) for v in clean.values())
            nql = f"INSERT VERTEX IF NOT EXISTS {tag}({cols}) VALUES '{vid}': ({vals});"
        self.client.execute(nql)
        self._note("insert_vertex", {
            "kind": "vertex", "tag": tag, "vid": vid, "props": clean,
            "undo": {"kind": "vertex_delete", "vid": vid},
        })
        return self.get_vertex(vid) or {"vid": vid, "tag": tag, "props": clean}

    def update_vertex(self, vid: str, props: dict[str, Any]) -> dict[str, Any] | None:
        node = self.get_vertex(vid)
        if not node:
            return None
        tag = node["tag"]
        self._assert_tag(tag)
        clean = self._filter_props(TAG_PROPS[tag], props)
        if not clean:
            return node
        prev = {k: node["props"].get(k) for k in clean if k in node["props"]}
        sets = ", ".join(f"{k} = {_escape(v)}" for k, v in clean.items())
        self.client.execute(f"UPDATE VERTEX ON {tag} '{_sanitize_vid(vid)}' SET {sets};")
        self._note("update_vertex", {
            "kind": "vertex_set", "tag": tag, "vid": vid,
            "props": {k: v for k, v in clean.items()},
            "undo": {"kind": "vertex_set", "tag": tag, "vid": vid, "props": prev},
        })
        return self.get_vertex(vid)

    def delete_vertex(self, vid: str) -> bool:
        vid = _sanitize_vid(vid)
        node = self.get_vertex(vid)
        if not node:
            return False
        # Snapshot the node + all its edges so undo can rebuild them.
        edges = self.neighbors(vid, depth=1).get("edges", [])
        self.client.execute(f"DELETE VERTEX '{vid}' WITH EDGE;")
        undo = {"kind": "vertex_with_edges",
                "vertex": {"tag": node["tag"], "vid": vid, "props": node["props"]},
                "edges": [e for e in edges
                          if e.get("src_vid") == vid or e.get("dst_vid") == vid]}
        self._note("delete_vertex", {"kind": "vertex_delete", "vid": vid, "undo": undo})
        return True

    def cascade_owned(self, vid: str) -> dict[str, Any]:
        """级联删除候选集：本节点 + 下层「只归本节点管控」的全部节点。

        判定规则：
        - 父(管控)关系同时看 belongs_to（子域→领域…）与 supports（文档→技术点/模块）。
        - 一个下层节点 c 只有当它的【所有】父节点都落在级联集内，才被认定“只归
          本节点管控”，才会一并删除；否则（如一个文档支撑两个技术点）保留。
        - 返回按发现顺序的节点列表（含根），供前端级联删除。
        """
        vid = _sanitize_vid(vid)
        if not self.get_vertex(vid):
            return {"root": None, "nodes": [], "count": 0}

        parents: dict[str, set[str]] = {}
        children_of: dict[str, set[str]] = {}

        def _collect(edge_type: str) -> None:
            resp = self.client.execute(
                f"MATCH (c)-[e:{edge_type}]->(p) RETURN id(c) AS c, id(p) AS p;"
            )
            for row in rows_as_dicts(resp):
                c = str(row.get("c") or "").strip("'\"")
                p = str(row.get("p") or "").strip("'\"")
                if not c or not p:
                    continue
                parents.setdefault(c, set()).add(p)
                children_of.setdefault(p, set()).add(c)

        _collect("belongs_to")
        _collect("supports")

        owned: set[str] = {vid}
        order: list[str] = [vid]
        i = 0
        while i < len(order):
            u = order[i]
            i += 1
            for c in (children_of.get(u) or ()):
                if c in owned:
                    continue
                if all(p in owned for p in parents.get(c, ())):
                    owned.add(c)
                    order.append(c)

        nodes = []
        by_id = self._get_vertices_in(order)
        for v in order:
            node = by_id.get(v)
            if node:
                nodes.append(node)
        return {"root": nodes[0] if nodes else None, "nodes": nodes, "count": len(nodes)}

    def vertex_with_edges(self, act: dict) -> None:
        """Rebuild a deleted vertex plus its edges (used when undoing a delete)."""
        v = act.get("vertex") or {}
        vid = v.get("vid")
        if vid:
            self.insert_vertex(v["tag"], vid, v.get("props") or {})
        for e in act.get("edges") or []:
            if e.get("src_vid") and e.get("dst_vid") and e.get("edge_type"):
                self.insert_edge(e["edge_type"], e["src_vid"], e["dst_vid"], e.get("props") or {})


    def get_vertex(self, vid: str) -> dict[str, Any] | None:
        vid = _sanitize_vid(vid)
        resp = self.client.execute(
            f"MATCH (v) WHERE id(v) == '{vid}' RETURN v AS node LIMIT 1;"
        )
        rows = rows_as_dicts(resp)
        if not rows:
            return None
        node = rows[0].get("node")
        return node if isinstance(node, dict) else None

    def _get_vertices_in(self, vids: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch many vertices by vid in a single query (avoids N+1).

        Returns {vid: node}. Unknown/absent vids are simply not present.
        """
        clean = []
        for v in vids:
            if not v:
                continue
            try:
                clean.append(_sanitize_vid(v))
            except ValueError:
                continue
        if not clean:
            return {}
        # IN-list of sanitized string vids; each is [A-Za-z0-9_\-:.] safe so no escaping needed
        in_list = ", ".join(f"'{v}'" for v in clean)
        resp = self.client.execute(
            f"MATCH (v) WHERE id(v) IN [{in_list}] RETURN v AS node;"
        )
        out: dict[str, dict[str, Any]] = {}
        for row in rows_as_dicts(resp):
            node = row.get("node")
            if isinstance(node, dict) and node.get("vid"):
                out[node["vid"]] = node
        return out

    def vertex_detail(self, vid: str) -> dict[str, Any] | None:
        """Node props plus 1-hop neighbor groups for the detail drawer."""
        node = self.get_vertex(vid)
        if not node:
            return None
        sub = self.neighbors(vid, depth=1)
        groups: dict[str, list[dict[str, Any]]] = {
            "belongs_to": [],
            "supports": [],
            "relates_to": [],
            "other": [],
        }
        by_id = {n["vid"]: n for n in sub.get("nodes", []) if n.get("vid") != vid}
        for e in sub.get("edges", []):
            et = e.get("edge_type") or "other"
            bucket = et if et in groups else "other"
            peer_vid = e["dst_vid"] if e.get("src_vid") == vid else e.get("src_vid")
            peer = by_id.get(peer_vid)
            if not peer:
                continue
            props = peer.get("props") or {}
            groups[bucket].append(
                {
                    "vid": peer["vid"],
                    "tag": peer.get("tag"),
                    "name": props.get("name") or props.get("title") or peer["vid"],
                    "direction": "out" if e.get("src_vid") == vid else "in",
                    "edge_type": et,
                    # expose for material "跳转" in the detail drawer
                    "source_url": props.get("source_url") or "",
                }
            )
        return {
            "node": node,
            "relations": groups,
            "stats": {
                "neighbors": len(by_id),
                "belongs_to": len(groups["belongs_to"]),
                "supports": len(groups["supports"]),
                "relates_to": len(groups["relates_to"]),
            },
        }

    def list_vertices(
        self,
        tag: str | None = None,
        keyword: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        tags = [tag] if tag else list(TAGS)
        for t in tags:
            self._assert_tag(t)

        results: list[dict[str, Any]] = []
        kw = _sanitize_keyword(keyword.strip()) if keyword else ""
        text_fields = ("name", "description", "keywords", "title", "summary")
        for t in tags:
            remain = limit - len(results)
            if remain <= 0:
                break
            if kw:
                fields = [f for f in text_fields if f in TAG_PROPS[t]]
                where = " OR ".join(f"v.{t}.{f} CONTAINS '{kw}'" for f in fields) or "true"
                nql = f"MATCH (v:{t}) WHERE {where} RETURN v AS node LIMIT {remain};"
            else:
                nql = f"MATCH (v:{t}) RETURN v AS node LIMIT {remain};"
            resp = self.client.execute(nql)
            for row in rows_as_dicts(resp):
                node = row.get("node")
                if isinstance(node, dict):
                    results.append(node)
        return results

    def insert_edge(
        self,
        edge_type: str,
        src: str,
        dst: str,
        props: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._assert_edge(edge_type)
        src, dst = _sanitize_vid(src), _sanitize_vid(dst)
        clean = self._filter_props(EDGE_PROPS[edge_type], props or {})
        if edge_type in ("belongs_to", "supports") and "weight" not in clean:
            clean["weight"] = 1.0
        if edge_type == "relates_to":
            clean.setdefault("relation_type", "related")
            clean.setdefault("weight", 0.8)

        cols = ", ".join(clean.keys())
        vals = ", ".join(_escape(v) for v in clean.values())
        nql = (
            f"INSERT EDGE IF NOT EXISTS {edge_type}({cols}) "
            f"VALUES '{src}' -> '{dst}': ({vals});"
        )
        self.client.execute(nql)
        self._note("insert_edge", {
            "kind": "edge_set", "edge_type": edge_type, "src": src, "dst": dst, "props": clean,
            "s_props": self._vertex_props_cached(src),
            "d_props": self._vertex_props_cached(dst),
            "undo": {"kind": "edge_delete", "edge_type": edge_type, "src": src, "dst": dst},
        })
        return {
            "edge_type": edge_type,
            "src_vid": src,
            "dst_vid": dst,
            "props": clean,
        }

    def _vertex_props_cached(self, vid: str) -> dict[str, Any]:
        """取节点 props（只读），带实例级缓存——批量加边时避免反复查询同名端点。"""
        cache = getattr(self, "_vprops_cache", None)
        if cache is None:
            cache = {}
            object.__setattr__(self, "_vprops_cache", cache)
        if vid in cache:
            return cache[vid]
        try:
            n = self.get_vertex(vid)
            cache[vid] = dict(n.get("props") or {}) if n else {}
        except Exception:
            cache[vid] = {}
        return cache[vid]

    def delete_edge(self, edge_type: str, src: str, dst: str) -> bool:
        self._assert_edge(edge_type)
        src, dst = _sanitize_vid(src), _sanitize_vid(dst)
        try:
            # Only report success when the edge actually exists; also capture its props for undo.
            check = self.client.execute(
                f"MATCH (a)-[e:{edge_type}]->(b) "
                f"WHERE id(a) == '{src}' AND id(b) == '{dst}' "
                f"RETURN count(e) AS c, properties(e) AS p;"
            )
            edge_props = {}
            try:
                edge_props = check.row_values(0)[1].as_map() if check.row_values(0).__len__() > 1 else {}
            except Exception:
                edge_props = {}
            try:
                exists = int(check.row_values(0)[0].as_int()) > 0
            except Exception:
                exists = True  # if we can't tell, attempt delete anyway
            if not exists:
                return False
            self.client.execute(f"DELETE EDGE {edge_type} '{src}' -> '{dst}';")
            self._note("delete_edge", {
                "kind": "edge_delete", "edge_type": edge_type, "src": src, "dst": dst,
                "undo": {"kind": "edge_set", "edge_type": edge_type, "src": src, "dst": dst, "props": edge_props},
            })
            return True
        except NebulaError:
            return False

    def children(self, parent_vid: str, tag: str = None) -> list[dict[str, Any]]:
        """Return vertices of `tag` (optional) that have a belongs_to edge to parent_vid.

        This is the scoped lookup used for domain isolation: when importing a new
        domain, subdomain/technology nodes are only matched within their parent's
        subtree, so same-named nodes in *other* domains are never reused / merged.
        """
        parent_vid = _sanitize_vid(parent_vid)
        tags = [tag] if tag else list(TAGS)
        for t in tags:
            self._assert_tag(t)
        results: list[dict[str, Any]] = []
        for t in tags:
            nql = (
                f"MATCH (v:{t})-[:belongs_to]->(p) WHERE id(p) == '{parent_vid}' "
                f"RETURN v AS node;"
            )
            resp = self.client.execute(nql)
            for row in rows_as_dicts(resp):
                node = row.get("node")
                if isinstance(node, dict):
                    results.append(node)
        return results

    def supports_children(self, parent_vid: str) -> list[dict[str, Any]]:
        """Return materials attached to `parent_vid` via a supports edge.

        Used by exports to render 文档（material）直接挂在 module / technology 下。
        """
        parent_vid = _sanitize_vid(parent_vid)
        resp = self.client.execute(
            f"MATCH (v:material)-[:supports]->(p) WHERE id(p) == '{parent_vid}' "
            f"RETURN v AS node;"
        )
        results = []
        for row in rows_as_dicts(resp):
            node = row.get("node")
            if isinstance(node, dict):
                results.append(node)
        return results

    def all_edges(self, edge_type: str) -> list[tuple[str, str]]:
        """Return all (src_vid, dst_vid) for `edge_type`（child->parent 方向）。"""
        self._assert_edge(edge_type)
        resp = self.client.execute(
            f"MATCH ()-[e:{edge_type}]->() RETURN src(e) AS s, dst(e) AS d;"
        )
        out = []
        for r in rows_as_dicts(resp):
            s = str(r.get("s") or "").strip("'\"")
            d = str(r.get("d") or "").strip("'\"")
            if s and d:
                out.append((s, d))
        return out

    def neighbors(self, vid: str, depth: int = 1) -> dict[str, Any]:
        vid = _sanitize_vid(vid)
        depth = max(1, min(int(depth), 3))
        center = self.get_vertex(vid)
        if not center:
            return {"nodes": [], "edges": []}

        # 必须用 src(edge)/dst(edge) 保留边的真实方向。
        # BIDIRECT 下 id($^)/id($$) 是“行走方向”，反向走时会把 belongs_to 画反。
        resp = self.client.execute(
            f"GO {depth} STEPS FROM '{vid}' OVER * BIDIRECT "
            f"YIELD DISTINCT src(edge) AS src, type(edge) AS edge_type, dst(edge) AS dst;"
        )
        edge_rows = rows_as_dicts(resp)
        node_ids = {vid}
        edges: list[dict[str, Any]] = []
        seen_e: set[tuple[str, str, str]] = set()
        for row in edge_rows:
            src = str(row.get("src") or "").strip("'\"")
            dst = str(row.get("dst") or "").strip("'\"")
            et = str(row.get("edge_type") or "")
            if not src or not dst or not et:
                continue
            key = (src, et, dst)
            if key in seen_e:
                continue
            seen_e.add(key)
            edges.append({"edge_type": et, "src_vid": src, "dst_vid": dst, "props": {}})
            node_ids.add(src)
            node_ids.add(dst)

        nodes = []
        if node_ids:
            by_id = self._get_vertices_in(list(node_ids))
            # Preserve traversal order is not essential; return in collected order
            for nid in node_ids:
                node = by_id.get(nid)
                if node:
                    nodes.append(node)
        return {"nodes": nodes, "edges": edges}

    def overview(
        self,
        limit_nodes: int = 3000,
        limit_edges: int = 8000,
        layer_cap: str = "",
    ) -> dict[str, Any]:
        """Return a capped overview for the workbench canvas.

        - `layer_cap`: 可选 "vehicle|domain|subdomain|module|technology|material"，
          只返回该层及上层（父链完整），资源多时可显著减轻画布压力。
        - 截断策略保证父链完整：优先保留结构层（车辆→领域→子域→模块→技术点），
          仅在必要时丢弃整组叶子；被保留节点不会被切掉父级而成为孤儿。
        """
        limit_nodes = max(1, min(int(limit_nodes), 10000))
        limit_edges = max(1, min(int(limit_edges), 20000))

        # 层级白名单（含上层），用于“按层动态加载”
        if layer_cap:
            cap_pos = _LAYER_POS.get(layer_cap, 99)
            allowed = [t for t, p in sorted(_LAYER_POS.items(), key=lambda kv: kv[1])
                       if p <= cap_pos]
        else:
            allowed = None

        # Layer budgets（仅对允许的层分配）
        quotas = [
            ("vehicle", 20),
            ("domain", 60),
            ("subdomain", 400),
            ("module", 2000),
            ("technology", 3000),
            ("material", 4000),
        ]
        nodes: list[dict[str, Any]] = []
        seen_v: set[str] = set()
        truncated = False
        for tag, quota in quotas:
            if allowed is not None and tag not in allowed:
                continue
            if len(nodes) >= limit_nodes:
                truncated = True
                break
            remain = min(quota, limit_nodes - len(nodes))
            if remain <= 0:
                truncated = True
                break
            batch = self.list_vertices(tag=tag, keyword="", limit=remain)
            for n in batch:
                vid = n.get("vid")
                if not vid or vid in seen_v:
                    continue
                seen_v.add(vid)
                nodes.append(n)
                if len(nodes) >= limit_nodes:
                    break
            # 该层若塞满配额而总量仍有余位，则还有更多 → 标记截断
            if len(batch) >= remain:
                truncated = True

        edges: list[dict[str, Any]] = []
        seen_e: set[tuple[str, str, str]] = set()
        remain = limit_edges
        kept_ids = list(seen_v)
        # Chunk kept ids so the IN-list stays within nGQL statement length limits.
        CHUNK = 500
        chunks = [kept_ids[i:i + CHUNK] for i in range(0, len(kept_ids), CHUNK)] or [[]]
        for et in EDGES:
            for chunk in chunks:
                if not chunk:
                    continue
                in_list = ", ".join(f"'{v}'" for v in chunk)
                # 只按 src IN 取边，再在 Python 侧校验 dst ∈ kept —— Nebula 对
                # `id(a) IN [...] AND id(b) IN [...]` 会漏匹配部分边，导致画布出现“孤节点”。
                resp = self.client.execute(
                    f"MATCH (a)-[e:{et}]->(b) "
                    f"WHERE id(a) IN [{in_list}] "
                    f"RETURN src(e) AS src, dst(e) AS dst;"
                )
                for row in rows_as_dicts(resp):
                    src = str(row.get("src") or "").strip("'\"")
                    dst = str(row.get("dst") or "").strip("'\"")
                    if not src or not dst:
                        continue
                    if src not in seen_v or dst not in seen_v:
                        continue
                    key = (src, et, dst)
                    if key in seen_e:
                        continue
                    seen_e.add(key)
                    if remain <= 0:
                        # 配额用尽：超出部分不计入返回（但 return 计数应如实反映截断）
                        truncated = True
                        continue
                    edges.append(
                        {"edge_type": et, "src_vid": src, "dst_vid": dst, "props": {}}
                    )
                    remain -= 1

        return {
            "nodes": nodes,
            "edges": edges,
            "mode": "overview",
            "counts": {"nodes": len(nodes), "edges": len(edges)},
            "truncated": truncated,
            "budget": {"max_nodes": limit_nodes, "max_edges": limit_edges},
        }

    def find_path(self, src: str, dst: str) -> list[Any]:
        src, dst = _sanitize_vid(src), _sanitize_vid(dst)
        try:
            resp = self.client.execute(
                f"FIND SHORTEST PATH FROM '{src}' TO '{dst}' OVER * BIDIRECT "
                f"YIELD path AS p;"
            )
            paths = []
            for row in rows_as_dicts(resp):
                p = row.get("p")
                if isinstance(p, dict) and "nodes" in p:
                    p_nodes = [n for n in (p.get("nodes") or []) if isinstance(n, dict)]
                    # Batch-hydrate full props for all path nodes at once (no N+1).
                    by_id = self._get_vertices_in([n.get("vid") for n in p_nodes])
                    nodes = []
                    for n in p_nodes:
                        full = by_id.get(n.get("vid"))
                        nodes.append(full or n)
                    edges = [e for e in (p.get("edges") or []) if isinstance(e, dict)]
                    paths.append({"nodes": nodes, "edges": edges, "length": len(edges)})
                elif p:
                    paths.append({"raw": str(p)})
            return paths
        except NebulaError:
            return []

    @staticmethod
    def _assert_tag(tag: str) -> None:
        if tag not in TAGS:
            raise ValueError(f"unsupported tag: {tag}; allow {TAGS}")

    @staticmethod
    def _assert_edge(edge_type: str) -> None:
        if edge_type not in EDGES:
            raise ValueError(f"unsupported edge: {edge_type}; allow {EDGES}")

    @staticmethod
    def _filter_props(allowed: tuple[str, ...], props: dict[str, Any]) -> dict[str, Any]:
        return {k: props[k] for k in allowed if k in props and props[k] is not None}
