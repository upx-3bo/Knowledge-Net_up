# AI 辅助多维技术信息库 — 驱制一体 / 角模块

基于知识图谱（NebulaGraph / SQLite）构建的汽车创新技术知识库，用于：

- **技术分类**：驱制一体 / 角模块领域的技术体系
- **标准化分析**：技术-标准关联矩阵
- **资源池挂载**：人 / 设备 / 工具 / 文档关联到技术
- **情报获取与动态更新**：专利、新闻自动采集 + AI 分析入库

架构遵循公司标准范式：**知识图谱 → API → MCP tools → AI 应用（Skill）**。

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────┐
│  AI 应用层  (Streamlit 前端 / MCP 客户端 / opencode)     │
├─────────────────────────────────────────────────────────┤
│  FastAPI 后端  (REST API)  +  MCP Server                │
├─────────────────────────────────────────────────────────┤
│  引擎抽象层  get_store() ── 按 KNOWLEDGE_ENGINE 切换     │
│    ├─ NebulaGraph  (生产/团队环境)                       │
│    └─ SQLite       (本地零依赖原型)                      │
└─────────────────────────────────────────────────────────┘
```

- **数据投喂**：手动录入（API / 前端）、上传文档后 **LLM 自动抽取**实体关系
- **存储**：图结构（技术、分类、标准、专利、资源、文档 6 类实体 + 关系）
- **消费**：全文搜索、子图查询、技术-标准对照、资源池查询、情报更新

---

## 二、目录结构

```
ai-knowledge-base/
├── backend/                       # FastAPI 后端
│   ├── main.py                    # 应用入口（API 文档 /docs）
│   ├── config.py                  # 配置
│   ├── database/                  # （Nebula 客户端，备用）
│   ├── models/schemas.py          # Pydantic 数据模型
│   ├── routers/                   # 路由
│   │   ├── knowledge.py           # 知识 CRUD
│   │   ├── search.py              # 搜索
│   │   └── classification.py      # 分类/标准/资源池
│   └── services/
│       ├── knowledge_base.py      # SQLite 图引擎
│       ├── nebula_store.py        # NebulaGraph 图引擎
│       ├── graph_store.py         # 引擎工厂（切换）
│       ├── extractor.py           # LLM 知识抽取
│       └── intelligence.py        # 情报自动获取
├── frontend/                      # Streamlit 前端
│   ├── app.py                     # 首页仪表盘
│   └── pages/                     # 投喂 / 图谱 / 查询
├── mcp-server/main.py             # MCP Server
├── data/seed/                     # 种子数据 + 导入脚本
├── nebula_init.py                 # Nebula 初始化（建库+建Schema+导数据）
├── docker-compose.nebula.yml      # NebulaGraph 集群
├── docker-compose.yml             # 全栈容器（备用）
├── requirements.txt               # Python 依赖
└── .env.example                   # 环境变量模板
```

---

## 三、环境准备

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 后端/前端/MCP |
| Docker Desktop + WSL2 | 最新 | 运行 NebulaGraph（可选，SQLite 模式不需要） |

安装依赖：

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

复制环境变量模板并填写（至少填 LLM API Key）：

```bash
cp .env.example .env
```

---

## 四、快速启动（两种模式）

### 模式 A：SQLite 本地模式（零依赖，推荐先跑通）

**无需 Docker**，只在本机跑后端 + 前端：

```bash
# 1. 导入种子数据（写入 data/knowledge.db）
python data/seed/seed_loader.py

# 2. 启动后端 (http://localhost:8000/docs)
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 3.（可选）启动前端 (http://localhost:8501)
streamlit run frontend/app.py
```

> 默认引擎即 SQLite，无需配置。验证：访问 `http://localhost:8000/stats`，应看到各类实体数量。

### 模式 B：NebulaGraph 模式（生产 / 团队）

**前置**：已安装 Docker Desktop + WSL2 并启动。

```bash
# 1. 启动 NebulaGraph 集群
docker compose -f docker-compose.nebula.yml up -d

# 2. 初始化图库（建 Space + Schema + 导种子数据）
python nebula_init.py

# 3. 配置环境变量指向 Nebula
#    .env 中设置:
#    KNOWLEDGE_ENGINE=nebula
#    NEBULA_HOST=127.0.0.1
#    NEBULA_PORT=9669

# 4. 启动后端（自动连 Nebula）
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

- 图谱可视化 Studio：`http://localhost:7001`
- 验证：访问 `http://localhost:8000/stats`

---

## 五、关键步骤与流程

### 1. 投喂数据（三种方式）

| 方式 | 入口 | 说明 |
|------|------|------|
| 手动录入 | `POST /knowledge/technology` 等 | 逐条添加技术/标准/专利/资源 |
| 文档 AI 抽取 | `POST /knowledge/document` + LLM | 粘贴文档文本 → LLM 抽取实体关系入库 |
| 情报自动采集 | `POST /intelligence/update` | 抓取专利/新闻 → LLM 分析 → 入图 |

### 2. 数据模型（Schema）

**实体（Tag）**：`technology`、`category`、`standard`、`patent`、`resource`、`component`、`document`

**关系（Edge）**：
| 关系 | 含义 |
|------|------|
| `belongs_to` | 技术 → 分类 |
| `contains`   | 分类 → 子分类（树） |
| `relates_to` | 技术 ↔ 技术 |
| `has_standard` | 技术 → 标准 |
| `has_patent`  | 技术 → 专利 |
| `references`  | 技术 → 资源（资源池挂载）|
| `derived_from`| 文档 → 源实体 |

### 3. 常用查询 API

| API | 说明 |
|-----|------|
| `GET /knowledge/technology` | 列出技术 |
| `GET /search/full-text?query=` | 全文搜索 |
| `GET /search/graph?keyword=&depth=` | 子图查询 |
| `GET /classification/tree` | 分类树 |
| `GET /classification/technology-standards?tech_name=` | 技术-标准对照 |
| `GET /classification/resource-pool?tech_name=` | 资源池查询 |
| `GET /stats` | 实体统计 |

### 4. MCP Server（AI 可调用）

```bash
python mcp-server/main.py
```

暴露 6 个工具（`query_technology`、`query_subgraph`、`query_standards_for_technology`、`query_resource_pool`、`query_category_tree`、`run_intelligence`），对接 opencode 等支持 MCP 的客户端后可用自然语言查图库。

---

## 六、在新电脑上重新部署（clone 后三步）

```bash
# 1. clone
git clone <your-repo> ai-knowledge-base
cd ai-knowledge-base

# 2. 起环境
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 填 LLM Key

# 3. 起库 + 起服务（选 A 或 B）
python data/seed/seed_loader.py          # A: SQLite 重建数据
uvicorn backend.main:app --port 8000     # 起后端
```

> 数据全部可从 `data/seed/init_data.json` 重建，`data/knowledge.db` 已 gitignore，不同机器的本地文件不影响 clone 与一致性。

---

## 七、Docker/WSL2 安装（仅 NebulaGraph 模式需要）

见 [INSTALL_DOCKER.md](INSTALL_DOCKER.md)。

要点：
1. 管理员终端 `wsl --install` → **重启**
2. 安装 Docker Desktop（勾选 WSL2）→ **重启**
3. Docker Desktop 配置代理 `http://proxy.huawei.com:8080`（公司网络）
4. `docker pull hello-world` 验证

---

## 八、安全与合规

- `.env` 存放 LLM API Key，已在 `.gitignore` 中忽略，**勿提交**。
- 团队生产环境建议接入公司统一 LLM 网关与知识图谱平台，而非外部 API / 自建 Docker。
