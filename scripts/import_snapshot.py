"""把 knowledge_base 下的快照导入到运行中的后端（/import/knowledge）。

用法:
    python scripts/import_snapshot.py knowledge_base/domain_chassis_tech.json --token <写入口令>
    python scripts/import_snapshot.py knowledge_base/domain_chassis_tech.json --dry-run

不加 --token 时仅做 dry_run 校验（不写库）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def post(api: str, path: str, payload: dict, token: str = "") -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(api.rstrip("/") + path, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def main() -> int:
    ap = argparse.ArgumentParser(description="导入知识库快照")
    ap.add_argument("file", help="快照 JSON 路径")
    ap.add_argument("--api", default=os.getenv("KN_API", "http://127.0.0.1:8001"))
    ap.add_argument("--token", default=os.getenv("WRITE_PASSWORD", ""))
    ap.add_argument("--dry-run", action="store_true", help="只校验不写库")
    args = ap.parse_args()

    with open(args.file, encoding="utf-8") as f:
        payload = json.load(f)

    dry = args.dry_run or not args.token
    path = "/import/knowledge" + ("?dry_run=true" if dry else "")
    try:
        res = post(args.api, path, payload, args.token if not dry else "")
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"请求失败: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(res, ensure_ascii=False, indent=2))
    if not res.get("valid", False):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
