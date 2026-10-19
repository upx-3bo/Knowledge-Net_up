# 六层技术架构 + 二维/三维树状布局 —— 可复用实现指南（SKILL）

> 适用目标：本仓库（`AI4KnowledgeNet`）之外的其它知识库项目，若想复刻「车辆→领域→子域→模块→技术点→文档」六层架构，以及二维/三维树状图（同心圆·树状·力导向 / 分层·环形）的呈现能力，直接按本文档迁移与调整。
>
> 文档口径基于当前已上线、并在无头浏览器逐项验证过的实现。涉及文件：
> - 后端：`backend/models.py`、`backend/store.py`、`backend/routers/graph.py`、`backend/services/extractor.py`
> - 前端：`frontend/app.js`、`frontend/index.html`、`frontend/styles.css`
> - 数据：NebulaGraph（graph 数据库），服务 `uvicorn backend.main:app` 静态托管 `frontend/`

---

## 0. 一句话架构

把知识按 6 个层级组织成一棵/多棵树：
**车辆(L0) → 领域(L1) → 子域(L2) → 模块(L3) → 技术点(L4) → 文档(L5)**

- `车辆` 是虚拟根球（数量 1），组织多个领域，本身不挂具体内容。
- `领域` 是最大的知识簇；每个领域及其子树在视觉上自成体系（“太阳系” / 独立平面 / 独立树）。
- `文档`（材料）是叶子，通过 `supports` 边支撑其上层技术点/模块。
- 层级关系用 `belongs_to` 边；文档支撑用 `supports` 边。

---

## 1. 数据模型（后端）

### 1.1 标签（Tag / Vertex 类型）

`backend/models.py` 的 `TagName`、`backend/store.py` 的 `TAGS` 顺序即前端 `LAYER_RANK` 的顺序（越靠后层级越低）：

| tag | 中文 | 属性（`TAG_PROPS`） | vid 前缀 |
|-----|------|----------------------|----------|
| `vehicle` | 车辆 | name, description | `veh_` |
| `domain` | 领域 | name, description | `dom_` |
| `subdomain` | 子域 | name, description | `sub_` |
| `module` | 模块 | name, description, keywords, status | `mod_` |
| `technology` | 技术点 | name, description, keywords, status | `tech_` |
| `material` | 文档 | name, material_type, title, summary, source_url, published_at | `mat_` |

- 6 个 tag 需在 `models.py`（校验）、`store.py`（`TAGS`/`TAG_PROPS`）、`graph.py`+`extractor.py`（`prefix` 映射）三处一致注册，否则新增节点会被校验拒绝。

### 1.2 边（Edge）

| edge_type | 方向 | 含义 | 属性 |
|-----------|------|------|------|
| `belongs_to` | 子 → 父 | 上下层归属 | weight |
| `supports` | 文档 → 技术点/模块 | 文档支撑上层 | weight |
| `relates_to` | 双向 | 平级关联（当前数据 0 条） | relation_type, weight |

### 1.3 总览预算（`store.py::GraphStore.overview`）

所有层级都要进 `quotas`，叶子(文档)配额要给足，否则全貌会砍掉内容：

```python
quotas = [
    ("vehicle", min(20, limit_nodes)),
    ("domain",   min(40, limit_nodes)),
    ("subdomain",min(120, limit_nodes)),
    ("module",   min(400, limit_nodes)),
    ("technology",min(600, limit_nodes)),
    ("material", min(400, limit_nodes)),
]
```

### 1.4 历史迁移经验（把旧结构升级成六层）

旧库可能是 `domain → subdomain → technology → material` 且技术点可嵌套（技术点挂技术点）。升级为六层时：

- 把**没有技术点父级**的 `technology` 重命名/复制成 `module`（位置 = 模块层），其下的嵌套技术点保持 `technology` = 技术点层。
- 重挂 `belongs_to`/`supports` 边到新 vid，删旧节点（`DELETE VERTEX … WITH EDGE`）。
- 先整库快照备份（`scripts/snapshot.py export`），迁移脚本用带 `nebula3` 的 venv python 直连 Nebula 执行。
- `store.overview` 的配额、前端常量、图例行全部要感知新 tag。

