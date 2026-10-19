#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "==> apt deps"
apt-get update -y
apt-get install -y curl ca-certificates tar wget \
  libreadline8 libatomic1 || true
apt-get install -y libncurses6 || apt-get install -y libncurses5 || true

PKG=nebula-graph-3.8.0.ubuntu2004.amd64.tar.gz
URL="https://oss-cdn.nebula-graph.com.cn/package/3.8.0/${PKG}"
cd /tmp
if [ ! -f "$PKG" ] || [ "$(stat -c%s "$PKG" 2>/dev/null || echo 0)" -lt 1000000 ]; then
  echo "==> download $URL"
  curl -L --retry 3 -o "$PKG" "$URL"
fi
ls -lh "$PKG"

echo "==> extract"
rm -rf /usr/local/nebula /tmp/nebula_extract
mkdir -p /tmp/nebula_extract
tar -zxf "$PKG" -C /tmp/nebula_extract
TOP=$(find /tmp/nebula_extract -maxdepth 2 -type d -name bin -printf '%h\n' | head -1)
if [ -z "${TOP:-}" ]; then
  echo "ERROR: cannot find nebula bin dir"
  find /tmp/nebula_extract | head -50
  exit 1
fi
rm -rf /usr/local/nebula
mv "$TOP" /usr/local/nebula
echo "Installed to /usr/local/nebula"
ls -la /usr/local/nebula
ls /usr/local/nebula/bin
ls /usr/local/nebula/scripts || true
ls /usr/local/nebula/etc || true
