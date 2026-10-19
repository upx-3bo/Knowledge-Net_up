# AI4KnowledgeNet · 汽车创新技术点网络工作台

一个自包含的「技术点知识图谱 + 可视化工作台 + API + AI 协助入库」工具。
本仓库只包含**工具功能本身的代码、脚本与文档**；知识节点数据、运行时数据库、
本地环境与密钥均**不随仓库上传**（见文末「不随仓库上传的内容」）。

## 功能概览

- **知识图谱工作台**（`frontend/`）：二维/三维视图、树状/同心圆/力导向布局、
  节点检索、编辑、级联删除、撤回/重做、标注开关、入库审阅（分批确认）。
- **图存储与 API**（`backend/`）：FastAPI 应用，对接 NebulaGraph，提供图谱查询、
  导入、导出、AI 抽取、雷达采集等接口。
- **AI 协助入库**：通过 OpenAI 兼容接口把文档/URL 抽取为结构化技术点草稿再入库。
- **MCP 服务**（`mcp_server/`）：把知识库能力暴露给支持 MCP 的 AI 工具。
- **运维脚本**（`scripts/`）：Nebula 初始化/健康检查、快照备份/恢复、批量导入、
  发布打包等。
- **基础设施**（`infra/nebula/`）：NebulaGraph 3.8 的 Docker Compose 与说明。

## 目录结构

```
.
├─ backend/          FastAPI 后端（routers/services/store/history/auth/config）
├─ frontend/         静态前端（index.html / app.js / styles.css / vendor 第三方库）
├─ mcp_server/       MCP 服务
├─ scripts/          运维与导入脚本（Nebula 初始化、快照、备份、打包等）
├─ infra/nebula/     NebulaGraph 部署（docker-compose + README）
├─ docs/             架构/数据模型/功能/工作流等文档
├─ research/         抽取模板（templates/）
├─ requirements.txt  Python 依赖
├─ .env.example      配置示例（复制为 .env 后填写）
├─ run.bat           一键启动（Windows，默认端口 8001）
└─ setup.bat         首次/重建 venv（Windows）
```

## 快速开始

1. **Python 环境**（推荐 3.11）

   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux / WSL / macOS
   source venv/bin/activate
   pip install -r requirements.txt
   ```

   > 关键依赖：`nebula3-python==3.8.3`（版本已固定，勿随意改动）。

2. **配置**：复制 `.env.example` 为 `.env`，按需填写 Nebula 连接、AI 接口、写入
   口令（`WRITE_PASSWORD`）。

3. **启动 NebulaGraph**（三选一）：

   - **A. Docker（推荐）**：`cd infra/nebula && docker compose up -d`，
     首次进入 graphd 控制台执行 `ADD HOSTS "storaged0":9779;`。
   - **B. 原生二进制**：自行安装 NebulaGraph 3.8（参考 `scripts/nebul*` 脚本）；
     仓库不包含 240MB 原生二进制。
   - **C. 连接已有图库**：把 `.env` 的 `NEBULA_HOST` 指向已有 Nebula 即可。

4. **初始化 Schema**：

   ```bash
   # 项目根目录下
   set PYTHONPATH=%CD%          # Windows
   export PYTHONPATH=$PWD       # Linux/WSL
   python scripts/nebula_init.py
   ```

5. **启动服务**：

   ```bash
   venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
   # 或 Windows 直接运行 run.bat
   ```

   - 本机：<http://127.0.0.1:8001/>
   - 局域网：`http://<本机IP>:8001/`
   - 接口文档：<http://127.0.0.1:8001/docs>
   - 健康检查：`GET /health`

## 迁移到新机器（复制完整功能）

请参阅 [`REPLICATE.md`](REPLICATE.md) 的分布部署手册。要点：

- 源码（本仓库）+ `requirements.txt` + 新机 Python 3.11；
- 自行安装 NebulaGraph（Docker 或原生）；
- 知识图谱数据需用**快照**单独迁移（见下节，快照不在仓库内）；
- 新建 `.env` 并填写与源机一致的 Nebula / LLM / 写入配置。

## 不随仓库上传的内容（需在迁移时另行处理）

| 内容 | 位置 | 说明 |
|------|------|------|
| Python 虚拟环境 | `venv/` | 依赖体积大且与平台相关；用 `pip install -r requirements.txt` 重建 |
| 本地配置与密钥 | `.env` | 含 Nebula 口令、LLM API Key、写入口令；复制 `.env.example` 后自填，**切勿提交** |
| 知识节点数据（图谱快照） | `scripts/snapshots/` | 属业务数据；用 `python scripts/snapshot.py export/import` 单独迁移 |
| 导入批次 / 研究中间件 | `research/import_batches/`、`research/import_runs/`、`research/c2_*.json` | 属业务内容，不入库工具仓库 |
| 运行时数据库 | `data/*.db`（history/radar/collector） | 本机审计与审阅记录，随实例变化，不迁移 |
| Nebula 原生二进制 | `infra/nebula/native/` | 约 240MB；按需单独安装/拷贝 |
| 发布包 / 报告 | `dist/`、`1022汇报PPT/` | 构建产物与汇报材料 |

> 契约：**代码/脚本/文档 = 仓库；数据/环境/密钥 = 本地 + 单独迁移**。

## 开发与维护

- 改后端 `.py` 后需重启服务（uvicorn 未开 `--reload`）。
- 改前端后更新版本号（`frontend/index.html` 的 `?v=` 与徽标）。
- 依赖变更后更新 `requirements.txt` 并重装。

## 文档

- `docs/ARCHITECTURE.md` — 架构说明
- `docs/SCHEMA.md` — 数据模型 / 图 Schema
- `docs/FEATURES.md` — 功能清单
- `docs/DATA_IMPORT.md` — 数据导入
- `docs/MCP.md` — MCP 使用
- `docs/RADAR.md` — 雷达采集
- `docs/ROADMAP.md` — 演进与维护
