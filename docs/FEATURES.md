# 功能清单与缺口

对照 `reference/Knowledge-Net_up` SQLite 工作台。

## 已具备

- Nebula 连接、Schema、种子、健康检查
- REST：顶点 CRUD、边创建/删除、详情、子图、全貌、路径
- 工作台：统计、搜索、列表、全貌/子图、**2D/3D 切换**、详情抽屉、添加技术点、删除节点
- AI：内网 LLM 抽取（可达时）；Cursor 协助提示词 + JSON 粘贴写入；短文本翻译/提炼
- MCP：查询、添加技术点/材料/关系、删除、文本抽取（需 LLM）
- **推荐入库路径**：Cursor 对话提炼 → MCP 写入（不依赖内网模型 DNS）

### 可视化（对齐 Nebula Explorer 思路）

- **画布预算**：2D 软阈值 / 硬阈值（参考 Explorer ≤5000 图元），顶栏显示点数·边数；超限优先裁材料与交叉边
- **分层全貌**：overview 按 domain→subdomain→technology→material 配额拉取，避免材料淹没结构
- **增量展开**：选中点「展开邻居」，合并进当前画布并尽量保留原坐标（Studio/Explorer 探索流）
- **边聚合**：同起终点同类型边合并计数（Edge Aggregation）
- **只看选中**：Dismiss Others，仅保留选中点一跳邻域
- **度加权球体**：出度/入度越高球体略大（Weight Degree）
- **度加权斥力（力导向）**：节点 `mass ∝ 关联度+层级`，Barnes-Hut 斥力 ∝ massᵢ·massⱼ；枢纽（如线控底盘）把邻接点/材料撑开，避免堆叠；「再加热」打散重叠（Explorer Reheat）
- **布局**：力导向（默认）/ 同心圆扇区聚类；侧栏可收起与拖宽

## 近期待补

- AI 自动关联（旧 `/api/relate`）
- 资料批量导入流水线
- 派生层级分数 / 交叉边表单
- 小地图（Minimap）/ 鸟瞰采样、环路与悬挂边检测

## 后置

- 企业共享盘 / 本地材料文件登记与溯源切片
- 技术点统一 Tag + 派生层级分数
- 情报自动抓取（旧 intelligence）
