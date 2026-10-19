# -*- coding: utf-8 -*-
"""每日图数据变更检测 + 快照备份（同步到 scripts/snapshots）。

用法:
  python scripts/backup_daily.py            # 有变更才导出新快照
  python scripts/backup_daily.py --force    # 无论是否变更都导出
  python scripts/backup_daily.py --check    # 仅检查是否发生变更，不导出

可选离线冗余：设环境变量 BACKUP_SHARE_DIR=<共享路径> 时，
每次导出后会把最新快照复制一份到该目录（异地/共享盘）向后兼容。
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import snapshot as snap  # 复用快照的 TAGS/EDGES/_j/export

SNAP_DIR = SCRIPT_DIR + os.sep + "snapshots"
STATE_FILE = os.path.join(SNAP_DIR, ".last_fingerprint.json")
SHARE_DIR = os.environ.get("BACKUP_SHARE_DIR", "").strip()


def _cnt(nql: str, sess) -> int:
    rows = snap._j(sess, nql)
    for d in rows:
        row = d.get("row", [])
        if row:
            val = row[0]
            if isinstance(val, (int, float)):
                return int(val)
            s = str(val).strip().strip('"\'')
            if s.isdigit():
                return int(s)
    return 0


def fingerprint(sess) -> dict:
    """基于节点/边量的粗粒度指纹，用于判定图谱是否发生变更。"""
    fp = {}
    for t in snap.TAGS:
        fp[f"v:{t}"] = _cnt(f"MATCH (v:{t}) RETURN count(v) AS c;", sess)
    for e in snap.EDGES:
        fp[f"e:{e}"] = _cnt(f"MATCH ()-[x:{e}]->() RETURN count(x) AS c;", sess)
    return fp


def main() -> None:
    force = "--force" in sys.argv
    only_check = "--check" in sys.argv
    os.makedirs(SNAP_DIR, exist_ok=True)

    pool, sess = snap._connect()
    try:
        fp = fingerprint(sess)
    finally:
        try:
            sess.release()
            pool.close()
        except Exception:
            pass

    prev = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}

    changed = prev.get("fingerprint") != fp
    total = sum(v for v in fp.values())
    print("指纹:", fp, "共", total, "个图元")
    print("变更:", "是" if changed else "否")

    if only_check:
        return

    if not force and not changed:
        print("图谱未变化，跳过本次快照导出")
        return

    snap.export(out_path=None)  # 写入 SNAP_DIR/snapshot_<时间戳>.json
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"fingerprint": fp, "updated_at": datetime.now().isoformat(timespec="seconds")},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print("指纹已更新:", STATE_FILE)

    if SHARE_DIR:
        newest = sorted(glob.glob(os.path.join(SNAP_DIR, "snapshot_*.json")))
        if newest:
            os.makedirs(SHARE_DIR, exist_ok=True)
            for f in newest[-3:]:  # 保留最近 3 份在共享目录
                shutil.copy2(f, os.path.join(SHARE_DIR, os.path.basename(f)))
            print("已同步至共享目录:", SHARE_DIR)


if __name__ == "__main__":
    main()
