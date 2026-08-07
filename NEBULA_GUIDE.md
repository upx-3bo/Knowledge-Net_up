# 基于 NebulaGraph 搭建汽车创新技术知识图谱 · 完整指南

> 本文档面向另一台设备（以下简称"新机器"）的工程师，说明如何基于 NebulaGraph 重建并强化已有的汽车创新技术知识图谱平台。
>
> 源代码仓库：https://github.com/upx-3bo/Knowledge-Net_up

---

## 目录
1. [项目目标](#1-项目目标)
2. [当前进展与现有代码资产](#2-当前进展与现有代码资产)
3. [技术路线：从 SQLite 到 NebulaGraph](#3-技术路线从-sqlite-到-nebulagraph)
4. [哪些工作 NebulaGraph 本身就能实现](#4-哪些工作-nebulagraph-本身就能实现)
5. [NebulaGraph 安装与初始化](#5-nebulagraph-安装与初始化)
6. [Schema 设计（强化版）](#6-schema-设计强化版)
7. [数据迁移脚本](#7-数据迁移脚本)
8. [后端切换与配置](#8-后端切换与配置)
9. [AI 提取管道的复用与强化](#9-ai-提取管道的复用与强化)
10. [可视化前端复用说明](#10-可视化前端复用说明)
11. [经验与建议](#11-经验与建议)
12. [验证清单](#12-验证清单)

---

## 1. 项目目标

构建一个以「技术点」为核心节点的 **汽车创新技术知识图谱**，实现：

- **多层级节点网络**：顶层领域 → 子领域 → 具体技术点 → 支撑材料（论文/专利/新闻/技术文件）
- **力导向网络图可视化**：拖拽、缩放、折叠、搜索高亮、层级筛选
- **AI 自动提取入库**：粘贴技术资讯文本，LLM 自动抽取技术点/支撑材料并写入图数据库
- **AI 自动建立关联**：新建节点后，AI 分析语义并自动连接到相关现有节点
- **MCP Server 工具集**：让 AI Agent 直接操作知识图谱（搜索/查询/增删/提取）
- **团队共享访问**：7×24 在线服务，多人协作编辑

### 1.1 层级模型（核心约定）

| 层级 | 含义 | 节点类型 (tag) | 名称限制 | 球体大小 |
|------|------|---------------|---------|---------|
| L1 | 顶层领域 | `domain` | ≤8 字 | 最大（深色） |
| L2 | 子领域 | `subdomain` | ≤8 字 | 较大 |
| L3 | 具体技术点 | `technology` | ≤8 字 | 中等 |
| L0 | 支撑材料 | `material` | ≤14 字简称 | 最小（浅色） |

### 1.2 边类型约定

| 边类型 | 方向 | 含义 |
|--------|------|------|
| `belongs_to` | 子 → 父 | "属于"关系（L3→L2, L2→L1） |
| `supports` | material(L0) → tech_point(L3) | "支撑"关系（材料支撑技术点） |

> **注意**：`supports` 边方向是 **材料指向技术点**，不是技术点指向材料。

---

## 2. 当前进展与现有代码资产

### 2.1 已完成（SQLite 版本，350 节点 + 335 边）

| 模块 | 文件 | 说明 |
|------|------|------|
| FastAPI 后端入口 | `backend/main.py` | 35 个 API 接口，`FastAPIOffline` 离线 Swagger |
| 图可视化路由 | `backend/routers/graph_viz.py`（~1600 行） | Canvas 力导向渲染器，含搜索/筛选/编辑/连线/折叠/AI 提取 |
| 介绍页 | `backend/routers/about.py` | 6 tab 功能介绍 |
| 知识管理路由 | `backend/routers/knowledge.py` | CRUD 接口 |
| 搜索路由 | `backend/routers/search.py` | 关键词/路径/全文检索 |
| 分类路由 | `backend/routers/classification.py` | 分类树管理 |
| **SQLite 引擎** | `backend/services/knowledge_base.py` | `vertices`/`edges`/`node_notes` 三表 |
| **NebulaGraph 引擎** | `backend/services/nebula_store.py` | 已实现同接口（见下方） |
| **引擎工厂** | `backend/services/graph_store.py` | 按 `KNOWLEDGE_ENGINE` 环境变量切换 |
| AI 提取管道 | `backend/services/extractor.py` | LLM 提取 + 入库，适配层级模型 |
| 情报收集管道 | `backend/services/intelligence.py` | 资讯抓取 + AI 分析 + 入库 |
| **NebulaGraph 初始化** | `nebula_init.py` | 创建 Space + Tag + Edge + 种子数据 |
| 构建脚本 | `build_network.py` | 从 127 条 Excel 数据构建完整图谱 |
| MCP Server | `mcp-server/main.py` | 7 个工具，适配层级模型 |
| 数据 | `data_2026.json` | 127 条 2026 年汽车技术资讯 |

### 2.2 NebulaGraph 引擎已存在但未实测

`backend/services/nebula_store.py` 已经实现了与 SQLite 引擎**相同的接口**（`insert_vertex`/`update_vertex`/`delete_vertex`/`insert_edge`/`query_edges`/`get_neighbors`/`get_notes` 等），但**从未在真实 NebulaGraph 实例上运行过**。需要在新机器上实测并修复问题。

### 2.3 已知问题（迁移时需修复）

1. `nebula_store.py` 的 `update_vertex` 用 `DELETE VERTEX WITH EDGE + INSERT` 方式更新，会丢失该节点的所有边——应改用 `UPDATE VERTEX ON` 语法
2. `nebula_store.py` 的 `query_vertices` 硬编码了 7 个旧 tag（`technology`/`category`/`standard`/`patent`/`resource`/`component`/`document`），未包含新的 `domain`/`subdomain`/`material`
3. `nebula_init.py` 的 Schema 是旧版本（8 Tag + 9 Edge），**不包含** `domain`/`subdomain`/`material` 三个新 tag
4. `nebula_store.py` 的 `_vid()` 函数只处理空格/斜杠/括号，中文 vid 可能有问题——建议统一用 `node_` 前缀 + UUID

---

## 3. 技术路线：从 SQLite 到 NebulaGraph

### 3.1 为什么迁移到 NebulaGraph？

| 维度 | SQLite | NebulaGraph |
|------|--------|-------------|
| 数据规模 | <10 万节点可用 | 千万级节点 |
| 多跳查询 | 应用层 BFS/DFS，慢 | 原生图遍历，毫秒级 |
| 路径查找 | 手写 BFS | `FIND SHORTEST PATH` 一行 nGQL |
| 全文检索 | `LIKE '%keyword%'` | 内置全文索引（可选） |
| 并发写入 | 单写锁 | 分布式多写 |
| 部署复杂度 | 零 | 需要 Docker/K8s |

### 3.2 迁移策略

```
SQLite (现有)  ──导出 JSON──→  迁移脚本  ──写入──→  NebulaGraph (新)
                                                         │
后端代码 ──切换环境变量──→ NebulaKnowledgeStore ──连接──→ ┘
```

**不需要改动的代码**：
- `backend/main.py`（所有 API 接口）
- `backend/routers/*.py`（所有路由，包括可视化前端）
- `backend/services/extractor.py`（AI 提取管道）
- `backend/services/intelligence.py`（情报收集管道）
- `mcp-server/main.py`（MCP Server）
- `build_network.py`（构建脚本，仅需改 import）

**需要修复/增强的代码**：
- `backend/services/nebula_store.py`（修复上述 4 个问题）
- `nebula_init.py`（更新 Schema 为新层级模型）
- `backend/services/graph_store.py`（无需改，已支持切换）

---

## 4. 哪些工作 NebulaGraph 本身就能实现

以下是我们在 SQLite 版本中**手写了大量代码**实现的功能，迁移到 NebulaGraph 后**可以用 nGQL 一行语句替代**：

### 4.1 路径查找

**SQLite 版本**（`knowledge_base.py:195-210`，手写 BFS）：
```python
def find_path(self, src, dst):
    visited = set()
    queue = [[src]]
    while queue:
        path = queue.pop(0)
        node = path[-1]
        if node == dst:
            return path
        if node in visited:
            continue
        visited.add(node)
        for e in self.query_edges(src_vid=node):
            neighbor = e["dst_vid"] if e["src_vid"] == node else e["src_vid"]
            if neighbor not in visited:
                queue.append(path + [neighbor])
    return []
```

**NebulaGraph 版本**（一行 nGQL）：
```ngql
FIND SHORTEST PATH FROM "node_001" TO "node_002" OVER * YIELD path AS p;
```

### 4.2 邻居遍历（N 跳）

**SQLite 版本**（`knowledge_base.py:163-185`，手写 DFS）：
```python
def get_neighbors(self, vid, depth=1):
    visited = set()
    result_nodes = {}
    result_edges = []
    def dfs(current_vid, d):
        if d > depth or current_vid in visited:
            return
        visited.add(current_vid)
        node = self.get_vertex(current_vid)
        if node:
            result_nodes[current_vid] = node
        if d < depth:
            for e in self.query_edges(src_vid=current_vid):
                ...
```

**NebulaGraph 版本**：
```ngql
GET SUBGRAPH 2 STEPS FROM "node_001" YIELD VERTICES AS nodes, EDGES AS edges;
```

### 4.3 按类型批量查询

**SQLite 版本**（`knowledge_base.py:134-147`，SQL LIKE）：
```python
c.execute("SELECT * FROM vertices WHERE tag = ? AND props LIKE ? LIMIT ?", ...)
```

**NebulaGraph 版本**：
```ngql
MATCH (v:technology) WHERE v.technology.name CONTAINS "电池" RETURN v LIMIT 50;
```

### 4.4 图统计

**SQLite 版本**（`knowledge_base.py:212-216`，COUNT(*)）：
```python
c.execute("SELECT COUNT(*) as cnt FROM vertices WHERE tag = ?", (tag,))
```

**NebulaGraph 版本**：
```ngql
MATCH (v:technology) RETURN count(v) AS cnt;
```

### 4.5 全文搜索（NebulaGraph 内置全文索引）

SQLite 用 `LIKE '%keyword%'`，NebulaGraph 可以创建全文索引：
```ngql
-- 1. 创建全文索引（需启动 Elasticsearch listener）
CREATE ELASTIC INDEX tech_full_text ON technology(name, description);

-- 2. 查询
LOOKUP ON technology WHERE MATCH(name, "电池") YIELD id(v) AS vid, properties(v) AS props;
```

> 如果不部署 Elasticsearch，也可以用 `CONTAINS` 做简单文本匹配。

### 4.6 你**不需要**重写的部分

以下代码**无论用 SQLite 还是 NebulaGraph 都需要保留**，因为它们是应用层逻辑：

| 功能 | 代码 | 原因 |
|------|------|------|
| Canvas 力导向渲染 | `graph_viz.py` 前端 JS | NebulaGraph 是后端数据库，不负责前端渲染 |
| AI 提取 LLM 调用 | `extractor.py` | LLM 调用与数据库无关 |
| AI 自动关联 | `main.py` 的 `/api/relate` | 语义匹配逻辑在应用层 |
| MCP Server | `mcp-server/main.py` | MCP 协议层与数据库无关 |
| 层级颜色/折叠/标签透明度 | `graph_viz.py` 前端 | 纯前端视觉逻辑 |

---

## 5. NebulaGraph 安装与初始化

### 5.1 安装方式

#### 方式 A：Docker（推荐，但需能访问 Docker Hub）

```bash
# 安装 NebulaGraph 集群
git clone https://github.com/vesoft-inc/nebula-docker-compose.git
cd nebula-docker-compose
docker-compose up -d

# 验证
docker exec -it nebula-docker-compose_graphd_1 nebula -u root -p nebula
```

#### 方式 B：RPM/DEB 包（Linux，无需 Docker）

```bash
# 下载 RPM 包
wget https://github.com/vesoft-inc/nebula/releases/download/v3.8.0/nebula-graph-3.8.0.el8.x86_64.rpm
rpm -ivh nebula-graph-3.8.0.el8.x86_64.rpm

# 启动
/usr/local/nebula/scripts/nebula.service start all
```

#### 方式 C：源码编译（最灵活，但最慢）

```bash
git clone https://github.com/vesoft-inc/nebula.git
cd nebula && mkdir build && cd build
cmake .. && make -j4
```

> **企业网络注意**：如果无法下载 Docker 镜像或 RPM 包，可尝试：
> 1. 用个人手机热点下载
> 2. 在外部网络环境下载后用 U 盘拷贝
> 3. 用内网镜像源（如有）

### 5.2 连接验证

```bash
# 安装 Python 客户端
pip install nebula3-python

# 测试连接
python -c "
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config
config = Config()
config.max_connection_pool_size = 10
pool = ConnectionPool()
pool.init([('127.0.0.1', 9669)], config)
session = pool.get_session('root', 'nebula')
print(session.execute('SHOW SPACES;'))
session.release()
pool.close()
"
```

---

## 6. Schema 设计（强化版）

### 6.1 新建 Schema（替代旧版 `nebula_init.py`）

创建文件 `nebula_init_v2.py`：

```python
"""
NebulaGraph Schema V2 — 适配 4 级层级模型
Tag: domain, subdomain, technology, material
Edge: belongs_to, supports
"""
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config
import time, os

HOST = os.getenv("NEBULA_HOST", "127.0.0.1")
PORT = int(os.getenv("NEBULA_PORT", "9669"))
USER = os.getenv("NEBULA_USER", "root")
PWD = os.getenv("NEBULA_PASSWORD", "nebula")
SPACE = os.getenv("NEBULA_SPACE", "auto_knowledge")

TAGS = {
    "domain":      ["name string", "level int", "description string default ''"],
    "subdomain":   ["name string", "level int", "description string default ''"],
    "technology":  ["name string", "level int", "description string default ''", "trl int default -1", "status string default ''"],
    "material":    ["name string", "level int default 0", "material_type string default 'news'", "title string default ''", "summary string default ''"],
}

EDGES = {
    "belongs_to":  ["weight double default 1.0"],
    "supports":    ["weight double default 1.0", "remark string default ''"],
}

def run(session, nql):
    resp = session.execute(nql)
    if not resp.is_succeeded():
        raise RuntimeError(f"FAILED: {nql}\n  msg: {resp.error_msg()}")
    return resp

def init():
    config = Config()
    config.max_connection_pool_size = 10
    pool = ConnectionPool()
    pool.init([(HOST, PORT)], config)
    session = pool.get_session(USER, PWD)

    print(f"[1/4] 创建 Space: {SPACE}")
    run(session, f"CREATE SPACE IF NOT EXISTS {SPACE}(vid_type=FIXED_STRING(256), partition_num=10, replica_factor=1);")
    time.sleep(3)  # 等待 space 生效
    run(session, f"USE {SPACE};")

    print("[2/4] 创建 Tag")
    for tag, props in TAGS.items():
        run(session, f"CREATE TAG IF NOT EXISTS {tag}({', '.join(props)});")
        print(f"  Tag: {tag}")

    print("[3/4] 创建 Edge")
    for edge, props in EDGES.items():
        run(session, f"CREATE EDGE IF NOT EXISTS {edge}({', '.join(props)});")
        print(f"  Edge: {edge}")

    time.sleep(3)  # 等 schema 生效
    print("[4/4] 创建索引")
    run(session, f"USE {SPACE};")
    run(session, "CREATE TAG INDEX IF NOT EXISTS idx_domain_name ON domain(name(64));")
    run(session, "CREATE TAG INDEX IF NOT EXISTS idx_subdomain_name ON subdomain(name(64));")
    run(session, "CREATE TAG INDEX IF NOT EXISTS idx_tech_name ON technology(name(64));")
    run(session, "CREATE TAG INDEX IF NOT EXISTS idx_material_name ON material(name(64));")
    run(session, "CREATE TAG INDEX IF NOT EXISTS idx_tech_level ON technology(level);")
    print("  索引创建完成")

    # 验证
    run(session, f"USE {SPACE};")
    r = run(session, "SHOW TAGS;")
    print(f"\n验证 Tags: {r}")
    r = run(session, "SHOW EDGES;")
    print(f"验证 Edges: {r}")

    session.release()
    pool.close()
    print("\n✅ Schema V2 初始化完成！")

if __name__ == "__main__":
    init()
```

### 6.2 Schema 对比

| 旧 Schema (`nebula_init.py`) | 新 Schema V2 |
|------------------------------|-------------|
| 7 Tag: category/technology/component/standard/patent/resource/document | 4 Tag: domain/subdomain/technology/material |
| 9 Edge: belongs_to/contains/relates_to/has_standard/has_patent/references/implements/depends_on/derived_from | 2 Edge: belongs_to/supports |
| 无索引 | 6 个索引（name + level） |

---

## 7. 数据迁移脚本

### 7.1 从 SQLite 导出到 NebulaGraph

创建文件 `migrate_to_nebula.py`：

```python
"""
从 SQLite 导出全部数据，写入 NebulaGraph
"""
import sqlite3, json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from services.knowledge_base import DB_PATH
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config

NEBULA_HOST = os.getenv("NEBULA_HOST", "127.0.0.1")
NEBULA_PORT = int(os.getenv("NEBULA_PORT", "9669"))
NEBULA_USER = os.getenv("NEBULA_USER", "root")
NEBULA_PASSWORD = os.getenv("NEBULA_PASSWORD", "nebula")
SPACE = os.getenv("NEBULA_SPACE", "auto_knowledge")

# tag 映射：SQLite tag → NebulaGraph tag
TAG_MAP = {
    "technology": "technology",  # 可能是 L1/L2/L3，按 level 区分
    "domain": "domain",
    "subdomain": "subdomain",
    "material": "material",
    # 旧 tag 兼容
    "category": "domain",
    "standard": "material",
    "patent": "material",
    "resource": "material",
    "document": "material",
    "component": "material",
}

def val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    return repr(str(v))

def main():
    # 1. 读 SQLite
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM vertices")
    vertices = c.fetchall()
    c.execute("SELECT * FROM edges")
    edges = c.fetchall()
    c.execute("SELECT * FROM node_notes")
    notes = c.fetchall()
    conn.close()
    print(f"SQLite: {len(vertices)} 节点, {len(edges)} 边, {len(notes)} 备注")

    # 2. 连 NebulaGraph
    config = Config()
    config.max_connection_pool_size = 10
    pool = ConnectionPool()
    pool.init([(NEBULA_HOST, NEBULA_PORT)], config)
    session = pool.get_session(NEBULA_USER, NEBULA_PASSWORD)
    session.execute(f"USE {SPACE};")

    # 3. 导入节点
    print("导入节点...")
    for i, v in enumerate(vertices):
        vid = v["vid"]
        old_tag = v["tag"]
        props = json.loads(v["props"])
        level = props.get("level", 2)

        # 根据 level 决定 tag
        if old_tag in ("domain", "category") or level == 1:
            nebula_tag = "domain"
        elif old_tag in ("subdomain",) or level == 2:
            nebula_tag = "subdomain"
        elif old_tag in ("material", "standard", "patent", "resource", "document", "component") or level == 0:
            nebula_tag = "material"
        else:
            nebula_tag = "technology"

        # 构建属性
        cols = []
        vals = []
        for k, vv in props.items():
            cols.append(k)
            vals.append(val(vv))
        # 确保 level 存在
        if "level" not in cols:
            cols.append("level")
            vals.append(str(level if level is not None else 2))

        nql = f"INSERT VERTEX {nebula_tag}({', '.join(cols)}) VALUES '{vid}': ({', '.join(vals)});"
        try:
            session.execute(nql)
        except Exception as e:
            print(f"  [WARN] 节点 {vid}: {e}")
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(vertices)}")
            time.sleep(0.2)

    # 4. 导入边
    print("导入边...")
    for i, e in enumerate(edges):
        etype = e["edge_type"]
        src = e["src_vid"]
        dst = e["dst_vid"]
        props = json.loads(e["props"])
        if props:
            cols = ", ".join(props.keys())
            vals = ", ".join(val(v) for v in props.values())
            nql = f"INSERT EDGE {etype}({cols}) VALUES '{src}' -> '{dst}': ({vals});"
        else:
            nql = f"INSERT EDGE {etype}() VALUES '{src}' -> '{dst}': ();"
        try:
            session.execute(nql)
        except Exception as ex:
            print(f"  [WARN] 边 {src}->{dst}: {ex}")
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(edges)}")

    # 5. 导入备注（写入 material 的 title/summary 或单独属性）
    print("导入备注...")
    for n in notes:
        vid = n["vid"]
        remarks = n["remarks"] or ""
        links = n["links"] or ""
        # 将备注写入 material tag 的属性（或扩展 tag）
        try:
            session.execute(f"UPDATE VERTEX ON material '{vid}' SET title={val(remarks[:200])}, summary={val(links)};")
        except Exception:
            pass  # 非 material 节点会失败，忽略

    # 6. 验证
    r = session.execute("MATCH (v) RETURN count(v) AS cnt;")
    print(f"\nNebulaGraph 节点数: {r}")
    r = session.execute("MATCH ()-[e]->() RETURN count(e) AS cnt;")
    print(f"NebulaGraph 边数: {r}")

    session.release()
    pool.close()
    print("\n✅ 迁移完成！")

if __name__ == "__main__":
    main()
```

### 7.2 从 data_2026.json 直接构建到 NebulaGraph

如果想跳过 SQLite 直接从原始数据构建：

```python
"""
从 data_2026.json 直接构建知识网络到 NebulaGraph
（改编自 build_network.py，仅替换 KnowledgeBase → NebulaKnowledgeStore）
"""
import json, os, sys, uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from services.graph_store import get_store

# 强制使用 nebula 引擎
os.environ["KNOWLEDGE_ENGINE"] = "nebula"

kb = get_store()

with open("data_2026.json", "r", encoding="utf-8") as f:
    entries = json.load(f)

# 复用 build_network.py 的 MAPPING 逻辑
# （将 build_network.py 的 MAPPING 字典和构建逻辑复制过来）
# ... 详见 build_network.py
```

---

## 8. 后端切换与配置

### 8.1 环境变量配置

在 `.env` 文件中添加/修改：

```bash
# 切换引擎：sqlite 或 nebula
KNOWLEDGE_ENGINE=nebula

# NebulaGraph 连接配置
NEBULA_HOST=127.0.0.1
NEBULA_PORT=9669
NEBULA_USER=root
NEBULA_PASSWORD=nebula
NEBULA_SPACE=auto_knowledge

# LLM 配置（保持不变）
LLM_API_KEY=your_key_here
LLM_API_URL=https://ai-models.rnd.yinwang.com/ai-platform-models-agent/v1
LLM_MODEL=DeepSeek-V4-Flash
```

### 8.2 引擎切换原理

`backend/services/graph_store.py` 已实现切换：

```python
def get_store():
    engine = os.getenv("KNOWLEDGE_ENGINE", "sqlite").lower()
    if engine == "nebula":
        from backend.services.nebula_store import NebulaKnowledgeStore
        store = NebulaKnowledgeStore()
        store.connect()
        return store
    from backend.services.knowledge_base import KnowledgeBase
    return KnowledgeBase()
```

**只需改环境变量，无需改任何业务代码。**

### 8.3 需要修复 `nebula_store.py` 的代码

以下是建议的修复（在新机器上直接替换 `backend/services/nebula_store.py`）：

```python
# 修复 1: query_vertices 包含新 tag
def query_vertices(self, tag=None, keyword="", limit=100):
    results = []
    tags = [tag] if tag else ["domain", "subdomain", "technology", "material"]
    # ... 其余逻辑不变

# 修复 2: update_vertex 用 UPDATE VERTEX ON 而非 DELETE+INSERT
def update_vertex(self, vid, tag=None, props=None):
    if not props:
        return True
    node = self.get_vertex(vid)
    if not node:
        return False
    new_tag = tag if tag else node.get("tag", "technology")
    sets = ", ".join(f"{k}={self._val(v)}" for k, v in props.items())
    try:
        self.execute(f"UPDATE VERTEX ON {new_tag} '{self._vid(vid)}' SET {sets};")
        return True
    except Exception:
        return False

# 修复 3: _vid 处理中文
def _vid(self, text):
    """VID 处理：保留中文字符，只替换特殊符号"""
    import re
    s = str(text)
    s = re.sub(r'[ /\(\)\[\]{}\'"\\]', '_', s)
    return s

# 修复 4: update_notes 用 UPDATE VERTEX ON
def update_notes(self, vid, remarks, links):
    node = self.get_vertex(vid)
    if not node:
        return {"remarks": "", "links": "", "updated_at": None}
    tag = node.get("tag", "technology")
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        self.execute(f"UPDATE VERTEX ON {tag} '{self._vid(vid)}' SET remarks={self._val(remarks or '')}, links={self._val(links or '')}, notes_updated_at={self._val(ts)};")
    except Exception:
        pass
    return self.get_notes(vid)
```

---

## 9. AI 提取管道的复用与强化

### 9.1 现有 AI 提取管道完全可复用

`backend/services/extractor.py` 的 `extract_knowledge_from_text()` 和 `save_extracted_knowledge()` 与数据库引擎无关——它们调用的是 `graph_store.get_store()` 返回的统一接口。

**迁移后无需改动**，只需确保：
1. `KNOWLEDGE_ENGINE=nebula` 环境变量生效
2. `nebula_store.py` 的 `insert_vertex`/`insert_edge`/`query_vertices` 正常工作

### 9.2 强化建议

#### 9.2.1 利用 NebulaGraph 的图查询增强 AI 关联

当前 `/api/relate` 接口把**所有节点**发给 LLM 让它选关联（最多 300 个候选）。可以用 NebulaGraph 的图查询先缩小范围：

```python
# 改进版：先用图查询找 2 跳邻居作为候选，再让 LLM 筛选
@app.post("/api/relate")
async def api_relate(req: RelateRequest):
    kb = get_store()
    node = kb.get_vertex(req.vid)
    
    # 先找 2 跳内的节点作为候选（NebulaGraph 原生图遍历）
    if hasattr(kb, 'execute_json'):
        # NebulaGraph: 用 nGQL 找 2 跳邻居
        nql = f"GET SUBGRAPH 2 STEPS FROM '{req.vid}' YIELD VERTICES AS nodes;"
        data = kb.execute_json(nql)
        candidates = [n for n in data if n.get("vid") != req.vid]
    else:
        # SQLite: 用原有的 query_vertices
        candidates = kb.query_vertices(limit=300)
    
    # 再让 LLM 从缩小后的候选中选关联
    # ...
```

#### 9.2.2 利用 NebulaGraph 全文索引加速搜索

```python
# NebulaGraph 全文索引查询（需部署 ES）
def full_text_search_nebula(query):
    nql = f'LOOKUP ON technology WHERE MATCH(name, "{query}") YIELD id(v) AS vid, properties(v) AS props;'
    return kb.execute_json(nql)
```

#### 9.2.3 图算法增强

NebulaGraph 内置图算法（需安装 nebula-algorithm）：

```bash
# 计算节点中心性（找出核心技术点）
./nebula-algorithm --algorithm=pagerank --space=auto_knowledge

# 社区发现（自动聚类技术领域）
./nebula-algorithm --algorithm=lpa --space=auto_knowledge
```

---

## 10. 可视化前端复用说明

### 10.1 前端代码无需改动

`backend/routers/graph_viz.py` 中的 Canvas 力导向渲染器（~1600 行前端 JS）**与数据库引擎完全无关**。它只调用后端 API：

| API | 用途 | 数据库无关 |
|-----|------|-----------|
| `GET /graph/data` | 获取全图节点+边 | ✅ 后端自动适配 |
| `POST /graph/node` | 添加节点 | ✅ |
| `PUT /graph/node/{vid}` | 编辑节点 | ✅ |
| `DELETE /graph/node/{vid}` | 删除节点 | ✅ |
| `POST /graph/edge` | 添加边 | ✅ |
| `DELETE /graph/edge` | 删除边 | ✅ |
| `PUT /graph/notes/{vid}` | 更新备注 | ✅ |
| `POST /api/extract` | AI 提取 | ✅ |
| `POST /api/relate` | AI 关联 | ✅ |

### 10.2 可选增强：NebulaGraph 原生可视化

NebulaGraph 有自己的可视化工具 **NebulaGraph Studio**（Web 界面），可以直接用 nGQL 查询并可视化：

```bash
# Docker 启动 Studio
docker run -d -p 7001:7001 vesoft/nebula-graph-studio
```

但我们的自研 Canvas 渲染器有以下 Studio 不具备的功能：
- 双击折叠/展开
- 层级筛选（选中层清晰，其余半透明）
- 标签分层透明度（L1 90% / L2 70% / L3 35% / L0 6%）
- 搜索高亮 + 备注匹配
- 节点编辑/连线管理/AI 提取/AI 关联

**建议**：保留自研前端，Studio 仅用于调试和 nGQL 查询测试。

---

## 11. 经验与建议

### 11.1 部署经验

1. **Docker 是最简单的部署方式**，但企业网络可能阻止 Docker Hub。备选方案：
   - 用 `nebula-graph-standalone` 单机版（一个容器搞定）
   - 用 RPM 包安装（Linux）
   - 源码编译（最慢但最灵活）

2. **NebulaGraph 端口**：
   - `9669` — graphd（查询入口，客户端连这个）
   - `9559` — metad（元数据）
   - `9779` — storaged（存储）
   - 防火墙需放行 9669

3. **内存需求**：NebulaGraph 集群至少 8GB 内存，单机版至少 4GB

### 11.2 Schema 设计建议

1. **VID 用字符串而非自增 ID**：方便跨数据库迁移，也方便人类阅读
   ```python
   # 推荐
   vid = f"tech_{uuid.uuid4().hex[:8]}"
   # 或
   vid = f"tech_{name}"  # 用名称做 vid（需确保唯一）
   ```

2. **Tag 属性尽量少**：NebulaGraph 的 Tag 属性过多会影响写入性能。核心属性放 Tag，扩展属性放备注

3. **索引必须建**：不建索引的 `MATCH` 查询会全表扫描
   ```ngql
   CREATE TAG INDEX idx_tech_name ON technology(name(64));
   ```

4. **Edge 必须有方向**：NebulaGraph 的边是有向的。`belongs_to` 是子→父，`supports` 是 material→tech_point

### 11.3 开发建议

1. **先跑通 Schema 初始化**：`python nebula_init_v2.py`，确保 Space/Tag/Edge/Index 都创建成功

2. **再跑数据迁移**：`python migrate_to_nebula.py`，从 SQLite 导入现有数据

3. **然后切换引擎启动后端**：
   ```bash
   # .env 中设置 KNOWLEDGE_ENGINE=nebula
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

4. **验证**：打开 `http://localhost:8000/graph`，确认图谱正常显示

5. **逐个修复 `nebula_store.py` 的问题**：
   - `update_vertex` 改用 `UPDATE VERTEX ON`
   - `query_vertices` 补全新 tag
   - `_vid` 处理中文
   - `update_notes` 改用 `UPDATE VERTEX ON`

### 11.4 性能建议

1. **批量插入**：NebulaGraph 支持 `INSERT VERTEX ... VALUES (...) (...) (...)` 批量插入，比逐条快 10 倍

2. **连接池**：`nebula_store.py` 已用 ConnectionPool（`max_connection_pool_size=10`），可调大

3. **异步查询**：NebulaGraph Python 客户端支持异步，可在 `nebula_store.py` 中改为 `async`

4. **缓存**：对于不常变的图数据（如全图节点列表），可在应用层加缓存

### 11.5 企业网络环境下的注意事项

1. **pip 安装**：`nebula3-python` 可能需要从 PyPI 下载，企业代理可能拦截。使用：
   ```bash
   pip install nebula3-python --proxy http://proxy.huawei.com:8080 --trusted-host pypi.org
   ```

2. **Docker 镜像**：如果无法 `docker pull`，可尝试从内部镜像源拉取，或离线导入 `.tar` 镜像

3. **SSL 证书**：企业代理的 SSL 证书可能不被信任，Python 中用 `verify=False`

4. **LLM 服务**：保持 `.env` 中的华为内部推理服务配置不变

---

## 12. 验证清单

迁移完成后，按以下清单验证：

- [ ] `python nebula_init_v2.py` 成功创建 Space/Tag/Edge/Index
- [ ] `python migrate_to_nebula.py` 成功导入 350+ 节点
- [ ] `KNOWLEDGE_ENGINE=nebula` 后后端启动无报错
- [ ] `GET /graph/data` 返回正确的节点和边
- [ ] `http://localhost:8000/graph` 图谱正常渲染
- [ ] 搜索功能正常（输入关键词高亮节点）
- [ ] 双击折叠/展开正常
- [ ] 层级筛选正常
- [ ] 添加节点正常
- [ ] 编辑节点正常
- [ ] 删除节点正常（连带删除边）
- [ ] 添加/删除连线正常
- [ ] 备注更新正常
- [ ] `POST /api/extract` AI 提取正常
- [ ] `POST /api/relate` AI 关联正常
- [ ] MCP Server 7 个工具正常

---

## 附录：关键文件速查

| 文件 | 作用 | 迁移时是否需改 |
|------|------|--------------|
| `backend/main.py` | FastAPI 入口 | ❌ 不改 |
| `backend/routers/graph_viz.py` | 图可视化（1600 行） | ❌ 不改 |
| `backend/routers/about.py` | 介绍页 | ❌ 不改 |
| `backend/routers/knowledge.py` | 知识管理 | ❌ 不改 |
| `backend/routers/search.py` | 搜索 | ❌ 不改 |
| `backend/routers/classification.py` | 分类 | ❌ 不改 |
| `backend/services/graph_store.py` | 引擎工厂 | ❌ 不改 |
| `backend/services/knowledge_base.py` | SQLite 引擎 | ❌ 不改（保留备用） |
| `backend/services/nebula_store.py` | NebulaGraph 引擎 | ✅ **需修复 4 处** |
| `backend/services/extractor.py` | AI 提取 | ❌ 不改 |
| `backend/services/intelligence.py` | 情报收集 | ❌ 不改 |
| `backend/config.py` | 配置 | ❌ 不改 |
| `backend/database/nebula_client.py` | 旧版客户端 | ❌ 不改（未使用） |
| `mcp-server/main.py` | MCP Server | ❌ 不改 |
| `build_network.py` | 构建脚本 | ⚠️ 仅改 import（可选） |
| `nebula_init.py` | 旧版 Schema | ⚠️ 用 `nebula_init_v2.py` 替代 |
| `data_2026.json` | 原始数据 | ❌ 不改 |
| `data/knowledge.db` | SQLite 数据库 | ❌ 不改（迁移源） |
| `.env` | 环境变量 | ✅ 改 `KNOWLEDGE_ENGINE=nebula` |
