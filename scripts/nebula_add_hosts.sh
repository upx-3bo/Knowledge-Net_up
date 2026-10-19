#!/usr/bin/env bash
set -euo pipefail
cd /tmp
if [ ! -x nebula-console ]; then
  curl -L --retry 3 -o nebula-console \
    https://github.com/vesoft-inc/nebula-console/releases/download/v3.8.0/nebula-console-linux-amd64-v3.8.0
  chmod +x nebula-console
fi
ls -lh nebula-console

./nebula-console -addr 127.0.0.1 -port 9669 -u root -p '' -e 'ADD HOSTS "127.0.0.1":9779;'
sleep 5
./nebula-console -addr 127.0.0.1 -port 9669 -u root -p '' -e 'SHOW HOSTS;'

echo "==> storaged port"
ss -lntp 2>/dev/null | grep 9779 || netstat -lntp 2>/dev/null | grep 9779 || true
ps aux | grep nebula-storaged | grep -v grep || true
