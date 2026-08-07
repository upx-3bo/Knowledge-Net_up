from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["介绍页"])


@router.get("/about", response_class=HTMLResponse, summary="工具介绍页")
def about_page():
    return HTMLResponse(_render())


def _render():
    return """
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>汽车创新技术库 · AI 知识图谱平台</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * { box-sizing: border-box; }
  html, body { margin:0; padding:0; font-family:"Microsoft YaHei","PingFang SC",sans-serif; color:#222; background:#f5f6f8; }
  a { color:#2C5F8A; text-decoration:none; }
  /* Hero */
  .hero {
    background: linear-gradient(135deg, #1B3A5C 0%, #2C5F8A 60%, #3a6ea5 100%);
    color:#fff; padding:64px 24px 40px; text-align:center; position:relative; overflow:hidden;
  }
  .hero::after {
    content:""; position:absolute; right:-80px; top:-80px; width:280px; height:280px;
    border-radius:50%; background:rgba(232,108,0,.18);
  }
  .hero h1 { font-size:40px; margin:0 0 12px; letter-spacing:2px; }
  .hero .tagline { font-size:18px; opacity:.92; margin-bottom:8px; }
  .hero .meta { font-size:13px; opacity:.7; }
  .hero .badges { margin-top:18px; }
  .hero .badge {
    display:inline-block; background:rgba(255,255,255,.15); border:1px solid rgba(255,255,255,.3);
    padding:4px 14px; border-radius:20px; font-size:12px; margin:4px 6px;
  }
  /* Nav tabs */
  .nav {
    background:#fff; box-shadow:0 2px 8px rgba(0,0,0,.06); position:sticky; top:0; z-index:50;
    display:flex; justify-content:center; gap:4px; padding:10px 12px; flex-wrap:wrap;
  }
  .nav button {
    background:none; border:none; cursor:pointer; font-size:15px; color:#555;
    padding:10px 22px; border-radius:8px; font-family:inherit; transition:all .2s;
    border-bottom:3px solid transparent;
  }
  .nav button:hover { background:#f0f3f7; color:#1B3A5C; }
  .nav button.active { color:#1B3A5C; border-bottom-color:#E86C00; font-weight:bold; }
  /* Content */
  .wrap { max-width:1080px; margin:0 auto; padding:40px 24px 80px; }
  .block { display:none; animation:fade .35s ease; }
  .block.active { display:block; }
  @keyframes fade { from{opacity:0; transform:translateY(10px);} to{opacity:1; transform:none;} }
  h2.sec { font-size:26px; color:#1B3A5C; margin:0 0 8px; padding-bottom:10px; border-bottom:3px solid #E86C00; display:inline-block; }
  h2.sec + p.lead { color:#555; font-size:15px; line-height:1.8; margin:14px 0 24px; max-width:900px; }
  h3.sub { color:#2C5F8A; font-size:18px; margin:28px 0 12px; }
  p, li { line-height:1.85; font-size:14.5px; }
  /* 卡片网格 */
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:18px; margin:18px 0; }
  .card {
    background:#fff; border-radius:12px; padding:20px 22px; box-shadow:0 2px 10px rgba(0,0,0,.06);
    border-top:4px solid #2C5F8A; transition:transform .2s, box-shadow .2s;
  }
  .card:hover { transform:translateY(-4px); box-shadow:0 8px 24px rgba(27,58,92,.15); }
  .card .ico { font-size:28px; margin-bottom:8px; }
  .card h4 { margin:0 0 8px; color:#1B3A5C; font-size:16px; }
  .card p { margin:0; color:#555; font-size:13.5px; line-height:1.7; }
  .card.o { border-top-color:#E86C00; }
  .card.g { border-top-color:#27AE60; }
  .card.p { border-top-color:#8E44AD; }
  /* 标签芯片 */
  .chips { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0; }
  .chip {
    background:#eef2f7; color:#2C5F8A; padding:5px 14px; border-radius:16px; font-size:12.5px;
    border:1px solid #d8e0ea;
  }
  /* 架构图 */
  .arch { margin:20px 0; }
  .layer {
    display:flex; align-items:stretch; margin:10px 0; border-radius:10px; overflow:hidden;
    box-shadow:0 2px 8px rgba(0,0,0,.08);
  }
  .layer .lname {
    width:90px; flex-shrink:0; color:#fff; display:flex; align-items:center; justify-content:center;
    font-weight:bold; font-size:15px; letter-spacing:2px; padding:0 6px;
  }
  .layer .lbody { flex:1; background:#fff; padding:14px 18px; display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
  .layer .mod {
    background:#f0f3f7; border:1px solid #d8e0ea; border-radius:8px; padding:8px 14px;
    font-size:13px; color:#333;
  }
  .layer.app .lname { background:#1B3A5C; }
  .layer.ai  .lname { background:#E86C00; }
  .layer.svc .lname { background:#2C5F8A; }
  .layer.data .lname { background:#27AE60; }
  .arrow { text-align:center; color:#aaa; font-size:20px; margin:2px 0; }
  /* 技术路线图 */
  .roadmap { margin:18px 0; }
  .rm-stage {
    background:#fff; border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,.07); margin:14px 0; overflow:hidden;
    border-left:6px solid #2C5F8A;
  }
  .rm-stage.s1 { border-left-color:#1B3A5C; }
  .rm-stage.s2 { border-left-color:#2C5F8A; }
  .rm-stage.s3 { border-left-color:#E86C00; }
  .rm-stage.s4 { border-left-color:#27AE60; }
  .rm-stage.s5 { border-left-color:#8E44AD; }
  .rm-stage .rm-head {
    display:flex; align-items:center; padding:12px 18px; background:#f8fafc; border-bottom:1px solid #eef2f7;
  }
  .rm-stage .rm-num {
    width:30px; height:30px; border-radius:50%; background:#1B3A5C; color:#fff; font-weight:bold;
    display:flex; align-items:center; justify-content:center; font-size:14px; margin-right:12px; flex-shrink:0;
  }
  .rm-stage.s2 .rm-num { background:#2C5F8A; }
  .rm-stage.s3 .rm-num { background:#E86C00; }
  .rm-stage.s4 .rm-num { background:#27AE60; }
  .rm-stage.s5 .rm-num { background:#8E44AD; }
  .rm-stage .rm-title { font-size:16px; font-weight:bold; color:#1B3A5C; }
  .rm-stage .rm-status {
    margin-left:auto; font-size:11px; padding:3px 10px; border-radius:12px; font-weight:normal;
  }
  .rm-status.done { background:#e6f4ea; color:#1e8449; }
  .rm-status.doing { background:#fff3e0; color:#b35a00; }
  .rm-status.todo { background:#eef2f7; color:#666; }
  .rm-stage .rm-body { padding:14px 18px; }
  .rm-blocks { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; }
  .rm-block {
    background:#f0f3f7; border:1px solid #d8e0ea; border-radius:8px; padding:10px 14px; font-size:13px; line-height:1.6;
  }
  .rm-block b { color:#1B3A5C; display:block; margin-bottom:2px; }
  .rm-block .tag { font-size:10px; color:#999; }
  .rm-flow { text-align:center; color:#bbb; font-size:22px; margin:6px 0; letter-spacing:4px; }
  /* 表格 */
  table { width:100%; border-collapse:collapse; margin:16px 0; font-size:13.5px; background:#fff; box-shadow:0 2px 8px rgba(0,0,0,.06); border-radius:8px; overflow:hidden; }
  th { background:#1B3A5C; color:#fff; padding:12px 14px; text-align:left; font-weight:normal; }
  td { padding:11px 14px; border-bottom:1px solid #eef2f7; vertical-align:top; line-height:1.7; }
  tr:last-child td { border-bottom:none; }
  tr:hover td { background:#f8fafc; }
  td b { color:#1B3A5C; }
  /* 收益 */
  .benefits { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; margin:16px 0; }
  .ben { background:linear-gradient(135deg,#fff,#f8fafc); border-left:4px solid #27AE60; padding:16px 18px; border-radius:8px; box-shadow:0 2px 6px rgba(0,0,0,.05); }
  .ben .num { font-size:28px; font-weight:bold; color:#27AE60; }
  .ben .desc { font-size:13px; color:#555; margin-top:4px; }
  /* 代码 */
  .code {
    background:#1B3A5C; color:#cfe2ff; padding:16px 20px; border-radius:10px; font-family:Consolas,monospace;
    font-size:13px; line-height:1.8; margin:12px 0; overflow-x:auto; white-space:pre;
  }
  .code .cmt { color:#7a9cc6; }
  .code .cmd { color:#E86C00; }
  .access { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; margin:14px 0; }
  .access a {
    display:block; background:#fff; border:1px solid #d8e0ea; border-radius:10px; padding:14px 18px;
    transition:all .2s; box-shadow:0 2px 6px rgba(0,0,0,.04);
  }
  .access a:hover { border-color:#E86C00; transform:translateY(-2px); box-shadow:0 6px 16px rgba(232,108,0,.15); }
  .access a .url { font-family:Consolas,monospace; color:#2C5F8A; font-size:13px; }
  .access a .desc { color:#888; font-size:12px; margin-top:4px; }
  .note { background:#fff7e8; border-left:4px solid #E86C00; padding:12px 16px; border-radius:6px; font-size:13px; color:#7a5a20; margin:16px 0; }
  /* footer */
  footer { background:#1B3A5C; color:#aabbcc; text-align:center; padding:24px; font-size:12px; }
  footer a { color:#cfe2ff; }
</style>
</head>
<body>

<div class="hero">
  <h1>汽车创新技术库</h1>
  <div class="tagline">以「技术点」为核心的关联网络 · 从资料与经验中提炼，双向贯通</div>
  <div class="meta">从海量资料与人工经验中提炼出一个个技术点，在技术点之间建立关联，形成一张既可自下而上由资料支撑、也可自上而下精细检索的技术网络</div>
  <div class="badges">
    <span class="badge">技术点关联网络</span>
    <span class="badge">AI 自动提炼</span>
    <span class="badge">双向贯通</span>
    <span class="badge">GraphRAG 问答</span>
    <span class="badge">MCP / Skill 接入</span>
    <span class="badge">内网离线可用</span>
  </div>
</div>

<div class="nav" id="nav">
  <button class="active" data-tab="intro">简介</button>
  <button data-tab="adv">核心优势</button>
  <button data-tab="arch">系统架构</button>
  <button data-tab="roadmap">技术路线</button>
  <button data-tab="feat">预期功能与收益</button>
  <button data-tab="usage">使用方式</button>
</div>

<div class="wrap">

  <!-- 简介 -->
  <div class="block active" id="tab-intro">
    <h2 class="sec">简介</h2>
    <p class="lead">
      汽车创新技术库的本质，是<u>一张以「技术点」为节点、以技术点之间的关联为边的网络</u>。
      海量的技术文档、标准法规、专利文书、零部件手册、供应商资料以及工程师的经验判断，都是这张网络的「原料」——
      平台用 AI 从这些原料中提炼出一个个具体的技术点，并自动建立技术点与标准、专利、零部件、其他技术点之间的关联，
      最终沉淀为一张可交互、可推理、可问答的技术点关联图谱。工程师面对的不再是几十个散落的文件，
      而是一张看得见全貌、摸得清脉络的技术网络。
    </p>

    <h3 class="sub">它解决什么问题</h3>
    <div class="grid">
      <div class="card o">
        <div class="ico">🕳️</div>
        <h4>技术点埋在资料里</h4>
        <p>真正有用的「技术点」散落在文档、标准、专利的行文之中，不读完读透就提炼不出来，资料多但技术点难浮现。</p>
      </div>
      <div class="card o">
        <div class="ico">🔗</div>
        <h4>技术点之间缺乏关联</h4>
        <p>技术点本应与对应标准、相关专利、依赖零部件、前后继技术大量关联，但资料形态下这些联系无法体现，全靠人脑拼接。</p>
      </div>
      <div class="card o">
        <div class="ico">👤</div>
        <h4>经验随人流失</h4>
        <p>核心的技术判断和调研结论存在个人笔记里，人员调动后新人又要从零提炼，组织层面的技术积累无法沉淀。</p>
      </div>
      <div class="card o">
        <div class="ico">🐢</div>
        <h4>双向调研都费时</h4>
        <p>从资料往技术点「自下而上」支撑、或从技术点往资料「自上而下」精检，都需大量重复检索，缺乏一个贯通的入口。</p>
      </div>
    </div>

    <h3 class="sub">核心思想：技术点网络，双向贯通</h3>
    <div class="grid">
      <div class="card g">
        <div class="ico">⬆️</div>
        <h4>自下而上 · 资料支撑技术</h4>
        <p>从已有资料中提炼出技术点，并把支撑该技术点的标准、专利、零部件、文献挂接上去——每个技术点都「站得住脚」，有据可查。</p>
      </div>
      <div class="card g">
        <div class="ico">⬇️</div>
        <h4>自上而下 · 技术精检资料</h4>
        <p>给定一个技术点，沿关联网络向下精细检索所需的标准、专利、供应商、参考案例——从一个点出发，快速锁定全链路材料。</p>
      </div>
    </div>

    <h3 class="sub">适用的技术领域（举例）</h3>
    <div class="chips">
      <span class="chip">线控制动 EMB / EHB</span>
      <span class="chip">线控转向</span>
      <span class="chip">底盘域控制器</span>
      <span class="chip">车辆动力学控制</span>
      <span class="chip">激光雷达感知</span>
      <span class="chip">毫米波雷达</span>
      <span class="chip">多传感器融合</span>
      <span class="chip">舱驾融合</span>
      <span class="chip">智能座舱 HUD</span>
      <span class="chip">800V 高压平台</span>
      <span class="chip">扁线电机</span>
      <span class="chip">一体化压铸</span>
      <span class="chip">主动悬架</span>
      <span class="chip">轮毂电机</span>
    </div>
    <p style="color:#888;font-size:13px;">平台主题不限定于某一领域，任何汽车创新技术方向均可作为知识库的覆盖范围。</p>
  </div>

  <!-- 核心优势 -->
  <div class="block" id="tab-adv">
    <h2 class="sec">核心优势</h2>
    <p class="lead">围绕「技术点」的提炼、关联与贯通，八个关键能力让技术积累从「文件堆」变成「可推理的技术网络」。</p>

    <div class="grid">
      <div class="card">
        <div class="ico">🕸️</div>
        <h4>技术点网络化</h4>
        <p>以技术点为节点、技术点间关联为边，力导向网络图一眼看清技术全貌与脉络，而非一堆孤立文件——这是本平台的本质形态。</p>
      </div>
      <div class="card o">
        <div class="ico">🤖</div>
        <h4>AI 自动提炼技术点</h4>
        <p>上传技术文档，大模型自动从中抽取技术点、对应标准、引用专利、关键零部件及彼此关系，输出结构化 JSON，无需人工逐条编目。</p>
      </div>
      <div class="card g">
        <div class="ico">🔎</div>
        <h4>多源聚合</h4>
        <p>标准库、专利库、供应商库、公开情报以「适配器」方式接入，可按需扩展检索源，围绕一个技术点一站式汇聚多维度材料。</p>
      </div>
      <div class="card p">
        <div class="ico">🔀</div>
        <h4>引擎可切换</h4>
        <p>本地用 SQLite 即开即用，零依赖；企业部署切到 NebulaGraph 图数据库，接口完全一致，仅改一个环境变量。</p>
      </div>
      <div class="card">
        <div class="ico">🔄</div>
        <h4>双向贯通</h4>
        <p>既支持「搜材料 → 提炼技术点 → 建立联系」自下而上支撑，也支持「提供技术点 → 搜材料 → 建立联系」自上而下精检，两个方向共用同一套管道。</p>
      </div>
      <div class="card o">
        <div class="ico">🧩</div>
        <h4>MCP / Skill 接入</h4>
        <p>知识库能力封装为 MCP 工具，任何 MCP 客户端或上层 Skill 均可调用，对齐公司 AI 平台「KG → API → MCP → Skill」四层架构。</p>
      </div>
      <div class="card g">
        <div class="ico">✈️</div>
        <h4>内网离线可用</h4>
        <p>前端无任何 CDN 依赖，大模型可切换为本地部署（如 Ollama），全程在企业内网闭环运行，数据不出网，适配保密环境。</p>
      </div>
      <div class="card p">
        <div class="ico">✍️</div>
        <h4>人工沉淀</h4>
        <p>每个技术点节点支持人工备注与相关链接，团队经验可直接挂到技术点上，逐步沉淀为组织资产，避免随人流失。</p>
      </div>
    </div>
  </div>

  <!-- 系统架构 -->
  <div class="block" id="tab-arch">
    <h2 class="sec">系统架构</h2>
    <p class="lead">自下而上四层结构，每一层可独立替换或扩展。数据层双引擎、AI 层可插拔、应用层多入口。技术点及其关联贯穿全栈。</p>

    <div class="arch">
      <div class="layer app">
        <div class="lname">应用层</div>
        <div class="lbody">
          <span class="mod">技术点图谱可视化</span>
          <span class="mod">文档上传与审核</span>
          <span class="mod">智能问答界面</span>
          <span class="mod">情报推送</span>
          <span class="mod">数据导入导出</span>
        </div>
      </div>
      <div class="arrow">▲</div>
      <div class="layer ai">
        <div class="lname">AI 层</div>
        <div class="lbody">
          <span class="mod">MCP Server（6 工具）</span>
          <span class="mod">技术点抽取 Extractor</span>
          <span class="mod">情报收集 Intelligence</span>
          <span class="mod">GraphRAG 问答</span>
          <span class="mod">实体去重 / 关系校验</span>
        </div>
      </div>
      <div class="arrow">▲</div>
      <div class="layer svc">
        <div class="lname">服务层</div>
        <div class="lbody">
          <span class="mod">FastAPI</span>
          <span class="mod">技术点 CRUD</span>
          <span class="mod">图/路径/全文搜索</span>
          <span class="mod">分类树</span>
          <span class="mod">图谱数据接口</span>
          <span class="mod">备注保存</span>
        </div>
      </div>
      <div class="arrow">▲</div>
      <div class="layer data">
        <div class="lname">数据层</div>
        <div class="lbody">
          <span class="mod">图引擎抽象层 get_store()</span>
          <span class="mod">SQLite（本地）</span>
          <span class="mod">NebulaGraph（企业）</span>
          <span class="mod">node_notes 备注</span>
          <span class="mod">pending 草稿（规划）</span>
        </div>
      </div>
    </div>

    <h3 class="sub">两条核心数据流 · 技术点网络的双向贯通</h3>
    <div class="grid">
      <div class="card o">
        <h4>流程 A：搜材料 → 提炼技术点 → 建立联系（自下而上）</h4>
        <p>手里有文档 → AI 抽取出技术点及其关联的标准/专利/零部件 → 人工审核 → 入图谱，技术点之间的关联自动建立，资料由此向上支撑技术点。</p>
      </div>
      <div class="card g">
        <h4>流程 B：提技术点 → 搜材料 → 建立联系（自上而下）</h4>
        <p>给定一个技术点 → 系统并行检索专利/标准/供应商/情报 → 抽取实体 → 强制挂到该技术点下 → 审核入库，从一个技术点向下精细锁定全链路材料。</p>
      </div>
    </div>
    <div class="note">两条流程共用同一套「抽取 + 审核 + 入库」管道，只是入口不同：A 是用户喂文档自下而上提炼，B 是系统去各源头搜自上而下精检。底层统一，只换入口。</div>
  </div>

  <!-- 技术路线 -->
  <div class="block" id="tab-roadmap">
    <h2 class="sec">技术路线</h2>
    <p class="lead">整条技术路线分五个阶段、若干 block，自下而上贯通「数据 → 提炼 → 存储 → 服务 → 应用」。每个 block 都已框定边界与职责，后续按 block 逐步落地，避免思路散乱。</p>

    <div class="roadmap">

      <!-- 阶段1：数据接入 -->
      <div class="rm-stage s1">
        <div class="rm-head">
          <div class="rm-num">1</div>
          <div class="rm-title">数据接入层 · 多源原料汇入</div>
          <span class="rm-status doing">部分完成</span>
        </div>
        <div class="rm-body">
          <div class="rm-blocks">
            <div class="rm-block"><b>文档上传</b>PDF / Word / TXT / URL 拖拽上传<span class="tag"> · 规划</span></div>
            <div class="rm-block"><b>文本抽取</b>pdfplumber / python-docx 离线解析为纯文本<span class="tag"> · 规划</span></div>
            <div class="rm-block"><b>批量导入</b>JSON / CSV / Excel 一次性灌入<span class="tag"> · 骨架在</span></div>
            <div class="rm-block"><b>外部 API 接入</b>标准库 / 专利库 / 供应商库适配器<span class="tag"> · 骨架在</span></div>
            <div class="rm-block"><b>人工经验录入</b>工程师直接录入技术点与备注<span class="tag"> · 已完成</span></div>
          </div>
        </div>
      </div>
      <div class="rm-flow">▲</div>

      <!-- 阶段2：AI 提炼 -->
      <div class="rm-stage s2">
        <div class="rm-head">
          <div class="rm-num">2</div>
          <div class="rm-title">AI 提炼层 · 从原料中提炼技术点与关联</div>
          <span class="rm-status doing">骨架完成</span>
        </div>
        <div class="rm-body">
          <div class="rm-blocks">
            <div class="rm-block"><b>技术点抽取</b>LLM 从文本输出结构化技术点 JSON<span class="tag"> · 骨架在</span></div>
            <div class="rm-block"><b>关联识别</b>自动识别 技术点→标准/专利/零部件 关系<span class="tag"> · 骨架在</span></div>
            <div class="rm-block"><b>实体去重</b>同义技术点合并（如"轮毂电机"=""轮端驱动电机""）<span class="tag"> · 规划</span></div>
            <div class="rm-block"><b>关系校验</b>LLM 二次确认边是否成立，防幻觉<span class="tag"> · 规划</span></div>
            <div class="rm-block"><b>草稿审核</b>抽取结果先进 pending 表，人工勾选后入库<span class="tag"> · 规划</span></div>
          </div>
        </div>
      </div>
      <div class="rm-flow">▲</div>

      <!-- 阶段3：知识存储 -->
      <div class="rm-stage s3">
        <div class="rm-head">
          <div class="rm-num">3</div>
          <div class="rm-title">知识存储层 · 技术点关联网络沉淀</div>
          <span class="rm-status done">已完成</span>
        </div>
        <div class="rm-body">
          <div class="rm-blocks">
            <div class="rm-block"><b>图引擎抽象层</b>get_store() 工厂，统一接口<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>SQLite 引擎</b>本地零依赖即开即用<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>NebulaGraph 引擎</b>企业级图数据库部署<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>节点备注表</b>node_notes 持久化人工备注与链接<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>草稿表</b>pending_nodes 待审核暂存<span class="tag"> · 规划</span></div>
            <div class="rm-block"><b>软删除/版本</b>deleted_at 可回溯，不物理删<span class="tag"> · 规划</span></div>
          </div>
        </div>
      </div>
      <div class="rm-flow">▲</div>

      <!-- 阶段4：服务与接口 -->
      <div class="rm-stage s4">
        <div class="rm-head">
          <div class="rm-num">4</div>
          <div class="rm-title">服务与接口层 · 对外暴露能力</div>
          <span class="rm-status done">核心完成</span>
        </div>
        <div class="rm-body">
          <div class="rm-blocks">
            <div class="rm-block"><b>FastAPI 服务</b>知识 CRUD / 搜索 / 分类 / 图谱接口<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>图/路径/全文搜索</b>多维度检索技术点<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>图谱数据接口</b>/graph/data + /graph/node 供前端<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>MCP Server</b>6 工具供 AI 助手调用<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>GraphRAG 问答</b>子图检索 + LLM 总结自然语言回答<span class="tag"> · 规划</span></div>
            <div class="rm-block"><b>导出接口</b>JSON / CSV / GraphML 导出<span class="tag"> · 规划</span></div>
          </div>
        </div>
      </div>
      <div class="rm-flow">▲</div>

      <!-- 阶段5：应用与交互 -->
      <div class="rm-stage s5">
        <div class="rm-head">
          <div class="rm-num">5</div>
          <div class="rm-title">应用与交互层 · 人与 AI 共用</div>
          <span class="rm-status doing">部分完成</span>
        </div>
        <div class="rm-body">
          <div class="rm-blocks">
            <div class="rm-block"><b>技术点图谱可视化</b>力导向网络，点击高亮，详情联动<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>布局模式切换</b>牵引拉伸 / 静态拉伸<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>备注与链接</b>节点详情页人工沉淀<span class="tag"> · 已完成</span></div>
            <div class="rm-block"><b>文档上传审核页</b>上传→AI抽取→勾选→入库<span class="tag"> · 规划</span></div>
            <div class="rm-block"><b>智能问答界面</b>自然语言提问，图谱回答<span class="tag"> · 规划</span></div>
            <div class="rm-block"><b>情报监控推送</b>订阅技术点，定时推送新专利/标准<span class="tag"> · 规划</span></div>
            <div class="rm-block"><b>Skill 上层接入</b>对接公司 AI 平台 Skill<span class="tag"> · 规划</span></div>
          </div>
        </div>
      </div>

    </div>

    <h3 class="sub">两条贯穿全栈的流程线</h3>
    <div class="grid">
      <div class="card o">
        <h4>流程 A · 自下而上（搜材料→提炼技术点→建联系）</h4>
        <p>阶段1 文档上传 → 阶段2 AI 抽取技术点 → 阶段3 入库 → 阶段5 图谱呈现。资料向上支撑技术点。</p>
      </div>
      <div class="card g">
        <h4>流程 B · 自上而下（提技术点→搜材料→建联系）</h4>
        <p>阶段5 输入技术点 → 阶段4 检索接口 → 阶段1 多源抓取 → 阶段2 抽取挂接 → 阶段3 入库。从技术点向下精检材料。</p>
      </div>
    </div>
    <div class="note">五个阶段、约 30 个 block，每个 block 边界清晰、可独立推进。绿色=已完成，橙色=部分/骨架，灰色=规划中。后续按 block 逐个落地，思路不散。</div>
  </div>

  <!-- 预期功能与收益 -->
  <div class="block" id="tab-feat">
    <h2 class="sec">预期功能与收益</h2>
    <p class="lead">围绕「技术点」的提炼、关联、检索与沉淀，从能用到好用，以及带来的实际收益。</p>

    <h3 class="sub">预期功能</h3>
    <table>
      <tr><th style="width:170px;">功能</th><th>说明</th></tr>
      <tr><td><b>技术点关联图谱</b></td><td>以技术点为核心节点，关联标准/专利/资源/零部件/分类，力导向网络可视化，点击高亮，详情联动，看清技术点全貌与脉络。</td></tr>
      <tr><td><b>AI 文档提炼技术点</b></td><td>上传 PDF / Word / TXT / URL → 文本抽取 → LLM 输出结构化技术点及关联 → 草稿审核 → 入图谱。</td></tr>
      <tr><td><b>智能检索发现</b></td><td>输入技术点（如「线控制动 EMB」）→ 多源并行检索专利 / 标准 / 供应商 → 自动建立关联并挂到该技术点下，自上而下精检。</td></tr>
      <tr><td><b>图谱问答（GraphRAG）</b></td><td>自然语言提问（如「EMB 对应哪些标准？TRL 几？」）→ 沿技术点关联检索子图 → LLM 总结 → 自然语言回答。</td></tr>
      <tr><td><b>情报监控推送</b></td><td>订阅感兴趣的技术点 → 定时扫描新公开专利 / 标准 → 有更新主动推送给订阅人。</td></tr>
      <tr><td><b>备注与链接</b></td><td>每个技术点节点可挂人工备注文本与相关链接，沉淀团队经验，支持多人协作完善。</td></tr>
      <tr><td><b>数据导入导出</b></td><td>支持 JSON / CSV / GraphML 导出与批量导入，便于知识库备份与跨环境迁移。</td></tr>
      <tr><td><b>MCP 工具调用</b></td><td>6 个 MCP 工具供 AI 助手调用：查技术 / 查子图 / 查标准 / 查资源池 / 查分类树 / 触发情报。</td></tr>
    </table>

    <h3 class="sub">预期收益</h3>
    <div class="benefits">
      <div class="ben"><div class="num">60%</div><div class="desc">调研时间节省：从翻文件到一图看清技术点全貌</div></div>
      <div class="ben"><div class="num">1 张网</div><div class="desc">技术点关联网络：点与点之间脉络一目了然</div></div>
      <div class="ben"><div class="num">双向</div><div class="desc">自下而上支撑 + 自上而下精检，贯通无断点</div></div>
      <div class="ben"><div class="num">0 依赖</div><div class="desc">内网离线运行：无 CDN，数据不出网</div></div>
      <div class="ben"><div class="num">N 项目</div><div class="desc">共享复用：多项目共用同一技术点库，减少重复提炼</div></div>
      <div class="ben"><div class="num">AI+</div><div class="desc">决策有据：技术选型 / 标准对标 / 专利布局可查可问</div></div>
    </div>
    <div class="note">技术沉淀从「个人笔记」转为「组织资产」，避免人员流动导致的技术经验流失。</div>
  </div>

  <!-- 使用方式 -->
  <div class="block" id="tab-usage">
    <h2 class="sec">使用方式</h2>
    <p class="lead">三条命令启动，浏览器即可访问。本地零依赖，企业部署切换图引擎。</p>

    <h3 class="sub">启动</h3>
    <div class="code"><span class="cmt"># 进入项目目录</span>
cd ai-knowledge-base

<span class="cmt"># 安装依赖（首次）</span>
<span class="cmd">.\venv\Scripts\pip</span> install -r requirements.txt

<span class="cmt"># 启动后端服务</span>
<span class="cmd">.\venv\Scripts\python</span> -m uvicorn backend.main:app --host 0.0.0.0 --port 8000</div>

    <h3 class="sub">访问入口</h3>
    <div class="access">
      <a href="/about"><div class="url">/  或  /about</div><div class="desc">本介绍页（功能介绍、架构、使用方式）</div></a>
      <a href="/graph"><div class="url">/graph</div><div class="desc">⭐ 图谱可视化主工作台（浏览/编辑/添加节点/AI 提取）</div></a>
      <a href="/docs"><div class="url">/docs</div><div class="desc">API 文档（Swagger 风格，可交互点击调用）</div></a>
      <a href="/redoc"><div class="url">/redoc</div><div class="desc">API 文档（ReDoc 风格，适合阅读）</div></a>
      <a href="/stats"><div class="url">/stats</div><div class="desc">知识库统计（各类型节点数量）</div></a>
      <a href="/health"><div class="url">/health</div><div class="desc">健康检查</div></a>
    </div>

    <h3 class="sub">切换到企业图引擎（NebulaGraph）</h3>
    <div class="code"><span class="cmt"># .env 配置</span>
KNOWLEDGE_ENGINE=nebula
NEBULA_HOST=127.0.0.1
NEBULA_PORT=9669

<span class="cmt"># 启动 NebulaGraph 集群 + 初始化</span>
<span class="cmd">docker-compose</span> -f docker-compose.nebula.yml up -d
<span class="cmd">python</span> nebula_init.py</div>

    <h3 class="sub">激活 AI 能力</h3>
    <div class="code"><span class="cmt"># .env 填写大模型配置（OpenAI 兼容接口均可）</span>
LLM_API_KEY=your-key
LLM_API_URL=https://your-llm-endpoint/v1
LLM_MODEL=model-name

<span class="cmt"># 华为内部推理服务示例</span>
<span class="cmt"># LLM_API_URL=https://ai-models.rnd.yinwang.com/ai-platform-models-agent/v1</span>
<span class="cmt"># LLM_MODEL=DeepSeek-V4-Flash</span>

<span class="cmt"># 本地离线模型示例</span>
<span class="cmt"># LLM_API_URL=http://localhost:11434/v1</span>
<span class="cmt"># LLM_MODEL=qwen2.5:14b</span></div>

    <h3 class="sub">日常使用</h3>
    <ul style="line-height:2;">
      <li><b>浏览图谱</b>：打开 /graph，拖拽节点、滚轮缩放、点击节点查看详情</li>
      <li><b>AI 提取</b>：/graph 页面点「🤖 AI 提取」按钮，粘贴技术资讯→LLM 自动提取领域/技术点/支撑材料并入库→图谱自动刷新</li>
      <li><b>手动添加</b>：/graph 页面点「＋ 添加节点」按钮，填写名称/层级/材料类型/备注/父节点</li>
      <li><b>编辑节点</b>：点击节点→详情面板→编辑名称/层级/材料类型/备注/链接→保存</li>
      <li><b>连线管理</b>：详情面板底部"关联关系"区，添加/删除/编辑连线备注</li>
      <li><b>双击折叠</b>：双击技术点(L3)展开/收起支撑材料(右上角橙色数字=材料数)</li>
      <li><b>搜索高亮</b>：侧栏搜索框输入关键词，匹配节点高亮显示</li>
      <li><b>层级筛选</b>：侧栏下拉选择层级，仅高亮该层节点</li>
      <li><b>调用 API</b>：/docs 页面直接试用全部增删改查接口（已加中文说明）</li>
      <li><b>AI 助手</b>：通过 MCP Server 接入，AI 可查询技术/子图/添加节点/提取知识</li>
    </ul>
    <div class="note">提示：图谱页若显示异常，按 Ctrl + F5 强制刷新清除浏览器缓存。</div>
  </div>

</div>

<footer>
  汽车创新技术库 · AI 知识图谱平台 &nbsp;|&nbsp; 基于 FastAPI + 知识图谱 + MCP
  <br/>本地 SQLite / 企业 NebulaGraph 双引擎 · 内网离线可用 · 以技术点为核心的关联网络
</footer>

<script>
(function(){
  var nav = document.getElementById('nav');
  var buttons = nav.querySelectorAll('button');
  var blocks = document.querySelectorAll('.block');
  buttons.forEach(function(btn){
    btn.addEventListener('click', function(){
      var tab = btn.getAttribute('data-tab');
      buttons.forEach(function(b){ b.classList.remove('active'); });
      blocks.forEach(function(bl){ bl.classList.remove('active'); });
      btn.classList.add('active');
      var target = document.getElementById('tab-' + tab);
      if (target) target.classList.add('active');
      window.scrollTo({top:0, behavior:'smooth'});
    });
  });
})();
</script>
</body>
</html>
"""
