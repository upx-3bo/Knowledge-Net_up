# -*- coding: utf-8 -*-
"""打包可分发副本：源码 + 数据快照 + 文档，排除体积大/隐私目录。

用法:
  python scripts/package_release.py [--out 输出zip路径] [--include-native]
  --include-native  额外纳入 infra/nebula/native（原生二进制，约240MB；无 Docker 时用）
"""
from __future__ import annotations

import argparse
import os
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 总是包含的顶层条目
INCLUDE_TOPLVL = [
    "backend", "frontend", "scripts", "mcp_server", "docs",
    "README.md", "REPLICATE.md", "requirements.txt", ".env.example", ".gitignore",
    "infra",
]

# 需要剔除的子路径（相对 ROOT，目录名即整目录剔除）
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache",
    "out.txt", "err.txt",
}
# 进入 infra 时只保留这些
INFRA_KEEP = {"nebula"}
# infra/nebula 下剔除的目录（原生二进制体积大）
NEBULA_EXCLUDE = {"native"}


def walk_rel(top: str, exclude: set[str]):
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = [d for d in dirnames if d not in exclude and not d.startswith(".")]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            yield full


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dist", "AI4KnowledgeNet_release.zip"))
    ap.add_argument("--include-native", action="store_true")
    args = ap.parse_args()

    out_dir = os.path.dirname(args.out)
    os.makedirs(out_dir, exist_ok=True)
    if os.path.exists(args.out):
        os.remove(args.out)

    included = 0
    bytes_total = 0
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for entry in INCLUDE_TOPLVL:
            src = os.path.join(ROOT, entry)
            if not os.path.exists(src):
                continue
            if entry == "infra":
                for sub in INFRA_KEEP:
                    s2 = os.path.join(src, sub)
                    if not os.path.exists(s2):
                        continue
                    keep = set(NEBULA_EXCLUDE)
                    if args.include_native:
                        keep = set()
                    for full in walk_rel(s2, keep):
                        rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
                        z.write(full, rel)
                        included += 1
                        bytes_total += os.path.getsize(full)
                continue
            if entry in ("backend", "frontend", "scripts", "mcp_server", "docs"):
                for full in walk_rel(src, EXCLUDE_DIRS):
                    rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
                    z.write(full, rel)
                    included += 1
                    bytes_total += os.path.getsize(full)
            else:  # 普通文件
                rel = entry.replace(os.sep, "/")
                z.write(src, rel)
                included += 1
                bytes_total += os.path.getsize(src)

    print(f"已打包 {included} 个文件, 共 {bytes_total/1024/1024:.1f} MB -> {args.out}")


if __name__ == "__main__":
    main()
