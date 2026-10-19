# -*- coding: utf-8 -*-
"""全库核对固定 6 层架构（ARCH_SCHEMA）合规性。

用法:
  python scripts/audit_architecture.py            # 简要报告（exit code: 0 合规 / 2 有 error）
  python scripts/audit_architecture.py --detail   # 逐条打印问题明细
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from nebula3.Config import Config  # noqa: E402
from nebula3.gclient.net import ConnectionPool  # noqa: E402

from backend import architecture  # noqa: E402
from backend.config import NEBULA_HOST, NEBULA_PASSWORD, NEBULA_PORT, NEBULA_SPACE, NEBULA_USER  # noqa: E402


def _connect():
    cfg = Config()
    cfg.max_connection_pool_size = 4
    pool = ConnectionPool()
    if not pool.init([(NEBULA_HOST, NEBULA_PORT)], cfg):
        raise RuntimeError(f"cannot connect {NEBULA_HOST}:{NEBULA_PORT}")
    sess = pool.get_session(NEBULA_USER, NEBULA_PASSWORD)
    sess.execute(f"USE {NEBULA_SPACE};")
    return pool, sess


def _j(sess, nql):
    raw = sess.execute_json(nql)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        raw = json.loads(raw)
    out = []
    for res in raw.get("results", []):
        for d in res.get("data") or []:
            out.append(d)
    return out


def load_graph(sess):
    nodes = []
    for tag in architecture.LEVELS:
        for d in _j(sess, f"MATCH (v:{tag}) RETURN id(v) AS vid, v AS node;"):
            row = d.get("row") or []
            if len(row) < 2:
                continue
            vid, node = row[0], row[1]
            props = {}
            if isinstance(node, dict):
                for k, val in node.items():
                    key = k.split(".", 1)[1] if "." in k else k
                    props[key] = val
            nodes.append({"vid": str(vid).strip("'\""), "tag": tag, "props": props})
    edges = []
    for et in ("belongs_to", "supports", "relates_to"):
        for d in _j(sess, f"MATCH ()-[e:{et}]->() RETURN src(e) AS s, dst(e) AS d;"):
            row = d.get("row") or []
            if len(row) < 2:
                continue
            edges.append(
                {
                    "edge_type": et,
                    "src_vid": str(row[0]).strip("'\""),
                    "dst_vid": str(row[1]).strip("'\""),
                }
            )
    return nodes, edges


def main(argv):
    detail = "--detail" in argv
    pool, sess = _connect()
    try:
        nodes, edges = load_graph(sess)
    finally:
        try:
            sess.release()
            pool.close()
        except Exception:
            pass

    result = architecture.check_hierarchy(nodes, edges)
    st = result["stats"]
    print("== 节点分布 ==")
    for t, c in st["nodes"].items():
        print(f"  {t:<12} {c}")
    print("== 边分布 ==")
    for t, c in st["edges"].items():
        print(f"  {t:<12} {c}")
    print(f"\n架构版本: {architecture.ARCH_SCHEMA['version']}")
    print(f"errors={result['errors']}  warns={result['warns']}")
    if result["summary"]:
        print("问题分布:", result["summary"])

    issues = result["issues"]
    if detail and issues:
        print("\n== 问题明细 ==")
        for i in issues:
            line = f"[{i['severity']}] {i['kind']}  {i.get('tag')} {i.get('vid')}: {i.get('message')}"
            if i.get("refs"):
                line += "  refs=" + ",".join(i["refs"])
            print(line)
    print("\n结论:", "合规（通过）" if result["ok"] else "存在不符合固定架构的 error，需要处理")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
