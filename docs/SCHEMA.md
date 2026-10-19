# Nebula Schema：auto_innovation_kg

Space：`auto_innovation_kg`  
vid：`FIXED_STRING(64)`（推荐 `dom_xxx` / `sub_xxx` / `tech_xxx` / `mat_xxx`）

> 业务上是多分支向下发散的技术点 DAG（可交叉汇合）；下列 Tag 为过渡实现，domain/subdomain 表示较粗技术簇，不必等同于固定「第 1/2 层」。

## Tags

### domain（粗技术簇，过渡名 L1）
| 属性 | 类型 | 说明 |
|------|------|------|
| name | string | 领域名 |
| description | string | 可选 |

### subdomain（L2）
| 属性 | 类型 | 说明 |
|------|------|------|
| name | string | 子领域名 |
| description | string | 可选 |

### technology（L3）
| 属性 | 类型 | 说明 |
|------|------|------|
| name | string | 技术点名称（核心） |
| description | string | 简述 |
| keywords | string | 可选，逗号分隔 |
| status | string | draft / active / deprecated |

### material（L0）
| 属性 | 类型 | 说明 |
|------|------|------|
| name | string | 材料简称 |
| material_type | string | paper / patent / news / doc |
| title | string | 原始标题 |
| summary | string | 摘要 |
| source_url | string | 来源链接 |
| published_at | string | 日期字符串 |

## Edges

| Edge | 方向 | 属性 | 含义 |
|------|------|------|------|
| belongs_to | child → parent | weight double | 子领域→领域；技术点→子领域 |
| supports | material → technology | weight double | 材料支撑技术点 |
| relates_to | technology → technology | relation_type string, weight double | 技术点横向关联 |

## 索引

- `technology(name)`
- `domain(name)`
- `subdomain(name)`
- `material(name)`
