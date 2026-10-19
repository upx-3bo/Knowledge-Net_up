#!/usr/bin/env bash
set -euo pipefail
ROOT="/mnt/c/Users/Administrator/Desktop/up_x/AI4KnowledgeNet"
cd "$ROOT"
export PYTHONPATH="$ROOT"

# 加载项目 .env（含 LLM_API_KEY）；兼容 Windows CRLF
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(sed 's/\r$//' "$ROOT/.env")
  set +a
fi

export NEBULA_HOST="${NEBULA_HOST:-127.0.0.1}"
export NEBULA_PORT="${NEBULA_PORT:-9669}"
export NEBULA_USER="${NEBULA_USER:-root}"
export NEBULA_PASSWORD="${NEBULA_PASSWORD:-}"
export NEBULA_SPACE="${NEBULA_SPACE:-auto_innovation_kg}"

# kill previous uvicorn on 8000 if any
pkill -f "uvicorn backend.main:app" 2>/dev/null || true
sleep 1
nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > /tmp/ai4kg_api.log 2>&1 &
echo "started pid=$!"
sleep 2
curl -sS http://127.0.0.1:8000/health || (echo "API failed"; tail -n 50 /tmp/ai4kg_api.log; exit 1)
echo
# 不打印 Key，只提示是否已加载
python3 - <<'PY'
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path("/mnt/c/Users/Administrator/Desktop/up_x/AI4KnowledgeNet") / ".env")
key = (os.getenv("LLM_API_KEY") or "").strip()
print("LLM:", "ready" if key else "NOT configured (set LLM_API_KEY in .env)")
PY
