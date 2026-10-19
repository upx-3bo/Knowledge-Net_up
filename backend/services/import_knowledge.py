"""按导出同构格式（tree / nodes / edges）批量入库。

冲突策略（已与用户对齐）：
- 节点带 vid：存在则按 vid 指主更新（仅更新载荷给出的属性）；缺失则用该 vid 新建。
- 节点不带 vid：按「父节点 + tag + 名称」精确匹配，同父同名命中 → 视为已存在（可更新）；
  同名存在于其它父下 → 报告冲突（warn，按本文件意图新建副本）；否则自动生成 vid 新建。
- material 按名称全局匹配复用（可同时支撑多个 module/technology）。
- 先 dry-run 校验出计划；存在 error 则拒绝写入。
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from backend import architecture
from backend.store import GraphStore, make_vid

_VID_RE = re.compile(r"[A-Za-z0-9_\-:.]{1,64}")

PROPS_BY_TAG = {
    "vehicle": ("name", "description"),
    "domain": ("name", "description"),
    "subdomain": ("name", "description"),
    "module": ("name", "description", "keywords", "status"),
    "technology": ("name", "description", "keywords", "status"),
    "material": ("name", "material_type", "title", "summary", "source_url", "published_at"),
}


def build_template() -> dict[str, Any]:
    """生成“自说明 + 可导入”的 6 层批量入库模板。

    - 与导出格式同构（tree 嵌套）；顶层 _guide 为使用说明，导入时自动忽略。
    - 已存在节点给 vid（按 vid 指主更新/跳过，不重复创建）；新建节点不填 vid。
    - 模板内两组示例：示例1 新建领域；示例2 在现有领域下新增子域/模块/技术点/文档。
    """
    guide = [
        "本文件 = 6 层架构批量入库模板，与「导出知识架构」同构，可直接上传/粘贴到「导入知识架构」校验后写入。",
        "",
        "用法：复制本文件 → 由本地 Agent 或人工按下面指示编辑 → 回传知识库导入。",
        "",
        "结构规则（必须遵守）：",
        "  1) 层级嵌套顺序：vehicle → domain → subdomain → module → technology；文档 material 放在其支撑点的 materials 列表里。",
        "  2) 已存在的节点【保留 vid】——导入时按 vid 找到它，只更新你写了的属性或跳过，绝不重复创建。",
        "  3) 新建的节点【不要写 vid】——系统按「父节点+层级+名称」定位：同父同名自动复用；否则自动生成 vid 新建。",
        "  4) 同名且父不同的节点会提示“名字冲突”，按本文件意图在指定父下新建副本。",
        "  5) material 只能出现在 module/technology 的 materials 中（支撑关系），不能作为 belongs_to 子节点。",
        "",
        "常用场景怎么填：",
        "  A) 新建领域：在 children 里新增一个 {tag:\"domain\"} 块（仿示例1），嵌套它的子域/模块/技术点/文档。",
        "  B) 现有领域下新增子域/模块/技术点/文档：找到对应的【已存在父节点】（保留其 vid），把新内容嵌进它的 children/materials（仿示例2）。",
        "  C) 只补文档：在某技术点或模块的 materials 里加 {'tag':'material'} 条目。",
        "",
        "字段提示：",
        "  - name（必需，≤48字）；title/summary/source_url 仅 material 用；description/keywords 给领域~技术点用。",
        "  - material_type：doc|paper|patent|news|standard。",
        "  - 导入前先点【校验（预览计划）】必须“校验通过”才能写入；有错误就照报告改。",
        "  - 模板里的两组示例导入前请删除或改名为真实内容，否则会按示例名称写入（仅用于格式自检）。",
    ]
    return {
        "format": "knowledge_import_template",
        "architecture_version": architecture.ARCH_SCHEMA["version"],
        "_guide": guide,
        "tree": {
            "tag": "vehicle",
            "vid": "veh_chassis",
            "props": {"name": "整车"},
            "children": [
                {
                    "tag": "domain",
                    "props": {"name": "【示例1-新建领域】请改名为真实领域名", "description": "领域一句话描述"},
                    "children": [
                        {
                            "tag": "subdomain",
                            "props": {"name": "【示例1-子域】请改名", "description": ""},
                            "children": [
                                {
                                    "tag": "module",
                                    "props": {"name": "【示例1-模块】请改名", "description": "", "keywords": "关键词,逗号分隔", "status": "active"},
                                    "children": [
                                        {"tag": "technology", "props": {"name": "【示例1-技术点】请改名", "description": "一句话描述", "keywords": ""}}
                                    ],
                                    "materials": [
                                        {"tag": "material", "props": {"name": "【示例1-文档】请改名", "material_type": "doc", "title": "", "summary": "", "source_url": ""}}
                                    ],
                                }
                            ],
                        }
                    ],
                },
                {
                    "tag": "domain",
                    "vid": "domain_chassis_tech",
                    "props": {"name": "底盘技术"},
                    "children": [
                        {
                            "tag": "subdomain",
                            "vid": "sub_97f69699bb_3768b5",
                            "props": {"name": "传动系统技术"},
                            "children": [
                                {
                                    "tag": "module",
                                    "props": {"name": "【示例2-现有领域下新增模块】请改名", "description": ""},
                                    "children": [
                                        {
                                            "tag": "technology",
                                            "props": {"name": "【示例2-新增技术点】请改名", "description": ""},
                                            "materials": [
                                                {"tag": "material", "props": {"name": "【示例2-新增文档】请改名", "material_type": "paper", "title": "", "summary": "", "source_url": ""}}
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
            ],
        },
    }


def _clean_props(tag: str, props: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(props, dict):
        for k, v in props.items():
            if v is None or isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                v = str(v)
            out[str(k)] = str(v).strip()
    return {k: v for k, v in out.items() if k in PROPS_BY_TAG[tag]}


def _tree_node(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    tag = str(obj.get("tag") or "")
    if not tag:
        return None
    props = obj.get("props")
    if not isinstance(props, dict):
        v = obj.get("name") or obj.get("title")
        props = {"name": v} if v else {}
    return {
        "vid": str(obj.get("vid") or "").strip() or None,
        "tag": tag,
        "props": _clean_props(tag, props),
        "children": obj.get("children") or [],
        "materials": obj.get("materials") or [],
    }


def parse_payload(payload: Any) -> dict[str, Any]:
    """标准化为 {nodes:[{vid?,tag,props}], edges:[{edge_type,src,dst}]}。

    支持：导出同构 {tree,nodes,edges}、裸嵌套树对象、节点数组。
    旧抽取格式（domain/tech_points）→ 抛错，建议走 /ai/commit。
    """
    if not isinstance(payload, dict):
        raise ValueError("导入文件应为 JSON 对象（导出格式 或 嵌套树）")
    if any(k in payload for k in ("domain", "tech_points")):
        raise ValueError(
            "检测到旧「抽取格式」（domain/tech_points），请改用 6 层导出格式（见「导出知识架构」JSON）。"
        )

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    seen: set[str] = set()
    tree = payload.get("tree")
    nodes_raw = payload.get("nodes")
    edges_raw = payload.get("edges")

    def add_node(n: dict[str, Any]) -> None:
        key = n["vid"] or n["props"].get("name") or ""
        if not key or key in seen:
            return
        seen.add(key)
        nodes.append(n)

    if isinstance(tree, dict):
        stack: list[Any] = [tree]
        while stack:
            t = stack.pop(0)
            n = _tree_node(t)
            if not n:
                continue
            add_node(n)
            stack[:0] = list(n["children"]) + list(n["materials"])

    if isinstance(nodes_raw, list):
        for it in nodes_raw:
            if not isinstance(it, dict):
                continue
            tag = str(it.get("tag") or "")
            props = _clean_props(tag, it.get("props") or it)
            vid = str(it.get("vid") or "").strip() or None
            add_node({"vid": vid, "tag": tag, "props": props, "children": [], "materials": []})
    elif (not isinstance(tree, dict)) and isinstance(payload, dict) and payload.get("tag"):
        t = _tree_node(payload)
        if t:
            add_node(t)

    def add_edge(et: str, src: Any, dst: Any) -> None:
        s = str(src or "").strip()
        d = str(dst or "").strip()
        if s and d:
            edges.append({"edge_type": et, "src": s, "dst": d})

    if isinstance(tree, dict):
        def walk(t: Any, parent_key: str | None = None) -> None:
            n = _tree_node(t)
            if not n:
                return
            key = n["vid"] or n["props"].get("name") or ""
            if parent_key and key:
                add_edge("belongs_to", key, parent_key)
            for c in n["children"]:
                walk(c, key)
            for m in n["materials"]:
                mk = (m.get("vid") or "") if isinstance(m, dict) else ""
                mn = (m.get("props", {}).get("name") if isinstance(m, dict) else "") or ""
                if key and (mk or mn):
                    add_edge("supports", mk or mn, key)
        walk(tree)

    if isinstance(edges_raw, list):
        for e in edges_raw:
            if not isinstance(e, dict):
                continue
            et = str(e.get("edge_type") or "")
            if et not in ("belongs_to", "supports", "relates_to"):
                continue
            add_edge(et, e.get("src") or e.get("src_vid"), e.get("dst") or e.get("dst_vid"))

    # 节点去重（同 vid 或同 名称）
    uniq: dict[str, dict[str, Any]] = {}
    for n in nodes:
        key = n["vid"] or n["props"].get("name") or ""
        if key and key not in uniq:
            uniq[key] = n
    # 边去重
    edge_seen: set[tuple[str, str, str]] = set()
    uniq_edges: list[dict[str, str]] = []
    for e in edges:
        k = (e["edge_type"], e["src"], e["dst"])
        if k in edge_seen:
            continue
        edge_seen.add(k)
        uniq_edges.append(e)
    return {"nodes": list(uniq.values()), "edges": uniq_edges}


class Importer:
    def __init__(self, store: GraphStore) -> None:
        self.store = store
        self.nodes_by_vid: dict[str, dict[str, Any]] = {}
        self.parent_of: dict[str, str] = {}
        self.by_parent_name: dict[tuple, list[str]] = defaultdict(list)
        self.by_name: dict[tuple, list[str]] = defaultdict(list)  # (tag,name) -> vids

    def _load_existing(self) -> None:
        for tag in architecture.LEVELS:
            for n in self.store.list_vertices(tag=tag, keyword="", limit=2000):
                self.nodes_by_vid[n["vid"]] = n
        for s, d in self.store.all_edges("belongs_to"):
            self.parent_of[s] = d
        for vid, n in self.nodes_by_vid.items():
            props = n.get("props") or {}
            name = props.get("name")
            tag = n.get("tag")
            if not name:
                continue
            if tag:
                self.by_name[(tag, str(name))].append(vid)
                par = self.parent_of.get(vid)
                if par or tag == "vehicle":
                    self.by_parent_name[(par or "", tag, str(name))].append(vid)

    def plan(self, payload: Any) -> dict[str, Any]:
        self._load_existing()
        parsed = parse_payload(payload)
        nodes = parsed["nodes"]
        edges = parsed["edges"]
        issues: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        summary = {"create": 0, "update": 0, "link": 0, "skip": 0}

        def issue(ref: str, severity: str, kind: str, message: str) -> None:
            issues.append({"ref": ref, "severity": severity, "kind": kind, "message": message})

        # 找出每个节点的 belongs_to 父 key
        parent_key_of: dict[str, str | None] = {}
        keys = [str(n["vid"] or n["props"].get("name") or "") for n in nodes]
        keyset = set(keys)
        for n in nodes:
            key = str(n["vid"] or n["props"].get("name") or "")
            parent_key_of[key] = None
            for e in edges:
                if e["edge_type"] == "belongs_to" and str(e.get("src") or "") == key:
                    pk = str(e.get("dst") or "")
                    if pk in keyset or pk in self.nodes_by_vid:
                        parent_key_of[key] = pk

        # 拓扑：父先解析（父存在或为本文件节点）
        resolved: dict[str, str] = {}
        new_plan: dict[tuple, str] = {}
        ref_of: dict[str, str] = {}

        remaining = list(nodes)
        while remaining:
            progressed = False
            for n in remaining[:]:
                key = str(n["vid"] or n["props"].get("name") or "")
                pk = parent_key_of.get(key)
                if pk is not None and pk not in resolved and pk not in self.nodes_by_vid:
                    continue  # 父尚未就绪
                remaining.remove(n)
                progressed = True
                self._resolve_node(n, pk, resolved, new_plan, ref_of, actions, summary, issues)
            if not progressed:
                for n in remaining:
                    key = str(n["vid"] or n["props"].get("name") or "")
                    pk = parent_key_of.get(key)
                    issue(f"node:{key}", "error", "dangling_parent",
                          f"父节点无法解析（可能成环或缺失）: parent={pk}")
                break

        # 边
        for e in edges:
            et = e["edge_type"]
            s, d = e["src"], e["dst"]
            sv = resolved.get(s) or (s if s in self.nodes_by_vid else None)
            dv = resolved.get(d) or (d if d in self.nodes_by_vid else None)
            if not sv or not dv:
                issue(f"edge:{et} {s}->{d}", "error", "dangling", f"边端点无法解析: {et} {s}->{d}")
                continue
            if sv == dv:
                issue(f"edge:{et} {s}->{d}", "error", "self_loop", "自环边")
                continue
            st = self._tag_of(sv, ref_of)
            dt = self._tag_of(dv, ref_of)
            if et == "belongs_to":
                if st == "material":
                    issue(f"edge:{et} {s}->{d}", "error", "material_belongs_to", "material 不允许 belongs_to")
                    continue
                if st not in architecture.BELONGS_TO_PARENT or dt not in architecture.BELONGS_TO_PARENT[st]:
                    issue(f"edge:{et} {s}->{d}", "error", "wrong_layer",
                          f"[{st}] 的父应为 {architecture.BELONGS_TO_PARENT.get(st)}，实际 [{dt}]")
                    continue
            elif et == "supports":
                if st != "material":
                    issue(f"edge:{et} {s}->{d}", "error", "supports_from_non_material", "supports 只能由 material 发出")
                    continue
                if dt not in architecture.SUPPORTS_TARGETS:
                    issue(f"edge:{et} {s}->{d}", "error", "wrong_supports_target",
                          f"material 只能支撑 {architecture.SUPPORTS_TARGETS}")
                    continue
            summary["link"] += 1
            actions.append({"ref": f"edge:{et} {s}->{d}", "tag": "", "vid": "", "name": "",
                            "action": "link",
                            "link": {"edge_type": et, "src_vid": sv, "dst_vid": dv}})

        errors = sum(1 for i in issues if i["severity"] == "error")
        return {
            "valid": errors == 0,
            "errors": errors,
            "warns": sum(1 for i in issues if i["severity"] == "warn"),
            "issues": issues,
            "actions": actions,
            "summary": summary,
        }

    def _resolve_node(
        self,
        n: dict[str, Any],
        pk: str | None,
        resolved: dict[str, str],
        new_plan: dict[tuple, str],
        ref_of: dict[str, str],
        actions: list[dict[str, Any]],
        summary: dict[str, int],
        issues: list[dict[str, Any]],
    ) -> None:
        tag = n["tag"]
        props = n["props"]
        name = str(props.get("name") or props.get("title") or "").strip()
        vid = n["vid"]
        key = vid or name
        ref = f"node:{key}"
        if tag not in architecture.LEVELS:
            issues.append({"ref": ref, "severity": "error", "kind": "bad_tag", "message": f"未知层级 {tag!r}"})
            return
        if not name:
            issues.append({"ref": ref, "severity": "error", "kind": "no_name", "message": "缺少名称（name/title）"})
            return

        if vid:
            if not _VID_RE.fullmatch(vid):
                issues.append({"ref": ref, "severity": "error", "kind": "bad_vid", "message": f"vid 不合法: {vid!r}"})
                return
            resolved[key] = vid
            ref_of[vid] = tag
            self._append_node_action(n, vid, actions, summary, issues)
            return

        parent_vid = resolved.get(pk) if pk else None
        matched = None
        others = []
        if parent_vid is not None or tag == "vehicle":
            candidates = self.by_parent_name.get((parent_vid or "", tag, name), [])
            if candidates:
                matched = candidates[0]
        all_same_name = self.by_name.get((tag, name), [])
        others = [v for v in all_same_name if v != matched]
        if matched:
            resolved[key] = matched
            ref_of[matched] = tag
            self._append_node_action(n, matched, actions, summary, issues, parent_vid=parent_vid)
            return
        if others:
            issues.append({"ref": ref, "severity": "warn", "kind": "name_conflict",
                           "message": f"同名「{name}」已存在于其它父下（{', '.join(others)}），将按本文件意图新建副本"})
        k = (tag, name)
        if k in new_plan:
            resolved[key] = new_plan[k]
            ref_of[new_plan[k]] = tag
            issue_ref = f"node:{name}"
            issues.append({"ref": issue_ref, "severity": "warn", "kind": "duplicate", "message": "文件内重复条目，复用前面节点"})
            actions.append({"ref": ref, "tag": tag, "vid": new_plan[k], "name": name,
                            "action": "skip", "new_props": dict(props)})
            summary["skip"] += 1
            return
        new_vid = make_vid(architecture.VID_PREFIX[tag])
        new_plan[k] = new_vid
        resolved[key] = new_vid
        ref_of[new_vid] = tag
        summary["create"] += 1
        actions.append({"ref": ref, "tag": tag, "vid": new_vid, "name": name,
                        "action": "create", "new_props": dict(props)})

    def _append_node_action(
        self,
        n: dict[str, Any],
        vid: str,
        actions: list[dict[str, Any]],
        summary: dict[str, int],
        issues: list[dict[str, Any]],
        parent_vid: str | None = None,
    ) -> None:
        existing = self.nodes_by_vid.get(vid)
        props = n["props"]
        name = str(props.get("name") or "?")
        tag = n["tag"]
        ref = f"node:{vid}"
        if not existing:
            summary["create"] += 1
            actions.append({"ref": ref, "tag": tag, "vid": vid, "name": name,
                            "action": "create", "new_props": dict(props)})
            return
        old = existing.get("props") or {}
        diff = {k: v for k, v in props.items() if old.get(k) != v and v != ""}
        if diff:
            summary["update"] += 1
            actions.append({"ref": ref, "tag": tag, "vid": vid, "name": name,
                            "action": "update", "new_props": dict(props), "changed": list(diff.keys())})
        else:
            summary["skip"] += 1
            actions.append({"ref": ref, "tag": tag, "vid": vid, "name": name,
                            "action": "skip", "new_props": dict(props)})

    def _tag_of(self, vid: str, ref_of: dict[str, str]) -> str:
        n = self.nodes_by_vid.get(vid)
        if n:
            return n.get("tag") or ""
        return ref_of.get(vid, "")

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        if not plan.get("valid"):
            return {"ok": False, "summary": plan.get("summary", {}),
                    "issues": plan.get("issues", []), "message": "存在校验 error，拒绝写入"}
        created = updated = linked = skipped = 0
        failures: list[str] = []
        for a in plan.get("actions", []):
            act = a.get("action")
            if act == "create":
                try:
                    self.store.insert_vertex(a["tag"], a["vid"], a.get("new_props") or {})
                    created += 1
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{a.get('ref')}: {exc}")
            elif act == "update":
                try:
                    self.store.update_vertex(a["vid"], a.get("new_props") or {})
                    updated += 1
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{a.get('ref')}: {exc}")
            elif act == "skip":
                skipped += 1
        for a in plan.get("actions", []):
            if a.get("action") != "link":
                continue
            ln = a.get("link") or {}
            try:
                self.store.insert_edge(ln["edge_type"], ln["src_vid"], ln["dst_vid"])
                linked += 1
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{a.get('ref')}: {exc}")
        return {"ok": not failures, "failures": failures,
                "summary": {"created": created, "updated": updated, "linked": linked, "skipped": skipped}}
