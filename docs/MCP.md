# MCP 接入说明

## 工具列表

| 工具 | 作用 |
|------|------|
| `kg_stats` | 各层节点计数 |
| `kg_schema` | Tag / Edge 清单 |
| `kg_search` | 关键词搜索 |
| `kg_get_node` | 节点详情（vid 或 name） |
| `kg_subgraph` | 子图 |
| `kg_add_technology` | 加技术点并挂到领域/子领域 |
| `kg_add_material` | 加材料并 `supports` 到技术点 |
| `kg_add_relation` | 任意边 |
| `kg_delete_node` | 删节点 |
| `kg_extract_from_text` | AI 抽取（可选写入；需 `LLM_API_KEY`） |

## Cursor 配置

项目内已提供 `.cursor/mcp.json`。在 Cursor 打开本仓库后启用 MCP，或把该配置合并进用户级 MCP 设置。

前置：Nebula 三件套已启动（`scripts/start_nebula_wsl1.sh`）。

手动自检：

```powershell
wsl -d Ubuntu -u root -- bash /mnt/c/Users/Administrator/Desktop/up_x/AI4KnowledgeNet/scripts/run_mcp_wsl.sh
```

（stdio 服务会等待客户端；正常无报错即表示可被 Cursor 拉起。）
