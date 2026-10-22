# 知识库快照（knowledge_base）

本目录保存**知识图谱内容**的快照，用于把工具迁移到新环境后重新灌入知识节点。
代码/工具迁移见仓库根 `REPLICATE.md`、`README.md`、`setup.bat` / `run.bat`。

## 版本

- 当前版本：`20261022`（见 `VERSION`）
- 仓库标签：`kb-20261022`
- 导出格式：6 层架构导出（`tree` / `nodes` / `edges`），与 `/export/knowledge` 同构，
  可直接被 `/import/knowledge` 导入。

## 内容

| 领域 | vid | 节点 | 边 | 文件 |
|------|-----|------|----|------|
| 底盘技术 | `domain_chassis_tech` | 237 | 240 | `domain_chassis_tech.json` / `.md` |
| 整车信息系统 | `dom_7c85bfb782` | 200 | 199 | `dom_7c85bfb782.json` / `.md` |

导出统计以 `manifest.json` 为准。`*.md` 为便于阅读的树状目录，导入请用 `*.json`。

说明：
- `domain_chassis_tech.json` 已剔除 1 条非法边（`material` 不应有 `belongs_to`），
  并把 1 个误挂在 `children` 下的文档移入 `materials`（按 `supports` 处理）。
- 本目录不含 `.env`、数据库、Nebula 运行数据，也不含写入口令。

## 迁移后导入

1. 按 `setup.bat` / `REPLICATE.md` 起好后端（默认 `http://127.0.0.1:8001`）。
2. 校验（不写库）：

   ```bash
   curl -X POST "http://127.0.0.1:8001/import/knowledge?dry_run=true" \
        -H "Content-Type: application/json" \
        --data-binary "@knowledge_base/domain_chassis_tech.json"
   ```

3. 写入（需要写入口令 / Bearer token）：

   ```bash
   curl -X POST "http://127.0.0.1:8001/import/knowledge" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer <WRITE_PASSWORD>" \
        --data-binary "@knowledge_base/domain_chassis_tech.json"
   ```

   或使用附带的 `scripts/import_snapshot.py`：

   ```bash
   python scripts/import_snapshot.py knowledge_base/domain_chassis_tech.json --token <WRITE_PASSWORD>
   ```

导入按「父 + 层级 + 名称」定位/新建节点，`vid` 保留时可直接复用；重复导入是幂等的
（已存在的节点会跳过或按名称同名处理）。

## 重新导出一份快照

```bash
curl "http://127.0.0.1:8001/export/knowledge?root=domain_chassis_tech&from_level=domain&to_level=material&fmt=json" \
     -o knowledge_base/domain_chassis_tech.json
```
