"""拼接 frontend/vendor/parts/*.partNNN 为完整的前端第三方库文件。

仓库为绕开上传体积限制，把两个较大的第三方库拆成多个 part 存放；
首次运行（或缺失时）由本脚本自动拼回：
  frontend/vendor/3d-force-graph.min.js
  frontend/vendor/vis-network.min.js

无第三方依赖，仅用标准库。幂等：已存在且大小一致则跳过。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "frontend", "vendor")
PARTS = os.path.join(VENDOR, "parts")

TARGETS = ["3d-force-graph.min.js", "vis-network.min.js"]


def assemble(name: str) -> None:
    prefix = name + ".part"
    part_files = sorted(
        f for f in os.listdir(PARTS) if f.startswith(prefix)
    ) if os.path.isdir(PARTS) else []
    if not part_files:
        return
    data = b""
    for f in part_files:
        with open(os.path.join(PARTS, f), "rb") as fh:
            data += fh.read()
    dest = os.path.join(VENDOR, name)
    if os.path.isfile(dest) and os.path.getsize(dest) == len(data):
        print(f"[assemble] up-to-date: {name}")
        return
    with open(dest, "wb") as fh:
        fh.write(data)
    print(f"[assemble] built: {name} ({len(data)} bytes from {len(part_files)} parts)")


def main() -> int:
    if not os.path.isdir(PARTS):
        print(f"[assemble] no parts dir, skip: {PARTS}")
        return 0
    for name in TARGETS:
        assemble(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
