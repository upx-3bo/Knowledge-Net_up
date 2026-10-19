#!/usr/bin/env bash
# Run INSIDE Ubuntu WSL after reboot.
# Installs Docker Engine (not Desktop) + compose plugin, then starts Nebula.
set -euo pipefail

PROJECT_WIN="/mnt/c/Users/Administrator/Desktop/up_x/AI4KnowledgeNet"
NEBULA_DIR="$PROJECT_WIN/infra/nebula"

echo "==> apt update"
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg

echo "==> Docker apt repo (Aliyun mirror)"
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
. /etc/os-release
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.aliyun.com/docker-ce/linux/ubuntu \
  ${VERSION_CODENAME} stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

echo "==> enable docker"
sudo service docker start
sudo usermod -aG docker "$USER" || true

echo "==> registry mirrors"
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run"
  ]
}
EOF
sudo service docker restart

echo "==> start Nebula"
cd "$NEBULA_DIR"
sudo docker compose pull
sudo docker compose up -d
sudo docker compose ps

echo "Done. Graphd :9669  Studio :7001"
echo "Then on Windows: python scripts/nebula_init.py"
