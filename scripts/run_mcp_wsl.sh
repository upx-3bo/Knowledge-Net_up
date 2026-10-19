#!/usr/bin/env bash
set -euo pipefail
ROOT="/mnt/c/Users/Administrator/Desktop/up_x/AI4KnowledgeNet"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export NEBULA_HOST=127.0.0.1
export NEBULA_PORT=9669
export NEBULA_USER=root
export NEBULA_PASSWORD=
export NEBULA_SPACE=auto_innovation_kg
exec python3 -m mcp_server.server
