"""按固定 6 层架构选择性导出知识子图（JSON / Markdown）。

场景:
- 整车 → 技术点（root=vehicle, from=vehicle, to=technology）：系统架构概览。
- 某领域 → 文档（root=领域vid, from=domain, to=material）：Agent 深度检索上下文
  （JSON 含 vid / source_url，可用 API 下钻）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend import architecture
from backend.store import GraphStore

_ORDER = architecture.LEVEL_ORDER


class ExportError(ValueError):
    pass


def _layer_rank(tag: str) -> int:
    r = _ORDER.get(tag)
    return r if r is not None else 99


class TreeBuilder:
    """批量加载一次（全部节点 + belongs_to/supports 边），内存 DFS 拼树。"""

    def __init__(self, store: GraphStore, from_rank: int, to_rank: int) -> None:
        self.store = store
        self.from_rank = from_rank
        self.to_rank = to_rank
        self.nodes: dict[str, dict[str, Any]] = {}
        self.kept: dict[str, dict[str, Any]] = {}
        self.child_of: dict[str, list[str]] = {}
        self.supp_of: dict[str, list[str]] = {}
        self.edge_set: set[tuple[str, str, str]] = set()
        self._visited: set[str] = set()

    def load(self) -> None:
        for tag in architecture.LEVELS:
            for n in self.store.list_vertices(tag=tag, keyword="", limit=500):
                vid = n.get("vid")
                if vid:
                    self.nodes[vid] = n
        for s, d in self.store.all_edges("belongs_to"):
            self.child_of.setdefault(d, []).append(s)
        for s, d in self.store.all_edges("supports"):
            self.supp_of.setdefault(d, []).append(s)

    def run(self, root_vid: str) -> None:
        self.root_vid = root_vid
        if root_vid not in self.nodes:
            raise ExportError(f"root 节点不存在: {root_vid}")
        self._visit(root_vid)

    def _visit(self, vid: str) -> None:
        if vid in self._visited:
            return
        self._visited.add(vid)
        node = self.nodes[vid]
        r = _layer_rank(node.get("tag"))
        if self.from_rank <= r <= self.to_rank:
            self.kept[vid] = node
        if r >= self.to_rank:
            return
        for c in self.child_of.get(vid, []):
            if c not in self.nodes:
                continue
            cr = _layer_rank(self.nodes[c].get("tag"))
            if cr > self.to_rank:
                continue
            if self.from_rank <= cr <= self.to_rank:
                self.edge_set.add(("belongs_to", c, vid))
            self._visit(c)
        if node.get("tag") in architecture.SUPPORTS_TARGETS:
            for c in self.supp_of.get(vid, []):
                if c not in self.nodes:
                    continue
                cr = _layer_rank(self.nodes[c].get("tag"))
                if cr > self.to_rank:
                    continue
                if self.from_rank <= cr <= self.to_rank:
                    self.edge_set.add(("supports", c, vid))
                self._visit(c)

    def relates_edges(self) -> list[tuple[str, str, str]]:
        out = []
        try:
            for s, d in self.store.all_edges("relates_to"):
                if s in self.kept and d in self.kept:
                    out.append(("relates_to", s, d))
        except Exception:
            pass
        return out

    def nested(self) -> dict[str, Any] | None:
        if not self.kept:
            return None

        def build(vid: str) -> dict[str, Any]:
            node = dict(self.kept[vid])
            node["children"] = [
                build(c) for c in self.child_of.get(vid, []) if c in self.kept
            ]
            node["materials"] = [
                self.kept[m] for m in self.supp_of.get(vid, []) if m in self.kept
            ]
            return node

        candidates = [getattr(self, "root_vid", None)]
        candidates += [
            v["vid"]
            for v in self.kept.values()
            if v["vid"] not in {d for et, s, d in self.edge_set if et == "belongs_to"}
        ]
        for vid in candidates:
            if vid in self.kept:
                return build(vid)
        vip = None
        for v in self.kept.values():
            r = _layer_rank(v.get("tag"))
            if vip is None or r < _layer_rank(vip.get("tag")):
                vip = v
        return build(vip["vid"]) if vip else None


def _name(node: dict[str, Any]) -> str:
    p = node.get("props") or {}
    raw = p.get("name") or p.get("title") or node.get("vid") or ""
    return " ".join(str(raw).replace("\r", " ").replace("\n", " ").split())


def export_data(store: GraphStore, root_vid: str, from_level: str, to_level: str) -> dict[str, Any]:
    if not architecture.is_level(from_level) or not architecture.is_level(to_level):
        raise ExportError(f"from_level/to_level 必须是 {architecture.LEVELS}")
    if _ORDER[from_level] > _ORDER[to_level]:
        raise ExportError("from_level 不能在 to_level 之下")

    builder = TreeBuilder(store, _ORDER[from_level], _ORDER[to_level])
    builder.load()
    builder.run(root_vid)
    root = builder.nodes[root_vid]

    edges = [
        {"edge_type": et, "src_vid": s, "dst_vid": d}
        for et, s, d in sorted(
            builder.edge_set | set(builder.relates_edges()),
            key=lambda e: (e[0], e[1], e[2]),
        )
    ]

    counted: dict[str, int] = {}
    for n in builder.kept.values():
        tag = n.get("tag")
        counted[tag] = counted.get(tag, 0) + 1

    return {
        "export": {
            "format": "json",
            "architecture_version": architecture.ARCH_SCHEMA["version"],
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "scope": {
                "root_vid": root["vid"],
                "root_name": _name(root),
                "from_level": from_level,
                "to_level": to_level,
            },
            "stats": {"nodes": len(builder.kept), "edges": len(edges)},
            "node_counts": counted,
        },
        "tree": builder.nested(),
        "nodes": sorted(
            builder.kept.values(),
            key=lambda n: (_ORDER.get(n.get("tag"), 99), n.get("vid") or ""),
        ),
        "edges": edges,
    }


def to_markdown(data: dict[str, Any]) -> str:
    exp = data.get("export") or {}
    scope = exp.get("scope") or {}
    lines = [
        "导出信息：",
        f"- 架构版本：{exp.get('architecture_version', '?')}",
        f"- 导出时间：{exp.get('exported_at', '?')}",
        f"- 范围：{scope.get('root_name', '?')}（{scope.get('root_vid', '?')}） {scope.get('from_level', '?')} → {scope.get('to_level', '?')}",
        f"- 统计：节点 {exp.get('stats', {}).get('nodes', 0)} · 边 {exp.get('stats', {}).get('edges', 0)}",
        "",
        "---",
        "",
    ]
    root = data.get("tree")
    if not root:
        return "\n".join(lines) + "（范围内无可导出节点）\n"

    body: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        tag = node.get("tag")
        if tag == "material":
            body.append(f"- 文档：{_name(node)}")
            return
        r = _ORDER.get(tag)
        heading = "#" * ((r + 1) if r is not None else 1)
        body.append(f"{heading} {_name(node)}（{architecture.LEVEL_LABEL.get(tag or '', tag or '')}）")
        p = node.get("props") or {}
        extra = []
        for k in ("description", "keywords", "status"):
            v = str(p.get(k) or "").strip()
            if v:
                extra.append(v)
        if extra:
            body.append(f"  {'；'.join(extra)}")
        for c in node.get("children") or []:
            body.append("")
            walk(c)
        mats = node.get("materials") or []
        if mats:
            if not (node.get("children") or []):
                body.append("")
                body.append("  挂接文档（supports）：")
                for m in sorted(mats, key=lambda x: _name(x)):
                    mp = m.get("props") or {}
                    url = str(mp.get("source_url") or "").strip()
                    extra = (m.get("props") or {}).get("title") or ""
                    seg = _name(m)
                    if extra and str(extra) != _name(m):
                        seg = f"{_name(m)}（{extra}）"
                    line = f"  - {seg}"
                    if url:
                        line += f"  <{url}>"
                    body.append(line)
                body.append("")

    walk(root)
    return "\n".join(lines + body) + "\n"
