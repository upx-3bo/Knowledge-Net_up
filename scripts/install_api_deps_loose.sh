#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install --break-system-packages \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  fastapi uvicorn python-dotenv 'nebula3-python==3.8.3'
python3 - <<'PY'
import fastapi, uvicorn
print("ok", fastapi.__version__, uvicorn.__version__)
PY