---

## 2. 前端工程要点

### 2.1 所有层级相关的“五件套”常量（`frontend/app.js` 46–81 行）

新增层级（或改名）时这 5 组与 1 组默认标注必须一起改：

```js
const TAG_LABEL = { vehicle:"车辆", domain:"领域", subdomain:"子域", module:"模块", technology:"技术点", material:"文档" };
const TAG_COLOR = { vehicle:"#0ea5e9", domain:"#3b82f6", subdomain:"#14b8a6", module:"#a855f7", technology:"#f59e0b", material:"#a3a3a3" };
const LAYER_RANK = { vehicle:0, domain:1, subdomain:2, module:3, technology:4, material:5 };  // 决定了“显示层级”筛选与各布局的深度
const NODE_SIZE  = { vehicle:42, domain:34, subdomain:24, module:20, technology:15, material:9 };
const label3dTags = new Set(["vehicle","domain","subdomain"]);  // 3D 默认常显标注的层级
```

### 2.2 URL hash 快捷入口（3528–3534 行）

支持 `#view=2d|3d`、`#layout=tree|radial|force`、`#tree3d=layer|ring`，便于分享指定视图，调试可直接拼 hash。

### 2.3 展示 / 筛选管线

```
overview?limit_nodes=1000&limit_edges=3000  (或 /subgraph/vid)
   → filterGraphPayload():
       filterByDomain()  // 领域筛选（含车辆根球保留）
       → filterByLayer()  // 显示层级（LAYER_RANK ≤/== cap）
       → applyIsolateFilter()  // 只看选中
       → enforceCanvasBudget()  // 超阈值裁文档/relates
       → aggregateEdgeList()    // 平行边聚合
   → drawGraph2d() 或 drawGraph3d()
```

- `filterByDomain`（1044 行）：用「沿 `belongs_to` 上溯能遇到所选领域即属该领域」判定子树；**选中某领域时显式保留 `vehicle` 球**及其到领域的边，满足“选领域也显示车辆”。
- `filterByLayer`（1010 行）：`r = LAYER_RANK[n.tag] ?? 99`，`'only'` 时 `r===cap`，否则 `r<=cap`。

> ⚠️ 反复出现的坑：`LAYER_RANK`/`levels` 的值为 **0** 时，`x || 99` 会把 0 变 99。这类默认值必须用 `??`（空值合并），不能用 `||`。全文已替换为 `??`。

### 2.4 静态资源版本号

`index.html` 里引用了 `app.js?v=20261010e` 这样的版本号。**前端一改就手动 +1 版本号**，否则用户浏览器可能命中缓存看不到更新。

---

## 3. 布局算法详解（核心）

### 3.1 二维 · 树状（`computeTreePositions`，1448 行）

自上而下根在顶部：

- `y = (level(vid) ?? 1 - 1) * ROW_H`，`ROW_H = 200` 为层级间距。
- `x`：子节点在水平带内展开，父节点置于子树带中线（`treeCenterLayout=true` 居中 / `false` 左对齐挂载）。
- `COL_W = 36` 保证同层兄弟最小水平间距；同层去重后水平推开。
- 根判定：`vehicle || domain || 无父` 都算根，`vehicle`（level0）自然在最顶行。
- 布局结果只是“初始种子”，物理关闭，节点可自由拖动；拖过之后坐标会被 `savedPositions` 记住。

### 3.2 二维 · 同心圆 / 力导向（`computeRadialPositions`，1824 行）

“太阳系”式（`layoutMode=radial` 与 `force` 共用同一套种子坐标）：

- 车辆固定在圆心 `(0,0)`。
- **领域**在车辆外圈 环形布置：半径 `RD = max(430, 200 + N*190)`，N 为领域数，等角均分。
- 每个领域再作为它**自己子体系**的圆心，用局部环半径铺开子树：
  - 子域环 `LR1=110`、模块环 `LR2=205`、技术点环 `LR3=310`、文档环 `LR4=410`。
  - 同一领域的同级节点围绕**该领域**环布，而不是绕车辆转圈——这就是“不同领域不同太阳系”的关键。
  - 子域在其领域局部 360° 内等角分带，其下的模块/技术点/文档落进各自子域的角带内。
