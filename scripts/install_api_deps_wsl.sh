#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install --break-system-packages \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  fastapi==0.115.0 \
  "uvicorn[standard]==0.30.6" \
  pydantic==2.9.2 \
  python-dotenv==1.0.1 \
  nebula3-python==3.8.3
python3 -c "import fastapi, uvicorn, nebula3; print('imports_ok')"
