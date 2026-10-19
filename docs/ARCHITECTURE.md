# 架构说明

## 目标

用 NebulaGraph 承载汽车创新「技术点网络」：多分支向下发散、允许交叉汇合，最底层挂支撑材料；工作台 + API + MCP 统一读写。

## 概念模型（业务）

```
汽车创新技术库
  ├─ 底盘结构 → 驱动 → 电机驱动 → 轮毂电机 → 热管理 / 效率…
  ├─ 底盘结构 → 制动 → …
  └─ 驱动 + 制动 共同支撑 → 驱制一体 → …
支撑材料（论文 / 专利 / 标准 / 文档 / 资讯）──supports──→ 一个或多个技术点
```

要点：

- 本质是 **DAG**（可多父、多子），不是死板的 L1/L2/L3 三层树
- 「第几层」可后续由支配子点数、支撑材料数等 **派生**，不必手写层号
- 材料原件先走企业共享盘 / 链接；对象存储（MinIO 等）后置

## 当前实现模型（过渡）

为兼容已有种子与 API，图 Tag 暂仍为：

| Tag | 含义（过渡） |
|-----|----------------|
| domain | 较粗技术簇（如底盘结构） |
| subdomain | 中层技术簇（如驱动） |
| technology | 较细技术点 |
| material | 支撑材料元数据 |

边：`belongs_to`（子→父）、`supports`（材料→技术点）、`relates_to`（横向/交叉）

后续资料库精细化时，可收敛为「统一 technology + material」，domain/subdomain 降为粗粒度技术点或标签。

## 运行分层

```
工作台 UI / Cursor MCP
        ↓
FastAPI（CRUD · 子图 · 全貌 · AI 协助）
        ↓
NebulaGraph（WSL1 原生 3.8 · Space: auto_innovation_kg）
```

材料文件：元数据在 Nebula；文件本体后接共享盘 / 本地目录（暂不强制 MinIO）。

## 与旧 SQLite demo（reference/）对照

| 能力 | 旧 demo | 当前 Nebula | 状态 |
|------|---------|-------------|------|
| 图引擎 | SQLite / 可选 Nebula | **仅 Nebula** | 已升级 |
| 搜索 / 列表 / 子图 | 有 | 有 | OK |
| 全貌图 | 弱 | `/overview` + UI | OK |
| 节点详情抽屉 | 有 | 有 | OK |
| 手工添加技术点 | 有 | 有 | OK |
| **删除节点** | API+UI | API+MCP+**UI** | 本次补齐 |
| 编辑节点 / 删边 | UI 有 | API 有，UI 后补 | 部分 |
| **AI 抽取** | `/api/extract` | `/ai/extract` | 本次接入 |
| **AI 翻译协助** | extract `translate` | 同左 + `/ai/assist` | 本次接入 |
| **AI 写入图谱** | extract `save` | extract `save` / `/ai/commit` | 本次接入 |
| AI 自动关联 relate | 有 | 后补 | 待做 |
| 材料文件库 | 弱 | 后置（共享盘） | 待做 |
| 派生层级 | 无 | 设计已定，实现后置 | 待做 |

不做双引擎；`reference/` 只读对照，不参与构建。

## 数据与 AI 策略

1. Schema + 手工/种子验证读写（已完成）
2. 工作台具备删改与 AI 投喂闭环（进行中）
3. 你提供高质量资料后：批量抽取 → 人工确认 → 入库
4. 派生层级、材料文件同步、交叉边增强随资料密度迭代

## AI 协助三条路径（可并存）

| 路径 | 适用 | 做法 |
|------|------|------|
| **A. Cursor + MCP（推荐）** | 内网模型不可达时 | 在 Cursor 打开本仓库对话，把资料发给助手；助手用 `kg_*` / 抽取结果直接写入 Nebula。工作台负责查看/核对。 |
| **B. 工作台 ↔ Cursor 接力** | 想留在页面流程 | 「生成协助提示词」→ Cursor 返回 JSON → 粘贴「解析」→「确认写入」。 |
| **C. 内网 LLM 直连** | VM 能解析公司模型域名 | `.env` 配 `LLM_API_URL` / `LLM_API_KEY` / `LLM_MODEL`，点「内网 LLM 抽取」。 |

说明：Cursor 订阅额度**不能**当成浏览器里的 OpenAI 兼容 Key；「借助 Cursor」本质是人在 Cursor 对话，或 MCP 工具由助手调用，而不是页面静默调用 Cursor。

华为内网示例：

- `LLM_API_URL=https://ai-models.rnd.yinwang.com/ai-platform-models-agent/v1`
- 需本机 DNS/VPN 可达，并填写平台真实 `LLM_MODEL`
