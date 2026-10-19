"""固定 6 层架构（ARCH_SCHEMA）——导入/导出/表单/校验的单一事实来源。

层级顺序:
    vehicle(0) -> domain(1) -> subdomain(2) -> module(3) -> technology(4) -> material(5)

规则:
- belongs_to = 严格单父树：domain..technology 每层恰好 1 个父，层类型固定；
  vehicle 是唯一根（无父）；material 禁止使用 belongs_to。
- material 通过 supports 挂接，目标允许 module / technology（多对多）。
- 层不必填满：某棵子树最高只到 module 也合法（兼容旧式形态）。
- relates_to 为平级关联，不限层级。
"""
from __future__ import annotations

from typing import Any, Iterable

LEVELS: tuple[str, ...] = (
    "vehicle",
    "domain",
    "subdomain",
    "module",
    "technology",
    "material",
)

LEVEL_ORDER: dict[str, int] = {name: i for i, name in enumerate(LEVELS)}

LEVEL_LABEL: dict[str, str] = {
    "vehicle": "整车/车辆",
    "domain": "领域",
    "subdomain": "子域",
    "module": "模块",
    "technology": "技术点",
    "material": "文档",
}

# belongs_to 每层允许的父类型（顺序即建议校验次序；空元组表示禁止/无父）
BELONGS_TO_PARENT: dict[str, tuple[str, ...]] = {
    "vehicle": (),
    "domain": ("vehicle",),
    "subdomain": ("domain",),
    "module": ("subdomain",),
    "technology": ("module",),
    "material": (),
}

# supports：material 允许支撑的目标层
SUPPORTS_TARGETS: tuple[str, ...] = ("module", "technology")

# belongs_to 反向（每层允许的直属子层），由 BELONGS_TO_PARENT 推导
BELONGS_TO_CHILDREN: dict[str, tuple[str, ...]] = {
    parent: tuple(c for c, ps in BELONGS_TO_PARENT.items() if parent in ps)
    for parent in LEVELS
}

# 建节点 vid 前缀（与现有库内多数数据一致，如 tec_）
VID_PREFIX: dict[str, str] = {
    "vehicle": "veh",
    "domain": "dom",
    "subdomain": "sub",
    "module": "mod",
    "technology": "tec",
    "material": "mat",
}

ARCH_SCHEMA: dict[str, Any] = {
    "version": "1.0",
    "levels": list(LEVELS),
    "level_order": dict(LEVEL_ORDER),
    "level_label": dict(LEVEL_LABEL),
    "belongs_to_parent": {k: list(v) for k, v in BELONGS_TO_PARENT.items()},
    "belongs_to_children": {k: list(v) for k, v in BELONGS_TO_CHILDREN.items()},
    "supports_targets": list(SUPPORTS_TARGETS),
    "vid_prefix": dict(VID_PREFIX),
}


def is_level(value: str) -> bool:
    return value in LEVEL_ORDER


def parent_tags(tag: str) -> tuple[str, ...]:
    """belongs_to 允许的父类型；material 返回 supports 目标类型（挂接对象）。"""
    if tag == "material":
        return SUPPORTS_TARGETS
    return BELONGS_TO_PARENT.get(tag, ())


def child_tags(tag: str) -> tuple[str, ...]:
    """允许作为『下层』的类型：belongs_to 子层 + （若本层是 supports 目标）document。"""
    out = list(BELONGS_TO_CHILDREN.get(tag, ()))
    if tag in SUPPORTS_TARGETS:
        out.append("material")
    return tuple(out)


class HierarchyIssue(dict):
    pass


