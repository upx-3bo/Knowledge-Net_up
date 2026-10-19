# -*- coding: utf-8 -*-
"""NebulaGraph 全图快照备份 / 回滚脚本（方案A）- 基于 execute_json

用法:
  python snapshot.py export
  python snapshot.py list
  python snapshot.py import snap.json [--dry-run]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool

from backend.config import NEBULA_HOST, NEBULA_PASSWORD, NEBULA_PORT, NEBULA_SPACE, NEBULA_USER

TAGS = ("domain", "subdomain", "technology", "material")
EDGES = ("belongs_to", "supports", "relates_to")
SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")


def _connect():
    cfg = Config()
    cfg.max_connection_pool_size = 8
    pool = ConnectionPool()
    if not pool.init([(NEBULA_HOST, NEBULA_PORT)], cfg):
        raise RuntimeError(f"cannot connect {NEBULA_HOST}:{NEBULA_PORT}")
    sess = pool.get_session(NEBULA_USER, NEBULA_PASSWORD)
    sess.execute(f"USE {NEBULA_SPACE};")
    return pool, sess


def _j(sess, nql):
    """run nGQL and return parsed JSON results"""
    raw = sess.execute_json(nql)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        raw = json.loads(raw)
    results = raw.get("results", []) if isinstance(raw, dict) else []
    rows = []
    for res in results:
        for d in (res.get("data") or []):
            rows.append(d)
    return rows


def _strip(s):
    return str(s).strip("'\"") if s is not None else ""


def export(out_path=None):
    pool, sess = _connect()
    try:
        data = {
            "space": NEBULA_SPACE,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "vertices": [],
            "edges": [],
        }
        rows = _j(sess, "SHOW TAGS;")
        tags = []
        for d in rows:
            for cell in d.get("row", []):
                t = _strip(cell)
                if t and t not in tags:
                    tags.append(t)
        if not tags:
            tags = list(TAGS)
        print("tags:", tags)
        for tag in tags:
            resp_rows = _j(sess, f"MATCH (v:{tag}) RETURN id(v) AS vid, v AS node;")
            for d in resp_rows:
                row = d.get("row", [])
                if len(row) < 2:
                    continue
                vid = _strip(row[0])
                node = row[1]
                props = {}
                if isinstance(node, dict):
                    for k, val in node.items():
                        # k like 'domain.name' -> strip tag prefix
                        key = k.split(".", 1)[1] if "." in k else k
                        props[key] = val
                data["vertices"].append({"tag": tag, "vid": vid, "props": props})
        for et in EDGES:
            resp_rows = _j(sess, f"MATCH ()-[e:{et}]->() RETURN src(e) AS src, dst(e) AS dst, e AS e;")
            for d in resp_rows:
                row = d.get("row", [])
                if len(row) < 3:
                    continue
                src = _strip(row[0])
                dst = _strip(row[1])
                props = {}
                if isinstance(row[2], dict):
                    for k, val in row[2].items():
                        key = k.split(".", 1)[1] if "." in k else k
                        props[key] = val
                data["edges"].append({"edge_type": et, "src_vid": src, "dst_vid": dst, "props": props})
        if not out_path:
            os.makedirs(SNAP_DIR, exist_ok=True)
            out_path = os.path.join(SNAP_DIR, f"snapshot_{datetime.now():%Y%m%d_%H%M%S}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"已导出 {len(data['vertices'])} 节点, {len(data['edges'])} 边 -> {out_path}")
    finally:
        sess.release()
        pool.close()


def list_snapshots():
    os.makedirs(SNAP_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SNAP_DIR, "*.json")))
    if not files:
        print("暂无快照")
        return
    print("现有快照:")
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
            sz = os.path.getsize(f) // 1024
            print(f"  {os.path.basename(f)}  ({sz}KB, {len(d.get('vertices',[]))}节点/{len(d.get('edges',[]))}边)")
        except Exception:
            print(f"  {os.path.basename(f)}  (不可读)")


def _escape(v):
    if v is None:
        return "''"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"


def import_snapshot(path, dry_run=False):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    verts = data.get("vertices", [])
    edges = data.get("edges", [])
    if dry_run:
        print(f"[预演] 将导入 {len(verts)} 节点, {len(edges)} 边")
        return
    pool, sess = _connect()
    try:
        sess.execute("DELETE VERTEX (MATCH (v) RETURN id(v)) WITH EDGE;")
        nv = 0
        for v in verts:
            tag, vid = v.get("tag"), v.get("vid")
            props = v.get("props", {})
            if not tag or not vid:
                continue
            if props:
                cols = ", ".join(props.keys())
                vals = ", ".join(_escape(val) for val in props.values())
                sess.execute(f"INSERT VERTEX IF NOT EXISTS {tag}({cols}) VALUES '{vid}': ({vals});")
            else:
                sess.execute(f"INSERT VERTEX IF NOT EXISTS {tag}() VALUES '{vid}': ();")
            nv += 1
        ne = 0
        for e in edges:
            if e.get("edge_type") not in EDGES:
                continue
            src, dst = e.get("src_vid"), e.get("dst_vid")
            if not src or not dst:
                continue
            props = e.get("props", {})
            if props:
                cols = ", ".join(props.keys())
                vals = ", ".join(_escape(val) for val in props.values())
                sess.execute(f"INSERT EDGE IF NOT EXISTS {e['edge_type']}({cols}) VALUES '{src}' -> '{dst}': ({vals});")
            else:
                sess.execute(f"INSERT EDGE IF NOT EXISTS {e['edge_type']}() VALUES '{src}' -> '{dst}': ();")
            ne += 1
        print(f"已回滚导入 {nv} 节点, {ne} 边")
    finally:
        sess.release()
        pool.close()


def main():
    ap = argparse.ArgumentParser(description="NebulaGraph 快照备份/回滚")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export"); e.add_argument("--out", default=None)
    sub.add_parser("list")
    im = sub.add_parser("import"); im.add_argument("path"); im.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cmd == "export":
        export(out_path=args.out)
    elif args.cmd == "list":
        list_snapshots()
    elif args.cmd == "import":
        import_snapshot(args.path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
