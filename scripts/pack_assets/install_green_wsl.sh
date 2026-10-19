#!/usr/bin/env bash
# 绿区：从离线包安装 Nebula + Python 依赖，并启动空库 + API
set -euo pipefail

PACK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$PACK_ROOT/app"
WHEELS="$PACK_ROOT/offline/wheels"
NEBULA_SRC="$PACK_ROOT/offline/nebula"
NEBULA_DST="${NEBULA_DST:-/usr/local/nebula}"

echo "==> pack: $PACK_ROOT"

if [[ ! -d "$APP/backend" ]]; then
  echo "ERROR: 找不到 app/backend，请确认在解压后的绿区包内执行"
  exit 1
fi

# 1) Nebula
if [[ ! -x "$NEBULA_DST/bin/nebula-graphd" ]]; then
  if [[ -x "$NEBULA_SRC/bin/nebula-graphd" ]]; then
    echo "==> install nebula → $NEBULA_DST"
    mkdir -p "$NEBULA_DST"
    rsync -a "$NEBULA_SRC/" "$NEBULA_DST/"
  else
    echo "ERROR: offline/nebula 无 graphd，无法安装"
    exit 1
  fi
else
  echo "==> nebula already at $NEBULA_DST"
fi

# 2) Python deps (offline)
echo "==> pip install from wheels"
python3 -m pip install --break-system-packages --no-index --find-links="$WHEELS" \
  -r "$APP/requirements.txt"

python3 -c "import fastapi, uvicorn, nebula3; print('imports_ok')"

# 3) .env
if [[ ! -f "$APP/.env" ]]; then
  cp "$APP/.env.example" "$APP/.env"
  echo "==> wrote $APP/.env (from example)"
fi

# 4) start nebula
export PYTHONPATH="$APP"
cd "$APP"
if [[ -x "$APP/scripts/start_nebula_wsl1.sh" ]]; then
  bash "$APP/scripts/start_nebula_wsl1.sh" || true
else
  bash "$NEBULA_DST/scripts/nebula.service" start all || true
fi
sleep 3

# 5) schema init (empty business graph is fine)
python3 "$APP/scripts/nebula_wait_and_init.py"
# 可选：灌蓝区 demo。绿区业务入库前可跳过：
# python3 "$APP/scripts/nebula_seed_retry.py"

# 6) API
bash "$APP/scripts/start_api_wsl.sh"

echo
echo "GREEN_OK"
echo "工作台: http://127.0.0.1:8000/"
echo "健康检查: curl http://127.0.0.1:8000/health"
echo "材料请在绿区直接入库；详见 INSTALL_绿区.md"
