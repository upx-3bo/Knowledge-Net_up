#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install --break-system-packages --ignore-installed idna \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  'mcp==1.12.4'
python3 - <<'PY'
from mcp.server.fastmcp import FastMCP
print("fastmcp_ok")
PY
