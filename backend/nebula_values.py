"""Convert nebula3 Value / ResultSet rows into plain Python."""
from __future__ import annotations

from typing import Any


def _from_node(node: Any) -> dict[str, Any]:
    tags = list(node.tags())
    props: dict[str, Any] = {}
    for tag in tags:
        props.update({k: as_python(v) for k, v in node.properties(tag).items()})
    vid = node.get_id()
    if hasattr(vid, "as_string"):
        vid = vid.as_string()
    else:
        vid = str(vid)
    return {
        "vid": vid,
        "tag": tags[0] if tags else "unknown",
        "props": props,
    }


def _from_relationship(edge: Any) -> dict[str, Any]:
    src = edge.start_vertex_id()
    dst = edge.end_vertex_id()
    if hasattr(src, "as_string"):
        src = src.as_string()
    if hasattr(dst, "as_string"):
        dst = dst.as_string()
    return {
        "edge_type": edge.edge_name(),
        "src_vid": str(src),
        "dst_vid": str(dst),
        "props": {k: as_python(v) for k, v in edge.properties().items()},
    }


def as_python(value: Any) -> Any:
    if value is None:
        return None

    # Already-unwrapped Node / Relationship / Path
    cls = type(value).__name__
    if cls == "Node":
        return _from_node(value)
    if cls == "Relationship":
        return _from_relationship(value)
    if cls == "PathWrapper":
        nodes = [_from_node(n) for n in value.nodes()]
        edges = [_from_relationship(r) for r in value.relationships()]
        return {"nodes": nodes, "edges": edges, "length": len(edges)}

    try:
        if value.is_null():
            return None
        if value.is_bool():
            return value.as_bool()
        if value.is_int():
            return value.as_int()
        if value.is_double():
            return value.as_double()
        if value.is_string():
            return value.as_string()
        if value.is_list():
            return [as_python(v) for v in value.as_list()]
        if value.is_map():
            return {k: as_python(v) for k, v in value.as_map().items()}
        if value.is_set():
            return [as_python(v) for v in value.as_set()]
        if value.is_vertex():
            return _from_node(value.as_node())
        if value.is_edge():
            return _from_relationship(value.as_relationship())
        if hasattr(value, "is_path") and value.is_path():
            return as_python(value.as_path())
    except Exception:
        pass
    return str(value)


def rows_as_dicts(resp) -> list[dict[str, Any]]:
    keys = list(resp.keys())
    out: list[dict[str, Any]] = []
    for i in range(resp.row_size()):
        row = resp.row_values(i)
        out.append({keys[j]: as_python(row[j]) for j in range(len(keys))})
    return out
