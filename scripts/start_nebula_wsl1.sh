#!/usr/bin/env bash
set -euo pipefail
NEBULA_HOME=/usr/local/nebula
cd "$NEBULA_HOME"

cp -f etc/nebula-metad.conf.default etc/nebula-metad.conf
cp -f etc/nebula-storaged.conf.default etc/nebula-storaged.conf
cp -f etc/nebula-graphd.conf.default etc/nebula-graphd.conf

mkdir -p data/meta data/storage logs pids

# Prefer package helper if present
if [ -x scripts/nebula.service ]; then
  sed -i 's/\r$//' scripts/nebula.service scripts/utils.sh || true
  bash scripts/nebula.service start all
else
  ./bin/nebula-metad --flagfile=etc/nebula-metad.conf
  sleep 3
  ./bin/nebula-storaged --flagfile=etc/nebula-storaged.conf
  sleep 3
  ./bin/nebula-graphd --flagfile=etc/nebula-graphd.conf
fi

sleep 2
echo "==> processes"
ps aux | grep -E 'nebula-(meta|storage|graph)d' | grep -v grep || true
echo "==> ports"
ss -lntp 2>/dev/null | grep -E '9559|9779|9669' || netstat -lntp 2>/dev/null | grep -E '9559|9779|9669' || true
echo "==> recent metad log"
tail -n 30 logs/nebula-metad*.log 2>/dev/null || tail -n 30 logs/metad-stdout.log 2>/dev/null || true