- `force` 布局以同一套坐标为初始种子，物理撑开后领域仍保持分离。

### 3.3 三维 · 树状·分层（`computeTree3DDown`，1632 行）

满足“车辆原点，领域球沿 Z 错开，子树沿 −Z 居中向下平面展开”：

- 车辆 `(0,0,0)`。
- 领域排布规则（奇/偶不同）：
  - **偶数个**：全部沿 ±Y 以 `Y_OFF=510` 间隔展开，不含中心轴（如 `(0,+510,-Z)` / `(0,-510,-Z)`）。
  - **奇数个**：其中一个在 `(0,0,-Z)`，其余沿 ±Y 以 510 间隔展开。
  - 所有领域同高 `Z_BASE=510`（`(x,y,-510)`）。
- 每个领域子树：
  - 复用二维垂直树的排布 `computeTreePositions`（`x`=子树水平带、`y`=深度行×`ROW_H=200`），
  - 映射：`x' = x - 领域中心x`（以领域为轴心），`y = 领域y`（平铺在领域自身平面），`z = -510 - y(二维树)`（沿 −Z 逐层向下）。
  - 结果即“像二维树状一样，x 以领域节点为中心居中间下展开”。
- **文档（material）也走同一条逻辑**：上爬链 `parentOf` 必须同时纳入 `belongs_to` 和 `supports` 两条边，否则文档定位不到领域、Y 会掉到 0 或整层沉底。

### 3.4 三维 · 树状·环形（`computeTreePlaneXY` 1588 行 + `computeTreePlaneZ` 1547 行）

满足“领域有高度差，各领域子树在其各自平面上围绕领域环布”：

- `computeTreePlaneZ`：车辆 `z=0`；每个领域一层平行面，`z = -(领域序号+1) * PLANE_GAP(340)`。
- `computeTreePlaneXY`：以 `computeRadialPositions`（太阳系）为底，减去该领域中心 → **领域平面内的相对环布**（子域/模块/技术点/文档都围绕该领域球环形铺开）。
- ⚠️ 同上：`computeTreePlaneZ/XY` 的 `domainOf` 也要把 `supports` 纳入上爬链，文档才会落回自己领域的平面，而不是被丢到底层。

### 3.5 三维 · 非树状（同心圆/力导向）

`drawGraph3d` 里 `radial3dSeed = isTree3 ? null : computeRadialPositions(...)`，把二维太阳系坐标当 3D 初始种子，避免开局挤成一团。

---

## 4. 新增 / 调整一个层级的完整 Checklist

以“新增一个 tag `xxx`”为例，逐项勾选：

后端：
- [ ] `models.py`：`TagName = Literal[... "xxx" ...]`
- [ ] `store.py`：`TAGS` 元组按层级顺序插入；`TAG_PROPS["xxx"] = (…)`
- [ ] `store.py`：`overview()` 的 `quotas` 加入该层配额
- [ ] `graph.py` 与 `extractor.py`：`prefix` 映射加 `"xxx": "xx_"`
- [ ] （如已有旧数据）迁移脚本 + `snapshot.py export` 全量备份

前端：
- [ ] `app.js`：`TAG_LABEL / TAG_COLOR / LAYER_RANK / NODE_SIZE` 各加一组值
- [ ] `app.js`：`label3dTags` 视需要加入默认标注
- [ ] `index.html`：`tagFilter`、`layerCap` 下拉补 `<option>`；`label3d-layers` 加标注按钮；相关 tooltip/文案更新
- [ ] `styles.css`：`.graph3d-label.tag-xxx`（3D 浮动标签配色）
- [ ] 布局函数若要感知新层：`computeTreePositions`（树深自动由 `LAYER_RANK`+层级边算）；`computeRadialPositions`（若该层参与本体系环布，加一个 `LRn` 局部环，并在 `placeLocal` 里按 tag 分环）；3D 两模式（`computeTree3DDown` 复用树排布自动生效；环形靠 `computeRadialPositions` 自动生效）
- [ ] `index.html` 静态资源版本号 +1
- [ ] 无头浏览器验证（见 §6）