def check_hierarchy(
    nodes: Iterable[dict[str, Any]],
    edges: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """校验一批节点/边是否符合 ARCH_SCHEMA。

    输入:
      nodes: [{"vid", "tag", "props"}]（props 可空）
      edges: [{"edge_type", "src_vid", "dst_vid"}]（belongs_to/supports 方向 child->parent）
    返回:
      {"ok", "summary": {类型->计数}, "issues": [{kind, severity, tag, vid, message, refs}],
       "stats": {node 按层计数, edge 按类型计数}}
    """
    tags: dict[str, str] = {}
    for n in nodes:
        vid = str(n.get("vid") or "")
        tag = str(n.get("tag") or "")
        if vid:
            tags[vid] = tag

    belongs: list[tuple[str, str]] = []      # (child, parent)
    supports: list[tuple[str, str]] = []     # (material, target)
    count_e: dict[str, int] = {"belongs_to": 0, "supports": 0, "relates_to": 0, "other": 0}
    for e in edges:
        et = str(e.get("edge_type") or "")
        s = str(e.get("src_vid") or "")
        d = str(e.get("dst_vid") or "")
        count_e[et if et in count_e else "other"] += 1
        if et == "belongs_to":
            belongs.append((s, d))
        elif et == "supports":
            supports.append((s, d))

    parents_c: dict[str, list[str]] = {}
    children_of: dict[str, list[str]] = {}
    for s, d in belongs:
        parents_c.setdefault(s, []).append(d)
        children_of.setdefault(d, []).append(s)

    count_v: dict[str, int] = {}
    for t in tags.values():
        count_v[t] = count_v.get(t, 0) + 1

    issues: list[dict[str, Any]] = []

    def add(kind: str, severity: str, vid: str, message: str, refs: list[str] | None = None) -> None:
        issues.append(
            {
                "kind": kind,
                "severity": severity,
                "tag": tags.get(vid, ""),
                "vid": vid,
                "message": message,
                "refs": refs or [],
            }
        )

    for src, dst in belongs:
        st = tags.get(src)
        dt = tags.get(dst)
        if st is None:
            add("dangling_src", "error", src, f"belongs_to 起点不存在: {src} -> {dst}")
            continue
        if dt is None:
            add("dangling_parent", "error", src, f"belongs_to 父节点不存在: {src} -> {dst}")
            continue
        if st == "material":
            add("material_belongs_to", "error", src, f"material 禁止 belongs_to: {src} -> {dst}")
            continue
        if st == "vehicle":
            add("wrong_parent_for_vehicle", "error", src, f"vehicle 是根，不得有父: {src} -> {dst}")
            continue
        if st not in BELONGS_TO_PARENT or dt not in BELONGS_TO_PARENT[st]:
            add(
                "wrong_parent_layer",
                "error",
                src,
                f"[{st}] 的父应为 {BELONGS_TO_PARENT.get(st, ())}，实际为 [{dt}]: {src} -> {dst}",
            )

    for vid, tag in tags.items():
        ps = parents_c.get(vid)
        if tag == "material":
            if ps:
                # 已在上面报 material_belongs_to
                continue
            if not any(s == vid for s, _ in supports):
                add("isolated_material", "warn", vid, "文档未挂到任何 module/technology（孤立）")
            continue
        if tag == "vehicle":
            if vid in parents_c:
                add("vehicle_as_child", "error", vid, "vehicle 是根，不应有父节点")
            continue
        if not ps:
            add("orphan", "error", vid, f"[{tag}] 缺少 belongs_to 父节点（应恰 1 个）")
        elif len(ps) > 1:
            add("multi_parent", "error", vid, f"[{tag}] 有 {len(ps)} 个父节点（应恰 1 个）")

    for src, dst in supports:
        st = tags.get(src)
        dt = tags.get(dst)
        if st is None:
            add("dangling_src", "error", src, f"supports 起点不存在: {src} -> {dst}")
            continue
        if dt is None:
            add("dangling_target", "error", src, f"supports 目标不存在: {src} -> {dst}")
            continue
        if st != "material":
            add(
                "supports_from_non_material",
                "warn",
                src,
                f"supports 通常由 material 发出，实际 [{st}] -> [{dt}]",
            )
        if st == "material" and dt not in SUPPORTS_TARGETS:
            add(
                "wrong_supports_target",
                "error",
                src,
                f"material 支撑目标应为 {SUPPORTS_TARGETS}，实际为 [{dt}]",
            )

    summary: dict[str, int] = {}
    for i in issues:
        summary[i["kind"]] = summary.get(i["kind"], 0) + 1
    errors = sum(1 for i in issues if i["severity"] == "error")
    warns = sum(1 for i in issues if i["severity"] == "warn")
    return {
        "ok": errors == 0,
        "errors": errors,
        "warns": warns,
        "summary": summary,
        "issues": issues,
        "stats": {"nodes": count_v, "edges": count_e},
    }
