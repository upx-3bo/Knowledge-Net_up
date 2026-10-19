# AI4KnowledgeNet · 绿区离线部署与入库

蓝区打包 → 绿区解压安装 → **在绿区直接读材料入库**（无需再把材料传回蓝区）。

## 包内结构

```
AI4KnowledgeNet-green-*/
  INSTALL_绿区.md          ← 本文
  scripts/install_green_wsl.sh
  app/                     ← 工作台 + API + 脚本
  offline/nebula/          ← NebulaGraph 原生二进制
  offline/wheels/          ← Python 离线依赖
```

## 绿区环境要求（与蓝区一致时最省事）

- Windows + **WSL1 Ubuntu**（无 Docker / 无嵌套虚拟化也可）
- 或 Linux（可把 `offline/nebula` 装到 `/usr/local/nebula`，流程相同）

## 安装（WSL）

在绿区把压缩包解到例如 `C:\Users\<你>\Desktop\`，然后：

```powershell
wsl -d Ubuntu -u root -- bash /mnt/c/Users/<你>/Desktop/AI4KnowledgeNet-green-XXXX/scripts/install_green_wsl.sh
```

脚本会：

1. 安装 Nebula 到 `/usr/local/nebula`（若尚未安装）
2. 用 `offline/wheels` 离线安装 Python 依赖
3. 启动 Nebula + 初始化空库 `auto_innovation_kg`
4. 启动 API / 工作台（默认 `http://127.0.0.1:8000/`）

手动启动（装完之后）：

```powershell
wsl -d Ubuntu -u root -- bash <解压目录>/app/scripts/start_nebula_wsl1.sh
wsl -d Ubuntu -u root -- bash <解压目录>/app/scripts/start_api_wsl.sh
```

## 在绿区入库（推荐路径）

材料留在绿区，**不要**再传回蓝区。蓝区负责把工具做稳；绿区侧重「导数据」。

推荐流水线见 `app/docs/DATA_IMPORT.md`：

1. AI 第一轮抽取 → **人工审查** → 填入 `extract_batch` JSON（模板在 `app/research/templates/`）
2. AI 第二轮质检并入库：
   ```bash
   cd <解压目录>/app
   python3 scripts/import_with_ai_review.py research/my_batch.json          # 只审查
   python3 scripts/import_with_ai_review.py research/my_batch.json --commit # 通过后写入
   ```
3. 浏览器打开工作台点「全貌」验收

### 方式 A：工作台手工 / 粘贴

1. 浏览器打开 `http://127.0.0.1:8000/`
2. 左侧录入；或粘贴文本用「解析 / AI 抽取」（需绿区内网 LLM：`app/.env` 配 `LLM_API_*`）
3. 确认写入后点「全貌」

### 方式 B：Cursor MCP（可选）

用 `kg_add_technology` / `kg_add_material` / `kg_add_relation` 入库。

## 与蓝区数据的关系

| 内容 | 建议 |
|------|------|
| 工具代码 / Nebula / 依赖 | 蓝区打包带来 |
| 底盘 demo 数据 | 可选：绿区可重新 seed，或空库后只灌绿区业务 |
| 绿区机密材料 | **只在绿区入库**，不要回传蓝区 |
| 蓝区已有图 | 默认不迁移；若要同步需单独做导出（nGQL dump），本包默认是「绿区独立库」 |

## 验收

```text
GET http://127.0.0.1:8000/health   → status ok
GET http://127.0.0.1:8000/stats    → 各层计数
工作台「全貌」可出图
```

## 注意

- 打包**不含** `.env` 密钥；绿区按需复制 `.env.example` → `.env`
- 免费公网隧道（Pinggy 等）勿用于绿区；绿区一般只本机或内网访问
- 若绿区 Python / glibc 版本与蓝区差太多，wheels 可能装不上，需在绿区用内网 PyPI 重装同版本包