自动生效的机制：树深/层级排序几乎全部由 `LAYER_RANK` 驱动（`buildTreeLevels`、子节点排序、`filterByLayer`），所以“加常量→自动适配大部分布局”。

---

## 5. 已知坑（务必遵守）

1. **`LAYER_RANK`/`levels` 会用 0**，所有回退默认值用 `??` 而非 `||`（否则车辆/最顶层直接消失或错层）。
2. **`domainOf` 上爬链要同时含 `belongs_to` 和 `supports`**，否则 `material` 这类叶子定位不到领域：2D 里 Y 掉到 0、3D 环形里整层沉底。
3. **领域加 `vehicle` 父边后**，`filterByDomain` 不能再用「根==领域」判断子树，要用「上溯能遇到该领域」；否则选领域时只剩一个领域球。
4. **`overview` 预算漏层**＝全貌掉层级内容；叶子层配额要给足。
5. **改了前端要 +1 `index.html` 里的版本号**，否则用户看到旧缓存。

---

## 6. 验证与调试方法（无头实测）

本轮所有布局改动都靠“无头 Chrome + CDP 注入 JS”逐视图验证，强烈建议复刻：

1. 启动后端：`uvicorn backend.main:app --port 8000`（用带 `nebula3` 的 venv python）。
2. 用真实浏览器内核打开页面并注入探针读取页面内变量（顶层 `let` 变量不能走 `window.xxx`，直接用裸标识符）：

```powershell
# Chrome headless + remote debugging
chrome --headless=new --disable-gpu --remote-debugging-port=9333 http://127.0.0.1:8000/static/index.html#view=3d&layout=tree&tree3d=layer
# 用 WebSocket/CDP Runtime.evaluate 求值（示例）
(() => {
  const view = lastGraphPayload.view;                 // 顶层 let 可直接读
  const tags = view.nodes.reduce((m,n)=>{m[n.tag]=(m[n.tag]||0)+1;return m;},{});
  const p = network.getPositions();                    // 2D


  return JSON.stringify({ tags, vehPos: p['veh_chassis'] });
})()
```

3. 验证点：总节点/边数、各 tag 分布、车辆坐标、领域坐标、文档与其上层球是否同 Y/同面且 z 深一层。
4. 用 `snapshot.py export` 定期备份；大改前先导出。

---

## 7. 常见引导问题（FAQ）

- **“车辆没显示”** → 检查：`filterByDomain` 是否在上溯判定里把车辆所在路径搞断；`LAYER_RANK` 是否还在用 `||`；`overview` 配额是否含 vehicle。
- **“选了文档层，文档全沉底”** → `domainOf` 的 `parentOf` 是否只爬了 `belongs_to`（要加 `supports`）。
- **“领域都挤在一起”** → `computeRadialPositions` 是否仍是“全局分环”模板；应改成“领域各自为圆心的太阳系”。
- **“3D 树状分层里的文档没跟着上层球走”** → 同上（`supports` 上爬链缺失）。
- **“改了布局页面没变化”** → `index.html` 版本号没 +1，Ctrl+F5 或改版本号。

---

## 8. 变更记录（本仓库实际落地点）

| 能力 | 位置 | 说明 |
|------|------|------|
| 六层标签与属性 | `backend/models.py`、`store.py` | vehicle…material 六 tag + props |
| 总览配额 | `store.py::overview.quotas` | 六层配额（材料给足） |
| 前端五件套常量 | `app.js:46-81` | 标签/颜色/层级/尺寸/标注 |
| 展示管线 | `app.js:filterGraphPayload` | domain→layer→isolate→budget |
| 二维树状 | `app.js:computeTreePositions` | 自上而下居中树 |
| 二维同心圆/力导向 | `app.js:computeRadialPositions` | 太阳系（领域各自成系） |
| 3D 分层 | `app.js:computeTree3DDown` | 领域 Y 交错 + 子树沿 −Z 居中下展（含文档） |
| 3D 环形 | `app.js:computeTreePlaneZ/XY` | 领域平行面 + 面内环布（含文档） |
| 默认领域引导 | `app.js` boot | 默认展示 `底盘技术` 领域 |
| 静态资源版本 | `index.html` | app.js?v=… 需手动 +1 |
