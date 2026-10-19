# 数据导入流程（蓝区开发 / 绿区导数据）

目标：资料提炼正确、层级合理、材料挂接准确，最终图谱清晰。

## 总流程

```
原始资料
  → ① AI 第一轮：筛选 + 技术点/材料抽取
  → ② 人工审查（必过）
  → ③ AI 第二轮：入库质检（import_with_ai_review.py）
  → ④ --commit 写入 Nebula
  → ⑤ 工作台「全貌」验收
```

蓝区把工具与脚本做稳；绿区 WSL2 装好环境后，主要做 ①②④⑤（③ 需配置绿区内网 LLM）。

## 文件格式

模板：`research/templates/extract_batch.template.json`

- `human_review.passed` 必须为 `true` 才会进入导入（显式 `false` 会被拒绝）
- `extraction` 字段与工作台「AI 协助入库」一致：`domain` / `subdomain` / `tech_points` / `materials` / `tech_material_links`

## 命令

```bash
# 在项目根、已配置 .env 的 LLM、Nebula 已启动

# 只做第二轮 AI 质检（默认不写库）
python3 scripts/import_with_ai_review.py research/my_batch.json

# 查看报告
# research/import_runs/<时间戳>/<item_id>/review.json
# research/import_runs/<时间戳>/<item_id>/revised.json

# 质检通过后入库
python3 scripts/import_with_ai_review.py research/my_batch.json --commit

# 无 LLM 时仅规则检查
python3 scripts/import_with_ai_review.py research/my_batch.json --rules-only

# 强制入库（不推荐，仅应急）
python3 scripts/import_with_ai_review.py research/my_batch.json --commit --force
```

## 第二轮 AI 查什么

- 层级是否乱（材料当技术点、系统名错层）
- 命名过长/重复/与库内节点冲突
- 材料类型与摘要是否够用
- 材料↔技术点链接是否漏连、错连
- 给出可直接入库的 `revised.json`

有 `error` 级问题 → `approved=false`，默认不 `--commit`。

## 绿区注意

- 需要 WSL2 + 本工具包；导入数据前先 `health` 正常
- LLM 用**绿区内网** Key（`.env`），不要用蓝区密钥外传
- 原始机密资料留在绿区；只把结构化 JSON 与图谱库放在绿区
