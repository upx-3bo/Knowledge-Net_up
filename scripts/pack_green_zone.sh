#!/usr/bin/env bash
# 在蓝区打包，拷到绿区解压安装。
# 用法: bash scripts/pack_green_zone.sh [输出父目录]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M)"
OUT_PARENT="${1:-$(dirname "$ROOT")}"
STAGE="$OUT_PARENT/AI4KnowledgeNet-green-$STAMP"
ARCHIVE="$OUT_PARENT/AI4KnowledgeNet-green-$STAMP.tar.gz"

echo "==> stage: $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"/{app,offline/wheels,offline/nebula,scripts}

# ---- app ----
if command -v rsync >/dev/null 2>&1; then
  rsync -a \
    --exclude '.git/' \
    --exclude 'reference/' \
    --exclude 'tools/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude 'node_modules/' \
    --exclude '.cursor/' \
    "$ROOT/" "$STAGE/app/"
else
  # fallback
  cp -a "$ROOT/." "$STAGE/app/"
  rm -rf "$STAGE/app/reference" "$STAGE/app/tools" "$STAGE/app/.git" "$STAGE/app/.env" || true
fi

if [[ -f "$ROOT/.env.example" ]]; then
  cp "$ROOT/.env.example" "$STAGE/app/.env.example"
else
  cat >"$STAGE/app/.env.example" <<'EOF'
NEBULA_HOST=127.0.0.1
NEBULA_PORT=9669
NEBULA_USER=root
NEBULA_PASSWORD=
NEBULA_SPACE=auto_innovation_kg
# LLM_API_KEY=
# LLM_API_URL=
EOF
fi

# ---- Nebula ----
if [[ -x /usr/local/nebula/bin/nebula-graphd ]]; then
  echo "==> copy /usr/local/nebula (skip data/logs)"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a /usr/local/nebula/ "$STAGE/offline/nebula/" \
      --exclude 'data/' --exclude 'logs/' --exclude 'pids/'
  else
    cp -a /usr/local/nebula/. "$STAGE/offline/nebula/"
    rm -rf "$STAGE/offline/nebula/data" "$STAGE/offline/nebula/logs" "$STAGE/offline/nebula/pids" || true
  fi
elif [[ -x "$ROOT/infra/nebula/native/nebula/bin/nebula-graphd" ]]; then
  echo "==> copy infra/nebula/native/nebula"
  cp -a "$ROOT/infra/nebula/native/nebula/." "$STAGE/offline/nebula/"
else
  echo "WARN: 未找到 Nebula 二进制"
fi

# ---- wheels（只要二进制，避免绿区/蓝区现场编译 pydantic-core）----
echo "==> download pip wheels (binary only)"
python3 -m pip download \
  -d "$STAGE/offline/wheels" \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --only-binary=:all: \
  -r "$ROOT/requirements.txt"

# 兜底：把本机已装的相关 wheel/egg 从 pip cache 再扫一遍
CACHE="$(python3 -m pip cache dir 2>/dev/null || true)"
if [[ -n "$CACHE" && -d "$CACHE" ]]; then
  find "$CACHE" -type f \( -name 'pydantic_core-*.whl' -o -name 'pydantic-*.whl' -o -name 'nebula3_python-*.whl' \) \
    -exec cp -n {} "$STAGE/offline/wheels/" \; 2>/dev/null || true
fi

# ---- docs / installer ----
cp "$ROOT/scripts/pack_assets/install_green_wsl.sh" "$STAGE/scripts/install_green_wsl.sh"
cp "$ROOT/scripts/pack_assets/INSTALL_绿区.md" "$STAGE/INSTALL_绿区.md"
chmod +x "$STAGE/scripts/install_green_wsl.sh"

echo "==> tar.gz"
tar -czf "$ARCHIVE" -C "$OUT_PARENT" "$(basename "$STAGE")"
du -sh "$STAGE" "$ARCHIVE"
echo
echo "PACK_OK"
echo "DIR=$STAGE"
echo "TGZ=$ARCHIVE"
