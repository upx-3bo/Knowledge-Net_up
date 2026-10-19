# 运行说明（当前机器：WSL1 + Nebula 原生）

本机为 OpenStack VM，**无嵌套虚拟化**，无法使用 Docker / WSL2。已改用 WSL1 原生 Nebula。

## 状态检查

```powershell
wsl -l -v
netstat -ano | findstr "9669 9559 9779"
```

应看到 Ubuntu VERSION=1，且 9669/9559/9779 在监听。

## 启动 / 停止

```powershell
wsl -d Ubuntu -u root -- bash /mnt/c/Users/Administrator/Desktop/up_x/AI4KnowledgeNet/scripts/start_nebula_wsl1.sh
wsl -d Ubuntu -u root -- bash /usr/local/nebula/scripts/nebula.service stop all
```

## Schema 已初始化

- Space: `auto_innovation_kg`
- Tags: domain / subdomain / technology / material
- Edges: belongs_to / supports / relates_to
- 冒烟数据：各 1 个节点 + 3 条边

重置时可再跑：

```powershell
wsl -d Ubuntu -u root -- python3 /mnt/c/Users/Administrator/Desktop/up_x/AI4KnowledgeNet/scripts/nebula_wait_and_init.py
wsl -d Ubuntu -u root -- python3 /mnt/c/Users/Administrator/Desktop/up_x/AI4KnowledgeNet/scripts/nebula_seed_retry.py
```
