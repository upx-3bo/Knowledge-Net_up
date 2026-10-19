# AI4KnowledgeNet —— 完整副本部署手册（供新机器 / 同事或 AI 使用）

> 目标：让 **AI4KnowledgeNet**（知识图谱 + 工作台 + API + AI 协助入库）在一台**新的电脑**上完整跑起来；
> 并把现有知识图谱数据（约 500+ 节点）一起复制过去。本手册按步骤可直接执行。

## 0. 一次性判断：你现在拿到什么？

| 东西 | 是否需要 | 说明 |
|------|---------|------|
| 源码（backend / frontend / scripts / mcp_server / docs）| 必须 | 本仓库即是 |
| 数据快照 `scripts/snapshots/snapshot_*.json` | 必须 | 图谱数据（节点/边）；**不在仓库内**，需从源机单独拷贝 |
| NebulaGraph 数据库引擎 | 必须 | 图库运行时，需要你安装（见第 3 步）|
| Python 3.10+ | 必须 | 推荐 3.11 |
| `requirements.txt` | 必须 | Python 依赖 |

---

## 1. 准备 Python 环境

```bash
# 在项目根目录
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS / WSL
source venv/bin/activate

pip install -r requirements.txt
```

> 依赖较关键的是 `nebula3-python==3.8.3`（版本已固定，勿随意改）。

---

## 2. 准备配置文件

```bash
# 从示例复制一份 .env，再按需修改
cp .env.example .env
```

`.env` 关键项：

```ini
NEBULA_HOST=127.0.0.1    # 改成你自己 Nebula 的地址；本机 Docker 用 127.0.0.1
NEBULA_PORT=9669
NEBULA_USER=root
NEBULA_PASSWORD=         # 若你设了密码就填；原机 WSL 默认为空
NEBULA_SPACE=auto_innovation_kg

# AI 协助（OpenAI 兼容接口）—— 从原机 .env 拷贝同样的 LLM_* 值（含真实 key）
LLM_API_KEY=<和原机一致的key>
LLM_API_URL=https://ai-models.rnd.yinwang.com/ai-platform-models-agent/v1
LLM_MODEL=DeepSeek-V4-Flash

# 工作台写入口令 —— 务必改成你自己的
WRITE_PASSWORD=你的口令
```

> ⚠️ `.env` 里含真实密钥，属敏感信息，别提交到 git / 别外泄。

---

## 3. 安装并启动 NebulaGraph（三选一）

### 方案 A（推荐·有 Docker / Linux）—— 官方镜像

仓库自带 `infra/nebula/docker-compose.yml`（NebulaGraph v3.8 官方 `vesoft/nebula-*` 镜像）：

```bash
cd infra/nebula
docker compose up -d
# 首次启动后注册存储节点（进 graphd 容器执行）
docker compose exec graphd nebula-console -addr graphd -port 9669 -u root -p ''
# 在控制台里：
#   ADD HOSTS "storaged0":9779;
#   SHOW HOSTS;
```

### 方案 B（无 Docker / 无嵌套虚拟化）—— 原生二进制

原生二进制在 `infra/nebula/native/`（约 240MB，**不在仓库内**，可从原机单独拷）。
参考原机脚本 `scripts/install_nebula_wsl1.sh`、`scripts/start_nebula_wsl1.sh` 部署到 Linux/WSL。

### 方案 C（只想连已有图库，不装）

直接把 `.env` 的 `NEBULA_HOST` 指向那台 Nebula 的地址即可，跳到第 4 步。

---

## 4. 初始化 Schema（建空间 + Tag + Edge + 索引）

```bash
# 确保在项目根目录，且能 import backend
# Windows:
set PYTHONPATH=%CD%
# Linux/WSL:
export PYTHONPATH=$PWD

python scripts/nebula_init.py
```

如果 Nebula 需要等几秒就绪，可用：
```bash
python scripts/nebula_wait_and_init.py
```

---

## 5. 导入图谱数据（复制现有知识库）

```bash
python scripts/snapshot.py import scripts\snapshots\snapshot_20260901_020002.json
```
（或指定任意一份最新快照；列表可用 `python scripts/snapshot.py list`。）

> 说明：快照是全量「顶点+边」，导入前必须先建好 Schema（第 4 步）。
> 撤回/重做历史（`data/history.db`）**不会**随快照迁移，属本机运行记录，可接受。

---

## 6. 启动工作台 / API

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

- 本机：http://127.0.0.1:8001/
- 同网其他电脑：`http://<本机IP>:8001/`（Windows 需放行入站 TCP 8001）
- 接口文档：`http://127.0.0.1:8001/docs`
- 健康检查：`GET /health`，统计：`GET /stats`

验证：
```bash
curl http://127.0.0.1:8001/health
# {"status":"ok","space":"auto_innovation_kg"}
curl http://127.0.0.1:8001/stats
# {"domain":4,"subdomain":25,"technology":233,"material":241,...}
```

---

## 7.（可选）每日自动备份

```bash
python scripts/backup_daily.py            # 有变更才导出快照到 scripts/snapshots/
python scripts/backup_daily.py --force    # 强制导出
```
想定时，Windows 建计划任务每天调用它即可（参考原机任务 `AKNetDailyBackup`）。

---

## 8. 常见问题

- **`ModuleNotFoundError: No module named 'backend'`**：没在项目根目录运行或没设 `PYTHONPATH`（见第 4 步）。
- **连不上 Nebula / `Unable to connect`**：检查 `NEBULA_HOST:PORT` 和 Nebula 是否已启动（`docker compose ps` / 原生进程）。
- **`No space` / schema 报错**：空间/Tag 未建，先跑第 4 步。
- **AI 抽取报 503/超时**：上游推理服务过载，稍后重试；或改用「批量导入」用本地 AI 先处理好再入库。

---

打包命令（原机生成可分发 zip）：
```bash
python scripts/package_release.py                     # 默认不含原生二进制
python scripts/package_release.py --include-native    # 包含原生 Nebula 二进制（约 240MB）
```
产物：`dist/AI4KnowledgeNet_release.zip`
