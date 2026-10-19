const API = "";
const TOKEN_KEY = "akn_write_token";
const CLIENT_KEY = "akn_client_id";
const USER_KEY = "akn_user_id";

function getStoredUserId() {
  try { return localStorage.getItem(USER_KEY) || ""; } catch (_) { return ""; }
}
let userId = getStoredUserId();

function getClientId() {
  try {
    let id = localStorage.getItem(CLIENT_KEY);
    if (!id) {
      id = "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
      localStorage.setItem(CLIENT_KEY, id);
    }
    return id;
  } catch (_) { return ""; }
}
const CLIENT_ID = getClientId();

let writeToken = "";
try { writeToken = sessionStorage.getItem(TOKEN_KEY) || ""; } catch (_) {}
function saveToken(t) { try { sessionStorage.setItem(TOKEN_KEY, t || ""); } catch (_) {} }
function ensureTokenSaved() { return writeToken; }
function logout() { writeToken = ""; saveToken(""); updateLoginButtons(); }
function updateLoginButtons() {
  const b = $?.("btnLogin");
  if (b) {
    b.textContent = writeToken ? "退出登录" : "登录";
    b.title = writeToken
      ? `已登录${userId ? "（" + userId + "）" : ""}，点击退出登录`
      : "登录后可编辑/写入图谱";
  }
}
function openLoginModal(message) {
  const m = $("loginMask");
  const msg = $("loginMsg");
  if (msg) { msg.textContent = message || ""; msg.hidden = !message; }
  if (m) {
    m.hidden = false;
    const u = $("loginUser"); if (u) { u.value = userId; }
    const p = $("loginPwd"); if (p) { p.value = ""; p.focus(); }
  }
}
async function doLogin() {
  const pwd = $("loginPwd").value.trim();
  const uid = ($("loginUser").value || "").trim().slice(0, 40);
  const msg = $("loginMsg");
  if (msg) { msg.hidden = false; msg.textContent = "验证中…"; msg.style.color = "#8ba3c7"; }
  try {
    const r = await api("/ai/login", { method: "POST", body: JSON.stringify({ password: pwd }) });
    writeToken = r.token; saveToken(r.token);
    userId = uid;
    try { localStorage.setItem(USER_KEY, uid); } catch (_) {}
    updateLoginButtons();
    if (msg) { msg.textContent = "登录成功，可编辑/写入"; msg.style.color = "#9fe6b0"; }
    setTimeout(() => { const m = $("loginMask"); if (m) m.hidden = true; }, 700);
  } catch (err) {
    if (msg) { msg.textContent = String(err.message || err); msg.style.color = "#f0a8a8"; }
  }
}

const TAG_LABEL = {
  vehicle: "车辆",
  domain: "领域",
  subdomain: "子域",
  module: "模块",
  technology: "技术点",
  material: "文档",
};

const TAG_COLOR = {
  vehicle: "#0ea5e9",
  domain: "#3b82f6",
  subdomain: "#14b8a6",
  module: "#a855f7",
  technology: "#f59e0b",
  material: "#a3a3a3",
};

/** Higher rank = outer / lower in hierarchy; larger visual size for smaller rank. */
const LAYER_RANK = {
  vehicle: 0,
  domain: 1,
  subdomain: 2,
  module: 3,
  technology: 4,
  material: 5,
};

const NODE_SIZE = {
  vehicle: 42,
  domain: 34,
  subdomain: 24,
  module: 20,
  technology: 15,
  material: 9,
};

// 安全校核：待审改动在视图中的高亮态
let reviewHighlightOn = false;
let reviewVids = new Set();
let reviewEdgeKeys = new Set();
const REVIEW_HL = "#22d3ee";

const REL_LABEL = {
  belongs_to: "归属",
  supports: "支撑",
  relates_to: "关联",
  other: "其他",
};

const EDGE_COLOR = {
  belongs_to: "#64748b",
  supports: "#78716c",
  relates_to: "#a78bfa",
};

let network = null;
let graph3d = null;
let viewMode = "2d"; // 2d | 3d
let layoutMode = "radial"; // radial | force | tree — 默认同心圆，层级 DAG 更易读；力导向可选；树状为初始树状+自由拖动
let treeCenterLayout = true; // 二维树状初始排布：true=子层垂直居中展开（默认）；false=顶部对齐"挂载式"
let tree3dMode = "layer"; // 三维树状布局：layer=分层（同标签同高度） | ring=环形（每标签一圈，按层叠放）
let layerCap = "technology"; // domain | subdomain | technology | material
let layerScope = "with_upper"; // only | with_upper
let domainFilter = ""; // "" = 全部领域(sub库)；否则为 domain 名称
let domainIndex = new Map(); // domain.name -> domain node
let focusVid = null;
let detailVid = null;
/** Selected relationship on canvas: { id, src_vid, dst_vid, edge_type, count } */
let detailEdge = null;
let overviewMode = false;
let hideMaterials = false; // derived when layerCap !== material
let nodesCache = [];
let lastExtract = null;
let lastGraphPayload = null; // { data, centerVid, view }
let detailNode = null;
let pathNodeIndex = {}; // name -> vid
let addPool = {}; // tag -> [{name,vid,tag}]（「添加节点」表单候选池）
let classificationIndex = { byId: null, children: null }; // 分类树（侧栏）
let treeExpanded = new Set(); // 分类树展开的节点 vid
let networkResizeObs = null;
let forceFitNext = true; // only fit after layout/filter change, never steal wheel/drag
let forceFit3dNext = true;
/** Nebula Explorer–inspired canvas controls */
const CANVAS_SOFT_LIMIT = 800; // warn above this (nodes+edges)
const CANVAS_HARD_LIMIT = 5000; // Explorer 2D recommendation
let isolateSelection = false;
let weightByDegree = true;
let lastCanvasTruncated = false;
/** 3D floating name labels */
let label3dEnabled = true;
/** Default: vehicle + first two hierarchy layers only */
const label3dTags = new Set(["vehicle", "domain", "subdomain"]);
let searchResultVids = new Set(); // 当前搜索命中的节点 id
let highlightSearch = false; // 「查找结果图谱中高亮」开关

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (writeToken && !headers.Authorization) headers.Authorization = `Bearer ${writeToken}`;
  if (CLIENT_ID && !headers["X-Client-Id"]) headers["X-Client-Id"] = CLIENT_ID;
  if (userId && !headers["X-User-Id"]) headers["X-User-Id"] = encodeURIComponent(userId);
  const timeout = options.timeout ?? 30000;
  let timer;
  let aborted = false;
  const ctrl = new AbortController();
  const onAbort = () => { aborted = true; };
  ctrl.signal.addEventListener("abort", onAbort);
  if (options.signal) {
    options.signal.addEventListener("abort", () => ctrl.abort());
  }
  timer = setTimeout(() => { ctrl.abort(); }, timeout);
  const res = await fetch(API + path, {
    headers,
    ...options,
    signal: ctrl.signal,
  }).finally(() => {
    clearTimeout(timer);
    ctrl.signal.removeEventListener("abort", onAbort);
  });
  void aborted;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/ai/login")) {
      ensureTokenSaved(null);
      openLoginModal("需要写入口令，请先登录后再执行该操作");
    }
    throw new Error(data.detail || data.error || res.statusText || "request failed");
  }
  return data;
}

function $(id) {
  return document.getElementById(id);
}

function isLightTheme() {
  return document.documentElement.getAttribute("data-theme") === "light";
}

function applyTheme(theme) {
  const t = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("akn_theme", t); } catch (_) {}
  const b = $("btnTheme");
  if (b) {
    b.textContent = t === "light" ? "深色" : "浅色";
    b.title = t === "light" ? "切换到深色" : "切换到浅色";
  }
  // 画布/三维背景与 JS 侧颜色随主题重绘
  try { redrawCurrentGraph(); } catch (_) {}
  try { if (graph3d) graph3d.backgroundColor(t === "light" ? "#f7f9fc" : "#0b0f14"); } catch (_) {}
}

function initTheme() {
  let saved = "dark";
  try {
    const s = localStorage.getItem("akn_theme");
    if (s === "light" || s === "dark") saved = s;
  } catch (_) {}
  const cur = document.documentElement.getAttribute("data-theme") || saved;
  document.documentElement.setAttribute("data-theme", cur);
  const b = $("btnTheme");
  if (b) {
    b.textContent = cur === "light" ? "深色" : "浅色";
    b.title = cur === "light" ? "切换到深色" : "切换到浅色";
  }
}

function escHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function escAttr(s) {
  return escHtml(s);
}

function nodeDisplayName(n) {
  const props = n?.props || {};
  const name = (props.name || "").trim();
  const title = (props.title || "").trim();
  if (n?.tag === "material") {
    // Prefer meaningful short name; fall back to shortened title
    if (name && !looksLikeOpaqueId(name)) return name;
    if (title) return shortenTitle(title, 28);
    return name || n.vid;
  }
  return name || title || n?.vid || "";
}

function looksLikeOpaqueId(s) {
  // patent numbers / bare codes without CJK
  if (/[\u4e00-\u9fff]/.test(s)) return false;
  if (/^(US|EP|CN|WO)\d{5,}[A-Z]\d?$/i.test(s)) return true;
  if (/^[A-Z]{2,}[-_]?\d{3,}/.test(s) && s.length <= 28) return true;
  return false;
}

function shortenTitle(title, maxLen) {
  const t = String(title).replace(/\s+/g, " ").trim();
  if (t.length <= maxLen) return t;
  return `${t.slice(0, maxLen - 1)}…`;
}

/** Fixed hop count for 聚焦子图 / 展开邻居 (UI depth picker removed — overview ignores it). */
const SUBGRAPH_DEPTH = 2;

function stripMaterials(data) {
  const drop = new Set(
    (data.nodes || []).filter((n) => n.tag === "material").map((n) => n.vid)
  );
  if (!drop.size) return data;
  return {
    ...data,
    nodes: (data.nodes || []).filter((n) => !drop.has(n.vid)),
    edges: (data.edges || []).filter(
      (e) => !drop.has(e.src_vid) && !drop.has(e.dst_vid)
    ),
  };
}

/** Keep nodes within `maxDepth` undirected hops from all domain roots. */
function pruneByHopFromDomains(data, maxDepth) {
  const nodes = data.nodes || [];
  const edges = data.edges || [];
  if (!nodes.length) return data;
  const adj = new Map();
  for (const e of edges) {
    if (!adj.has(e.src_vid)) adj.set(e.src_vid, []);
    if (!adj.has(e.dst_vid)) adj.set(e.dst_vid, []);
    adj.get(e.src_vid).push(e.dst_vid);
    adj.get(e.dst_vid).push(e.src_vid);
  }
  let roots = nodes.filter((n) => n.tag === "domain").map((n) => n.vid);
  if (!roots.length) {
    // fallback: highest-level available
    roots = nodes.filter((n) => n.tag === "subdomain").map((n) => n.vid);
  }
  if (!roots.length) return data;

  const dist = new Map();
  const q = [];
  for (const r of roots) {
    dist.set(r, 0);
    q.push(r);
  }
  while (q.length) {
    const u = q.shift();
    const d = dist.get(u);
    if (d >= maxDepth) continue;
    for (const v of adj.get(u) || []) {
      if (!dist.has(v)) {
        dist.set(v, d + 1);
        q.push(v);
      }
    }
  }
  const keep = new Set(dist.keys());
  return {
    ...data,
    nodes: nodes.filter((n) => keep.has(n.vid)),
    edges: edges.filter((e) => keep.has(e.src_vid) && keep.has(e.dst_vid)),
  };
}

function readViewControls() {
  const capEl = $("layerCap");
  const scopeEl = $("layerScope");
  const domEl = $("domainFilter");
  if (capEl) layerCap = capEl.value || "technology";
  if (scopeEl) layerScope = scopeEl.value || "with_upper";
  if (domEl) domainFilter = domEl.value || "";
  hideMaterials = layerCap !== "material";
}

function refreshDomainFilterOptions(nodes) {
  const domEl = $("domainFilter");
  if (!domEl) return;
  const cur = domainFilter;
  const domains = (nodes || [])
    .filter((n) => n.tag === "domain")
    .sort((a, b) => (a?.props?.name || "").localeCompare(b?.props?.name || "", "zh"));
  domainIndex = new Map(domains.map((n) => [n?.props?.name || "", n]));
  domEl.innerHTML = '<option value="">全部领域</option>' +
    domains
      .map((d) => `<option value="${escAttr(d?.props?.name || "")}">${escHtml(d?.props?.name || "")}</option>`)
      .join("");
  if (cur && domainIndex.has(cur)) domEl.value = cur;
}

function syncViewControls() {
  const capEl = $("layerCap");
  const scopeEl = $("layerScope");
  const domEl = $("domainFilter");
  if (capEl) capEl.value = layerCap;
  if (scopeEl) scopeEl.value = layerScope;
  if (domEl) domEl.value = domainFilter;
  const bf = $("btnLayoutForce");
  const br = $("btnLayoutRadial");
  const bt = $("btnLayoutTree");
  if (bt) bt.classList.toggle("active", layoutMode === "tree");
  if (bf) bf.classList.toggle("active", layoutMode === "force");
  if (br) br.classList.toggle("active", layoutMode === "radial");
  const treeReset = $("btnTreeReset");
  if (treeReset) treeReset.hidden = !(layoutMode === "tree" && viewMode === "2d");
  const treeCenter = $("btnTreeCenter");
  if (treeCenter) {
    treeCenter.hidden = !(layoutMode === "tree" && viewMode === "2d");
    treeCenter.classList.toggle("active", treeCenterLayout);
    treeCenter.textContent = treeCenterLayout ? "居中" : "顶部";
  }
  const tree3dBtn = $("btnTree3dMode");
  if (tree3dBtn) {
    tree3dBtn.hidden = !(layoutMode === "tree" && viewMode === "3d");
    tree3dBtn.classList.toggle("active", tree3dMode === "ring");
    tree3dBtn.textContent = tree3dMode === "ring" ? "环形" : "分层";
  }
  const reheat = $("btnReheat");
  if (reheat) reheat.hidden = layoutMode !== "force";
  const labelBox = $("label3dControls");
  if (labelBox) labelBox.hidden = false; // 标注分级筛选对二维/三维均适用
  const btnLab = $("btnLabels3d");
  if (btnLab) btnLab.classList.toggle("active", label3dEnabled);
  document.querySelectorAll("[data-label3d-tag]").forEach((btn) => {
    const tag = btn.getAttribute("data-label3d-tag");
    btn.classList.toggle("active", label3dTags.has(tag));
    btn.disabled = !label3dEnabled;
  });
}

function layerFilterLabel() {
  const name = TAG_LABEL[layerCap] || layerCap;
  return layerScope === "only" ? `仅${name}` : `${name}+上层`;
}

function updateFocusMetaAfterDraw(center) {
  // 画布顶部标题栏已移除：聚焦上下文改由详情抽屉呈现
  const ft = $("focusTitle"); if (ft) ft.textContent = "";
  const fm = $("focusMeta"); if (fm) fm.textContent = "";
}

function updateGraphLegend() {
  const el = $("graphLegend");
  if (!el) return;
  el.innerHTML = ["vehicle", "domain", "subdomain", "module", "technology", "material"]
    .map(
      (t) =>
        `<span class="leg-item"><i style="background:${TAG_COLOR[t]}"></i>${TAG_LABEL[t]}</span>`
    )
    .join("");
}

async function loadStats() {
  const stats = await api("/stats");
  const order = ["vehicle", "domain", "subdomain", "module", "technology", "material"];
  $("statsBar").innerHTML = order
    .map(
      (k) => `<div class="stat"><div class="k">${TAG_LABEL[k] || k}</div><div class="v">${stats[k] ?? 0}</div></div>`
    )
    .join("");
}

function renderList(items) {
  readViewControls();
  const cap = LAYER_RANK[layerCap] ?? 3;
  const viewItems = items.filter((n) => {
    const r = LAYER_RANK[n.tag] ?? 99;
    return layerScope === "only" ? r === cap : r <= cap;
  });
  nodesCache = items;
  $("listCount").textContent = `${viewItems.length} 项`;
  const ul = $("nodeList");
  if (!viewItems.length) {
    ul.innerHTML = `<li><div class="name">无结果</div><div class="meta">试试换层级筛选</div></li>`;
    return;
  }
  ul.innerHTML = viewItems
    .map((n) => {
      const name = nodeDisplayName(n);
      const active = n.vid === focusVid || n.vid === detailVid ? "active" : "";
      return `<li class="${active}" data-vid="${n.vid}">
        <div class="name">${escapeHtml(name)}</div>
        <div class="meta">${TAG_LABEL[n.tag] || n.tag}</div>
      </li>`;
    })
    .join("");
}

async function searchNodes() {
  const keyword = $("keyword").value.trim();
  const tag = $("tagFilter").value;
  const qs = new URLSearchParams({ limit: "80" });
  if (keyword) qs.set("keyword", keyword);
  if (tag) qs.set("tag", tag);
  const data = await api(`/vertices?${qs}`);
  const items = data.items || [];
  renderList(items);
  if (keyword) {
    searchResultVids = new Set(items.map((n) => n.vid));
  } else {
    searchResultVids = new Set();
  }
  const hlBtn = $("btnHighlightSearch");
  if (hlBtn) hlBtn.classList.toggle("has-results", searchResultVids.size > 0);
  // 查找结果被清空/换词时，强制关闭高亮，避免整图一直处于变暗状态无法恢复
  if (!searchResultVids.size && highlightSearch) {
    highlightSearch = false;
    if (hlBtn) hlBtn.classList.remove("active");
    redrawCurrentGraph();
  }
}

function closeDrawer() {
  detailVid = null;
  detailEdge = null;
  const drawer = $("detailDrawer");
  drawer.hidden = true;
  document.querySelector(".canvas-body")?.classList.remove("with-drawer");
  [...$("nodeList").querySelectorAll("li")].forEach((li) => {
    li.classList.toggle("active", li.dataset.vid === focusVid);
  });
  syncDrawerActionLabels();
  applyGraphSelection();
  if (lastGraphPayload?.data) redrawCurrentGraph();
}

function edgeKey(e) {
  return `${e.src_vid}|${e.edge_type}|${e.dst_vid}`;
}

function lookupNodeBrief(vid) {
  const fromView = (lastGraphPayload?.view?.nodes || []).find((n) => n.vid === vid);
  if (fromView) return fromView;
  const fromData = (lastGraphPayload?.data?.nodes || []).find((n) => n.vid === vid);
  if (fromData) return fromData;
  return (nodesCache || []).find((n) => n.vid === vid) || null;
}

function syncDrawerActionLabels() {
  const focusBtn = $("btnFocusNode");
  const delBtn = $("btnDeleteNode");
  if (focusBtn) focusBtn.textContent = detailEdge ? "聚焦起点" : "聚焦子图";
  if (delBtn) delBtn.textContent = detailEdge ? "删除关系" : "删除";
}

function applyGraphSelection() {
  if (viewMode !== "2d" || !network) return;
  try {
    if (detailEdge) {
      const ends = [detailEdge.src_vid, detailEdge.dst_vid].filter(Boolean);
      network.selectNodes(ends);
      network.selectEdges([detailEdge.id]);
    } else if (detailVid) {
      network.selectNodes([detailVid]);
    } else {
      network.unselectAll();
    }
  } catch (_) {
    /* ignore */
  }
}

/** Build a clickable href for material source; local/UNC paths are marked specially. */
function sourceLinkMeta(raw) {
  const s = String(raw || "").trim();
  if (!s) return { kind: "empty", href: "", label: "跳转" };
  if (/^https?:\/\//i.test(s)) return { kind: "http", href: s, label: "打开链接" };
  if (/^www\./i.test(s)) return { kind: "http", href: `https://${s}`, label: "打开链接" };
  // Shared disk / local path: browsers block file:// from http pages → copy on click
  if (/^\\\\/.test(s) || /^[a-zA-Z]:[\\/]/.test(s) || s.startsWith("/")) {
    return { kind: "path", href: s, label: "复制路径" };
  }
  return { kind: "http", href: s, label: "打开链接" };
}

async function openSourceLink(el) {
  const kind = el?.dataset?.kind || "empty";
  const href = String(el?.dataset?.href || "").trim();
  if (!href) {
    setGraphHint("没有可跳转的来源链接", true);
    return;
  }
  if (kind === "http") {
    window.open(href, "_blank", "noopener,noreferrer");
    return;
  }
  try {
    await navigator.clipboard.writeText(href);
    setGraphHint("已复制路径，可在资源管理器粘贴打开", false);
  } catch (_) {
    window.prompt("复制路径后在资源管理器打开：", href);
  }
}

function editFieldsHtml(tag, props) {
  if (tag === "material") {
    const src = props.source_url || "";
    const meta = sourceLinkMeta(src);
    const jumpDisabled = !src ? "disabled aria-disabled=\"true\"" : "";
    return `
      <label>名称<input name="name" value="${escapeHtml(props.name || "")}" maxlength="48" /></label>
      <label>类型
        <select name="material_type">
          ${["doc", "paper", "patent", "standard", "news"]
            .map(
              (t) =>
                `<option value="${t}" ${props.material_type === t ? "selected" : ""}>${t}</option>`
            )
            .join("")}
        </select>
      </label>
      <label>标题<input name="title" value="${escapeHtml(props.title || "")}" maxlength="120" /></label>
      <label>摘要<textarea name="summary" rows="2" maxlength="300">${escapeHtml(props.summary || "")}</textarea></label>
      <label>来源链接
        <div class="field-with-action">
          <input id="editSourceUrl" name="source_url" value="${escapeHtml(src)}" maxlength="300" placeholder="https://… 或共享盘路径" />
          <button type="button" class="btn-jump" id="btnJumpSource" data-kind="${meta.kind}" data-href="${escapeHtml(meta.href)}" ${jumpDisabled}>${meta.label}</button>
        </div>
      </label>
      <label>发布日期<input name="published_at" value="${escapeHtml(props.published_at || "")}" maxlength="32" /></label>
    `;
  }
  return `
    <label>名称<input name="name" value="${escapeHtml(props.name || "")}" maxlength="40" /></label>
    <label>描述<textarea name="description" rows="3" maxlength="300">${escapeHtml(props.description || "")}</textarea></label>
    <label>关键词<input name="keywords" value="${escapeHtml(props.keywords || "")}" maxlength="120" /></label>
    ${
      tag === "technology" || tag === "module"
        ? `<label>状态
            <select name="status">
              ${["active", "draft", "deprecated"]
                .map(
                  (s) =>
                    `<option value="${s}" ${(props.status || "active") === s ? "selected" : ""}>${s}</option>`
                )
                .join("")}
            </select>
          </label>`
        : ""
    }
  `;
}

async function openEdgeDetail(edge) {
  if (!edge?.src_vid || !edge?.dst_vid) return;
  detailEdge = {
    id: edge.id || edgeKey(edge),
    src_vid: edge.src_vid,
    dst_vid: edge.dst_vid,
    edge_type: edge.edge_type || "other",
    count: edge.count || 1,
  };
  detailVid = null;
  detailNode = null;

  const srcN = lookupNodeBrief(detailEdge.src_vid);
  const dstN = lookupNodeBrief(detailEdge.dst_vid);
  const srcName = nodeDisplayName(srcN || { vid: detailEdge.src_vid, props: {} });
  const dstName = nodeDisplayName(dstN || { vid: detailEdge.dst_vid, props: {} });
  const relName = REL_LABEL[detailEdge.edge_type] || detailEdge.edge_type;

  $("drawerTag").textContent = "关系";
  $("drawerTitle").textContent = relName;
  $("drawerVid").textContent = `${detailEdge.src_vid} → ${detailEdge.dst_vid}`;
  $("drawerLink").hidden = true;
  $("drawerLink").style.display = "none";

  $("drawerBody").innerHTML = `
    <div class="edge-detail">
      <p class="hint" style="margin:0 0 10px">点击关系线查看详情；下方可跳转到两端节点。</p>
      <div class="edge-meta">
        <div><span class="muted">类型</span><strong>${escapeHtml(relName)}</strong> <span class="mono muted">(${escapeHtml(detailEdge.edge_type)})</span></div>
        <div><span class="muted">方向</span><strong>${escapeHtml(srcName)}</strong> → <strong>${escapeHtml(dstName)}</strong></div>
        ${detailEdge.count > 1 ? `<div><span class="muted">聚合</span><strong>${detailEdge.count}</strong> 条同向同类型边</div>` : ""}
      </div>
      <h4>连接实体</h4>
      <ul class="rel-list">
        <li class="rel-row">
          <div data-vid="${escapeHtml(detailEdge.src_vid)}" class="rel-main" style="cursor:pointer;flex:1">
            <div class="name">${escapeHtml(srcName)}</div>
            <div class="meta">起点 · ${escapeHtml(TAG_LABEL[srcN?.tag] || srcN?.tag || "节点")}</div>
          </div>
        </li>
        <li class="rel-row">
          <div data-vid="${escapeHtml(detailEdge.dst_vid)}" class="rel-main" style="cursor:pointer;flex:1">
            <div class="name">${escapeHtml(dstName)}</div>
            <div class="meta">终点 · ${escapeHtml(TAG_LABEL[dstN?.tag] || dstN?.tag || "节点")}</div>
          </div>
        </li>
      </ul>
    </div>
  `;

  $("detailDrawer").hidden = false;
  document.querySelector(".canvas-body")?.classList.add("with-drawer");
  $("btnFocusNode").dataset.vid = detailEdge.src_vid;
  $("btnDeleteNode").dataset.vid = "";
  syncDrawerActionLabels();

  if (lastGraphPayload?.data) {
    drawGraph(lastGraphPayload.data, lastGraphPayload.centerVid);
  }
  requestAnimationFrame(() => applyGraphSelection());
}

async function openDetail(vid, { focusGraph = false } = {}) {
  detailEdge = null;
  detailVid = vid;
  const data = await api(`/vertices/${encodeURIComponent(vid)}/detail`);
  const node = data.node;
  detailNode = node;
  const props = node.props || {};
  const name = props.name || props.title || node.vid;

  $("drawerTag").textContent = TAG_LABEL[node.tag] || node.tag;
  $("drawerTitle").textContent = name;
  $("drawerVid").textContent = node.vid;

  const relHtml = Object.entries(data.relations || {})
    .filter(([, items]) => items.length)
    .map(([et, items]) => {
      const lis = items
        .map((r) => {
          const src = r.direction === "out" ? vid : r.vid;
          const dst = r.direction === "out" ? r.vid : vid;
          const meta = r.tag === "material" ? sourceLinkMeta(r.source_url) : null;
          const jumpBtn =
            meta && meta.href
              ? `<button type="button" class="btn-jump" data-jump-source data-kind="${meta.kind}" data-href="${escapeHtml(meta.href)}" title="${escapeHtml(meta.label)}">${meta.label}</button>`
              : "";
          return `<li class="rel-row">
            <div data-vid="${escapeHtml(r.vid)}" class="rel-main" style="cursor:pointer;flex:1">
              <div class="name">${escapeHtml(r.name)}</div>
              <div class="meta">${TAG_LABEL[r.tag] || r.tag} · ${r.direction === "out" ? "→" : "←"} ${REL_LABEL[et] || et}</div>
            </div>
            ${jumpBtn}
            <button type="button" class="btn-x" data-del-edge="${escapeHtml(et)}" data-src="${escapeHtml(src)}" data-dst="${escapeHtml(dst)}">删边</button>
          </li>`;
        })
        .join("");
      return `<div class="rel-block"><h4>${REL_LABEL[et] || et}（${items.length}）</h4><ul class="rel-list">${lis}</ul></div>`;
    })
    .join("");

  $("drawerBody").innerHTML = `
    <form id="editNodeForm" class="edit-form">
      ${editFieldsHtml(node.tag, props)}
      <button type="submit">保存修改</button>
      <p id="editMsg" class="msg" hidden></p>
    </form>
    <details class="rel-block add-rel-block">
      <summary>＋ 建立关联</summary>
      <div class="add-rel-form">
        <label>边类型
          <select id="relType">
            <option value="belongs_to">归属 belongs_to</option>
            <option value="supports">支撑 supports</option>
            <option value="relates_to">关联 relates_to</option>
          </select>
        </label>
        <label>方向
          <select id="relDir">
            <option value="this_to_target">本节点 → 目标</option>
            <option value="target_to_this">目标 → 本节点</option>
          </select>
        </label>
        <label>目标节点
          <select id="relTarget" class="rel-target-select"></select>
        </label>
        <button type="button" id="btnAddRel">建立</button>
        <p id="relMsg" class="msg" hidden></p>
      </div>
    </details>
    <p class="hint">邻接 ${data.stats?.neighbors ?? 0} 个节点</p>
    ${relHtml || `<p class="muted">暂无直接关联</p>`}
  `;

  const relSelect = $("relTarget");
  if (relSelect) {
    (async () => {
      try {
        const resp = await api("/vertices?limit=500");
        const items = resp.items || [];
        relSelect.innerHTML = items
          .filter((n) => n.vid !== vid)
          .map((n) => {
            const nm = nodeDisplayName(n);
            return `<option value="${escapeHtml(n.vid)}">${escapeHtml(nm)}（${TAG_LABEL[n.tag] || n.tag}）</option>`;
          })
          .join("") || `<option value="">（无其他节点）</option>`;
      } catch (_) {
        relSelect.innerHTML = `<option value="">（加载目标失败）</option>`;
      }
    })();
  }
  const addBtn = $("btnAddRel");
  if (addBtn) {
    addBtn.addEventListener("click", () => addConnectionFromDetail(vid).catch(alertError));
  }

  $("editNodeForm").addEventListener("submit", (ev) => {
    ev.preventDefault();
    saveDetailEdit().catch(alertError);
  });

  const srcInput = $("editSourceUrl");
  const jumpBtn = $("btnJumpSource");
  if (srcInput && jumpBtn) {
    const syncJump = () => {
      const meta = sourceLinkMeta(srcInput.value);
      jumpBtn.dataset.kind = meta.kind;
      jumpBtn.dataset.href = meta.href;
      jumpBtn.textContent = meta.label;
      jumpBtn.disabled = !meta.href;
    };
    srcInput.addEventListener("input", syncJump);
    jumpBtn.addEventListener("click", () => openSourceLink(jumpBtn).catch(alertError));
  }

  const link = $("drawerLink");
  const footerMeta = sourceLinkMeta(props.source_url);
  if (footerMeta.href) {
    link.hidden = false;
    link.style.display = "";
    link.textContent = footerMeta.label;
    if (footerMeta.kind === "http") {
      link.href = footerMeta.href;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.onclick = null;
    } else {
      link.href = "#";
      link.removeAttribute("target");
      link.onclick = (ev) => {
        ev.preventDefault();
        openSourceLink({ dataset: { kind: footerMeta.kind, href: footerMeta.href } }).catch(alertError);
      };
    }
  } else {
    link.hidden = true;
    link.removeAttribute("href");
    link.onclick = null;
    link.style.display = "none";
    link.textContent = "打开来源";
  }

  $("detailDrawer").hidden = false;
  document.querySelector(".canvas-body")?.classList.add("with-drawer");
  $("btnFocusNode").dataset.vid = vid;
  $("btnDeleteNode").dataset.vid = vid;
  syncDrawerActionLabels();

  [...$("nodeList").querySelectorAll("li")].forEach((li) => {
    li.classList.toggle("active", li.dataset.vid === vid || li.dataset.vid === focusVid);
  });

  if (focusGraph) {
    await showSubgraph(vid, { withDetail: false });
  } else if (lastGraphPayload?.data) {
    // Stay on current canvas; redraw so selection highlight / dimming apply
    drawGraph(lastGraphPayload.data, lastGraphPayload.centerVid);
    updateFocusMetaAfterDraw(node);
  }

  requestAnimationFrame(() => applyGraphSelection());
}

async function saveDetailEdit() {
  if (!detailVid || !detailNode) return;
  const form = $("editNodeForm");
  const fd = new FormData(form);
  const props = {};
  for (const [k, v] of fd.entries()) {
    props[k] = String(v).trim();
  }
  const msg = $("editMsg");
  msg.hidden = false;
  msg.className = "msg";
  msg.textContent = "保存中…";
  const updated = await api(`/vertices/${encodeURIComponent(detailVid)}`, {
    method: "PATCH",
    body: JSON.stringify({ props }),
  });
  msg.textContent = "已保存";
  detailNode = updated;
  $("drawerTitle").textContent = updated.props?.name || updated.props?.title || detailVid;
  await searchNodes();
  await refreshClusterOptions().catch(() => {});
  if (overviewMode) await showOverview();
  else if (focusVid) await showSubgraph(focusVid, { withDetail: false });
  await openDetail(detailVid, { focusGraph: false });
}

async function deleteEdgeFromDetail(btn) {
  const edge_type = btn.dataset.delEdge;
  const src_vid = btn.dataset.src;
  const dst_vid = btn.dataset.dst;
  if (!edge_type || !src_vid || !dst_vid) return;
  if (!confirm(`删除边 ${src_vid} -${edge_type}-> ${dst_vid} ?`)) return;
  await api("/edges", {
    method: "DELETE",
    body: JSON.stringify({ edge_type, src_vid, dst_vid }),
  });
  await openDetail(detailVid, { focusGraph: false });
  if (overviewMode) await showOverview();
  else if (focusVid) await showSubgraph(focusVid, { withDetail: false });
}

async function showOverview() {
  overviewMode = true;
  focusVid = null;
  forceFitNext = true;
  // 按层动态加载：根据当前「显示层级」只向服务端要该层及上层，
  // 避免材料层很大时常年全量拉取把画布撑爆；窗口层级变了会重新拉取（bindViewControlsChanged）。
  const cap = layerScope === "only" ? layerCap : layerCap || "technology";
  const data = await api(`/overview?limit_nodes=3000&limit_edges=8000&layer_cap=${encodeURIComponent(cap)}`);
  drawGraph(data, detailVid);
  updateFocusMetaAfterDraw(null);
  [...$("nodeList").querySelectorAll("li")].forEach((li) => {
    li.classList.toggle("active", li.dataset.vid === detailVid);
  });
}

async function showSubgraph(vid, { withDetail = true } = {}) {
  overviewMode = false;
  focusVid = vid;
  forceFitNext = true;
  const data = await api(`/subgraph/${encodeURIComponent(vid)}?depth=${SUBGRAPH_DEPTH}`);
  const center = (data.nodes || []).find((n) => n.vid === vid);
  const ft = $("focusTitle"); if (ft) ft.textContent = "";
  drawGraph(data, vid);
  const shown = lastGraphPayload?.view;
  const n = (shown?.nodes || []).length;
  const matNote = hideMaterials ? " · 已藏文档" : "";
  const fm = $("focusMeta"); if (fm) fm.textContent = "";
  [...$("nodeList").querySelectorAll("li")].forEach((li) => {
    li.classList.toggle("active", li.dataset.vid === vid || li.dataset.vid === detailVid);
  });
  if (withDetail) {
    await openDetail(vid, { focusGraph: false });
  }
}

function setGraphHint(text, isErr) {
  let hint = $("graphHint");
  if (!hint) {
    hint = document.createElement("div");
    hint.id = "graphHint";
    hint.className = "graph-hint";
    const stage = document.querySelector(".graph-stage") || $("network");
    stage.appendChild(hint);
  }
  hint.textContent = text || "";
  hint.className = "graph-hint" + (isErr ? " err" : "");
  hint.hidden = !text;
}

function resizeGraphViewport() {
  if (viewMode === "2d" && network) {
    const container = $("network");
    if (!container || container.hidden) return;
    const box = container.getBoundingClientRect();
    if (box.width < 40 || box.height < 40) return;
    network.setSize(`${Math.floor(box.width)}px`, `${Math.floor(box.height)}px`);
    network.redraw();
  }
  if (viewMode === "3d" && graph3d) {
    const el = $("network3d");
    if (!el || el.hidden) return;
    const box = el.getBoundingClientRect();
    const w = Math.max(40, Math.floor(box.width || el.clientWidth || 800));
    const h = Math.max(40, Math.floor(box.height || el.clientHeight || 500));
    graph3d.width(w).height(h);
  }
}

function fitCurrentGraph() {
  if (viewMode === "2d" && network) {
    resizeGraphViewport();
    network.fit({ animation: { duration: 280 }, padding: 56 });
    return;
  }
  if (viewMode === "3d" && graph3d) {
    resizeGraphViewport();
    focusGraph3dCamera(null);
  }
}

/** Keep Three meshes in sync with d3 coords (engine can finish before first paint).
 *  Do NOT call graph3d.refresh() here — it recreates meshes at origin and undoes the sync. */
function syncGraph3dPositions() {
  if (!graph3d) return 0;
  const nodes = graph3d.graphData?.().nodes || [];
  let n = 0;
  for (const node of nodes) {
    const obj = node.__threeObj;
    if (!obj || !Number.isFinite(node.x) || !Number.isFinite(node.y) || !Number.isFinite(node.z)) continue;
    obj.position.set(node.x, node.y, node.z);
    n += 1;
  }
  return n;
}

/** Stable 3D framing via camera + OrbitControls (cameraPosition lookAt is unreliable here). */
function focusGraph3dCamera(centerVid) {
  if (!graph3d || viewMode !== "3d") return;
  try {
    syncGraph3dPositions();
    const nodes = (graph3d.graphData().nodes || []).filter(
      (n) => Number.isFinite(n.x) && Number.isFinite(n.y) && Number.isFinite(n.z)
    );
    if (!nodes.length) return;
    let cx = 0;
    let cy = 0;
    let cz = 0;
    let maxR = 12;
    for (const n of nodes) {
      cx += n.x;
      cy += n.y;
      cz += n.z;
    }
    cx /= nodes.length;
    cy /= nodes.length;
    cz /= nodes.length;
    for (const n of nodes) {
      const r = Math.hypot(n.x - cx, n.y - cy, n.z - cz);
      if (r > maxR) maxR = r;
    }
    if (centerVid) {
      const hit = nodes.find((n) => n.id === centerVid);
      if (hit) {
        cx = hit.x;
        cy = hit.y;
        cz = hit.z;
      }
    }
    // Keep camera close enough that the cluster fills most of the viewport
    const dist = Math.max(48, maxR * 1.45 + 28);
    const cam = graph3d.camera?.();
    const ctrl = graph3d.controls?.();
    if (cam && ctrl) {
      ctrl.target.set(cx, cy, cz);
      cam.position.set(cx + dist * 0.5, cy + dist * 0.32, cz + dist * 0.95);
      cam.near = 0.1;
      cam.far = Math.max(5000, dist * 20);
      cam.updateProjectionMatrix();
      ctrl.update();
    } else {
      graph3d.zoomToFit(300, 36);
    }
    forceFit3dNext = false;
  } catch (_) {
    try {
      graph3d.zoomToFit(300, 36);
      forceFit3dNext = false;
    } catch (__) {
      /* ignore */
    }
  }
}

function setViewMode(mode, onReady) {
  const next = mode === "3d" ? "3d" : "2d";
  const switched = next !== viewMode;
  viewMode = next;
  const b2 = $("btnView2d");
  const b3 = $("btnView3d");
  if (b2) b2.classList.toggle("active", viewMode === "2d");
  if (b3) b3.classList.toggle("active", viewMode === "3d");
  $("network").hidden = viewMode !== "2d";
  $("network3d").hidden = viewMode !== "3d";
  syncViewControls();
  // Fresh 3D instance avoids stale WebGL/camera after hide↔show
  if (switched && viewMode === "3d") destroyGraph3d();
  if (switched && viewMode === "2d") clear3dHtmlLabels();
  // Wait for layout after un-hiding, then draw/resize (0-size WebGL/vis breaks both views)
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      resizeGraphViewport();
      if (lastGraphPayload) {
        if (viewMode === "2d") {
          forceFitNext = true;
          drawGraph(lastGraphPayload.data, lastGraphPayload.centerVid);
          // Second fit after layout settles (hidden→shown can leave canvas at 0×0 briefly)
          setTimeout(() => {
            if (viewMode === "2d" && network) {
              resizeGraphViewport();
              network.fit({ animation: false, padding: 56 });
            }
          }, 200);
        } else {
          forceFit3dNext = true;
          drawGraph(lastGraphPayload.data, lastGraphPayload.centerVid);
        }
      } else if (viewMode === "3d") {
        setGraphHint("暂无图数据，先点全貌或选中节点", false);
      }
      if (typeof onReady === "function") onReady();
    });
  });
}

/** 确保在二维视图下执行回调（列表点击/查高高亮切换到 2D 呈现，规避 3D 卡顿）。 */
function focusIn2D(cb) {
  if (viewMode !== "2d") {
    // setViewMode 已在内部的一次 rAF 里完成切视图+重绘，回调紧随其后执行，
    // 避免再排一次双 rAF 造成重复重绘。
    setViewMode("2d", cb);
  } else {
    cb();
  }
}

function filterByLayer(data) {
  if (!data) return data;
  readViewControls();
  const cap = LAYER_RANK[layerCap] ?? 3;
  const keep = new Set(
    (data.nodes || [])
      .filter((n) => {
        const r = LAYER_RANK[n.tag] ?? 99;
        return layerScope === "only" ? r === cap : r <= cap;
      })
      .map((n) => n.vid)
  );
  // In subgraph, always keep the focus node even if filtered out by layer
  if (focusVid) keep.add(focusVid);
  // In subgraph, keep the materials that directly support the focus node
  // (its 支撑材料), regardless of the layer cap, so clicking a technology
  // node still shows the material spheres feeding it.
  if (focusVid) {
    for (const e of data.edges || []) {
      if (e.edge_type === "supports" && e.dst_vid === focusVid) {
        keep.add(e.src_vid);
        keep.add(e.dst_vid);
      }
    }
  }
  return {
    ...data,
    nodes: (data.nodes || []).filter((n) => keep.has(n.vid)),
    edges: (data.edges || []).filter(
      (e) => keep.has(e.src_vid) && keep.has(e.dst_vid)
    ),
  };
}

function filterByDomain(data) {
  readDomainFilterFromControl();
  const name = domainFilter?.trim?.();
  if (!name) return data;
  const domNode = domainIndex.get(name);
  const domVid = domNode?.vid;
  if (!domVid) return data;
  const nodes = data.nodes || [];
  const edges = data.edges || [];
  // Subgraph / single-node view: payload usually has no domain nodes, and the
  // belongs_to chain back to the domain isn't present. Applying the subtree
  // filter here would wrongly empty the view — so only filter when this is a
  // full/overview payload that actually contains domain nodes.
  if (!nodes.some((n) => n.tag === "domain")) return data;
  const byId = new Map(nodes.map((n) => [n.vid, n]));
  // Build parent map via belongs_to (child -> parent). Subtree = nodes whose
  // ancestry reaches the selected domain root.
  const parentOf = new Map();
  for (const e of edges) {
    if (e.edge_type === "belongs_to") parentOf.set(e.src_vid, e.dst_vid);
  }
  const keep = new Set();
  const walk = (vid) => {
    if (keep.has(vid)) return;
    keep.add(vid);
    for (const e of edges) {
      if (e.edge_type === "belongs_to" && e.dst_vid === vid) walk(e.src_vid);
    }
  };
  // 节点是否属于所选领域：沿 belongs_to 向上能找到该领域即算（领域之上还有车辆根，不能只比“根”）
  const inDomain = new Set();
  const hasAncestor = (vid, target) => {
    let cur = vid;
    const seen = new Set();
    while (cur && !seen.has(cur)) {
      if (cur === target) return true;
      seen.add(cur);
      cur = parentOf.get(cur);
    }
    return false;
  };
  for (const n of nodes) {
    if (hasAncestor(n.vid, domVid)) inDomain.add(n.vid);
  }
  keep.add(domVid);
  // 选中某领域时，整车根球一并在图中保留（与所选领域同时呈现）
  const vehicle = nodes.find((n) => n.tag === "vehicle");
  if (vehicle) keep.add(vehicle.vid);
  // Include materials that support a kept technology (they are reachable via supports)
  for (const e of edges) {
    if (e.edge_type === "supports" && inDomain.has(e.dst_vid)) {
      keep.add(e.src_vid); // material
      keep.add(e.dst_vid);
    }
  }
  inDomain.forEach((v) => keep.add(v));
  return {
    ...data,
    nodes: nodes.filter((n) => keep.has(n.vid)),
    edges: edges.filter((e) => keep.has(e.src_vid) && keep.has(e.dst_vid)),
  };
}

function readDomainFilterFromControl() {
  const domEl = $("domainFilter");
  if (domEl) domainFilter = domEl.value || "";
}

function aggregateEdgeList(edges) {  const map = new Map();
  for (const e of edges || []) {
    const key = `${e.src_vid}|${e.edge_type}|${e.dst_vid}`;
    const prev = map.get(key);
    if (!prev) {
      map.set(key, { ...e, count: 1 });
    } else {
      prev.count += 1;
    }
  }
  return [...map.values()];
}

function computeDegrees(edges) {
  const deg = new Map();
  for (const e of edges || []) {
    const w = e.count || 1;
    deg.set(e.src_vid, (deg.get(e.src_vid) || 0) + w);
    deg.set(e.dst_vid, (deg.get(e.dst_vid) || 0) + w);
  }
  return deg;
}

/** Mild degree-weighted mass — hubs push a bit harder without flinging the graph. */
function nodePhysicsMass(n, degree) {
  const deg = degree || 0;
  const tagBase =
    n.tag === "vehicle" ? 4.0
    : n.tag === "domain" ? 3.2
    : n.tag === "subdomain" ? 2.0
    : n.tag === "module" ? 1.6
    : n.tag === "technology" ? 1.2
    : 1;
  return Math.min(8, tagBase + deg * 0.22);
}

function edgeSpringLength(e, degrees) {
  const d =
    (degrees?.get(e.src_vid) || 1) + (degrees?.get(e.dst_vid) || 1) + (e.count || 1);
  return 95 + Math.min(120, d * 3.5);
}

function forcePhysicsOptions() {
  return {
    enabled: true,
    barnesHut: {
      // Balanced: readable spread without sending nodes to ±∞ (which shrinks fit)
      gravitationalConstant: -4200,
      centralGravity: 0.12,
      springLength: 130,
      springConstant: 0.035,
      damping: 0.42,
      avoidOverlap: 0.85,
    },
    maxVelocity: 40,
    minVelocity: 0.75,
    timestep: 0.45,
    stabilization: {
      enabled: true,
      iterations: 220,
      updateInterval: 25,
      fit: false, // we fit once after stabilize (see drawGraph2d)
    },
  };
}

function reheatForceLayout() {
  if (layoutMode !== "force") {
    layoutMode = "force";
    forceFitNext = true;
    syncViewControls();
    redrawCurrentGraph();
    setGraphHint("已切换力导向并重新撑开：枢纽点斥力更大，文档会被推开", false);
    return;
  }
  if (!network || viewMode !== "2d") {
    forceFitNext = true;
    redrawCurrentGraph();
    return;
  }
  try {
    network.setOptions({ physics: forcePhysicsOptions() });
    // kick velocities so clustered nodes disperse (Explorer “Reheat”)
    const ids = network.body.data.nodes.getIds();
    ids.forEach((id) => {
      const body = network.body.nodes[id];
      if (!body) return;
      body.vx = (Math.random() - 0.5) * 12;
      body.vy = (Math.random() - 0.5) * 12;
    });
    network.startSimulation();
    network.stabilize(220);
    setGraphHint("已重新撑开：按度数斥力推开重叠节点", false);
  } catch (err) {
    forceFitNext = true;
    redrawCurrentGraph();
  }
}

function applyIsolateFilter(data) {
  const seed = detailVid || focusVid;
  if (!isolateSelection || !seed) return data;
  const keep = neighborSet(seed, data.edges || []);
  return {
    ...data,
    nodes: (data.nodes || []).filter((n) => keep.has(n.vid)),
    edges: (data.edges || []).filter(
      (e) => keep.has(e.src_vid) && keep.has(e.dst_vid)
    ),
  };
}

/** Soft-cap for 2D readability (Explorer recommends ≤5000 total elements). */
function enforceCanvasBudget(data) {
  lastCanvasTruncated = !!(data && data.truncated);
  if (!data) return data;
  let nodes = data.nodes || [];
  let edges = data.edges || [];
  const total = nodes.length + edges.length;
  if (total <= CANVAS_HARD_LIMIT) {
    return { ...data, nodes, edges };
  }
  // Prefer dropping materials, then relates_to edges
  const mats = new Set(nodes.filter((n) => n.tag === "material").map((n) => n.vid));
  nodes = nodes.filter((n) => n.tag !== "material");
  edges = edges.filter(
    (e) =>
      e.edge_type !== "supports" &&
      !mats.has(e.src_vid) &&
      !mats.has(e.dst_vid)
  );
  if (nodes.length + edges.length > CANVAS_HARD_LIMIT) {
    edges = edges.filter((e) => e.edge_type !== "relates_to");
  }
  if (nodes.length + edges.length > CANVAS_HARD_LIMIT) {
    nodes = nodes.slice(0, Math.min(nodes.length, 1200));
    const keep = new Set(nodes.map((n) => n.vid));
    edges = edges
      .filter((e) => keep.has(e.src_vid) && keep.has(e.dst_vid))
      .slice(0, CANVAS_HARD_LIMIT - nodes.length);
  }
  lastCanvasTruncated = true;
  return { ...data, nodes, edges, truncated: true };
}

function updateCanvasBudgetBadge(view) {
  const el = $("canvasBudget");
  if (!el) return;
  const n = (view?.nodes || []).length;
  const e = (view?.edges || []).length;
  const total = n + e;
  el.textContent = `${n}点 ${e}边`;
  el.classList.remove("warn", "danger");
  if (total >= CANVAS_HARD_LIMIT || lastCanvasTruncated) el.classList.add("danger");
  else if (total >= CANVAS_SOFT_LIMIT) el.classList.add("warn");
  el.title = lastCanvasTruncated
    ? `已截断展示（参考 Nebula Explorer：2D 建议 ≤${CANVAS_HARD_LIMIT} 图元）`
    : `画布图元 ${total}（软阈值 ${CANVAS_SOFT_LIMIT}，硬阈值 ${CANVAS_HARD_LIMIT}）`;
}

function filterGraphPayload(data) {
  if (!data) return data;
  // domainFilter/dropdown 由 refreshClusterOptions 用全量领域列表维护，
  // 不随局部 payload 重建（子图模式不得清掉选中领域）。
  let view = filterByDomain(data); // domain subtree isolated on full payload
  view = filterByLayer(view);
  view = applyIsolateFilter(view);
  view = enforceCanvasBudget(view);
  // Always bundle parallel edges (same endpoints + type) so dense pairs stay readable
  return { ...view, edges: aggregateEdgeList(view.edges) };
}

function neighborSet(vid, edges) {
  const s = new Set([vid]);
  for (const e of edges || []) {
    if (e.src_vid === vid) s.add(e.dst_vid);
    if (e.dst_vid === vid) s.add(e.src_vid);
  }
  return s;
}

function buildParentIndex(nodes, edges) {
  const byId = new Map((nodes || []).map((n) => [n.vid, n]));
  const parents = new Map();
  const add = (child, parent) => {
    if (!child || !parent || child === parent) return;
    if (!parents.has(child)) parents.set(child, []);
    if (!parents.get(child).includes(parent)) parents.get(child).push(parent);
  };
  for (const e of edges || []) {
    if (e.edge_type === "belongs_to") add(e.src_vid, e.dst_vid);
    if (e.edge_type === "supports") add(e.src_vid, e.dst_vid);
  }
  return { byId, parents };
}

/** 树状模式专用：把原始边转成「父→子」方向的布局边（层级边反向；非层级边丢弃）。 */
function treeEdgesFor(edges) {
  const out = [];
  for (const e of edges || []) {
    if (e.edge_type === "belongs_to" || e.edge_type === "supports") {
      out.push({ ...e, src_vid: e.dst_vid, dst_vid: e.src_vid });
    }
  }
  return out;
}

/** 树状模式用：按真实层级（child→parent 边）计算每层（行）编号，车辆=0，领域=1，子域=2，模块=3，技术点=4… */
function buildTreeLevels(nodes, edges) {
  const byId = new Map((nodes || []).map((n) => [n.vid, n]));
  const parents = new Map(); // vid -> [parent vid]（child→parent）
  const add = (c, p) => {
    if (!c || !p || c === p) return;
    if (!parents.has(c)) parents.set(c, []);
    if (!parents.get(c).includes(p)) parents.get(c).push(p);
  };
  for (const e of edges || []) {
    if (e.edge_type === "belongs_to") add(e.src_vid, e.dst_vid); // 技术点→子域/领域、子域→领域
    if (e.edge_type === "supports") add(e.src_vid, e.dst_vid); // 文档→技术点
  }
  const level = new Map();
  for (const n of nodes || []) {
    if (n.tag === "vehicle") level.set(n.vid, 0);
    if (n.tag === "domain") level.set(n.vid, 1);
  }
  // 多层 DAG 松弛：level(child) = 1 + min(level(parents))
  for (let pass = 0; pass <= (nodes || []).length; pass++) {
    let changed = false;
    for (const n of nodes || []) {
      const par = parents.get(n.vid) || [];
      if (!par.length) continue;
      const pl = par.map((p) => level.get(p)).filter((v) => Number.isFinite(v));
      if (!pl.length) continue;
      const nl = Math.min(...pl) + 1;
      if ((level.get(n.vid) ?? Infinity) !== nl) {
        level.set(n.vid, nl);
        changed = true;
      }
    }
    if (!changed) break;
  }
  // 兜底：孤儿节点按标签给默认列，保证每列固定
  for (const n of nodes || []) {
    if (!level.has(n.vid)) level.set(n.vid, LAYER_RANK[n.tag] ?? 3);
  }
  return level;
}

/** 三维树状「环形」布局：层级径向树。
 * 每层（level）一圈、z 一层；子球位于父球角度方向的扇形内（楔形按子树叶子数分配），
 * 连线沿径向短直基本不交叉；嵌套技术点（父为技术点）自然落在下一层。
 * 返回 { pos: {vid:{x,y}}, level: Map(vid->level) }。
 */
function computeRadial3DPositions(nodes, edges) {
  const byId = new Map((nodes || []).map((n) => [n.vid, n]));
  const levels = buildTreeLevels(nodes, edges);
  const children = new Map(); // parent -> [child]
  const addChild = (p, c) => {
    if (!p || !c || p === c) return;
    if (!children.has(p)) children.set(p, []);
    if (!children.get(p).includes(c)) children.get(p).push(c);
  };
  for (const e of edges || []) {
    if (e.edge_type === "belongs_to") addChild(e.dst_vid, e.src_vid);
    if (e.edge_type === "supports") addChild(e.dst_vid, e.src_vid);
  }
  const weightMemo = new Map();
  const leafWeight = (v) => {
    if (weightMemo.has(v)) return weightMemo.get(v);
    const kids = children.get(v) || [];
    const w = kids.length ? kids.reduce((s, k) => s + leafWeight(k), 0) : 1;
    weightMemo.set(v, w);
    return w;
  };
  // 每个父节点 children 排序，稳定且让同层铺开
  for (const list of children.values()) {
    list.sort((a, b) => {
      const ta = byId.get(a)?.tag || "";
      const tb = byId.get(b)?.tag || "";
      const ra = LAYER_RANK[ta] ?? 9;
      const rb = LAYER_RANK[tb] ?? 9;
      return ra - rb || nodeDisplayName(byId.get(a) || {}).localeCompare(nodeDisplayName(byId.get(b) || {}), "zh");
    });
  }
  const hasParent = new Set();
  children.forEach((cs) => cs.forEach((c) => hasParent.add(c)));
  const roots = (nodes || [])
    .filter((n) => n.tag === "domain" || (!hasParent.has(n.vid) && n.tag !== "vehicle"))
    .map((n) => n.vid)
    .sort((a, b) => nodeDisplayName(byId.get(a) || {}).localeCompare(nodeDisplayName(byId.get(b) || {}), "zh"));

  const R_STEP = 150;
  const pos = {};
  const seen = new Set();

  // 车辆作为最上层中心的轴线顶点，不参与扇形分配
  for (const n of nodes || []) {
    if (n.tag === "vehicle") pos[n.vid] = { x: 0, y: 0 };
  }
  if (!roots.length) roots.push(...[...(nodes || [])].filter((n) => !pos[n.vid]).map((n) => n.vid));

  const place = (v, a0, a1) => {
    const mid = (a0 + a1) / 2;
    const lv = levels.get(v) ?? 1;
    const r = Math.max(20, (lv - 1) * R_STEP + 20); // 根也在小半径处，不压原点
    pos[v] = { x: Math.cos(mid) * r, y: Math.sin(mid) * r };
    const kids = children.get(v) || [];
    if (!kids.length) return;
    const total = kids.reduce((s, k) => s + leafWeight(k), 0) || 1;
    let cursor = a0;
    for (const k of kids) {
      const w = (leafWeight(k) / total) * (a1 - a0);
      place(k, cursor, cursor + w);
      cursor += w;
    }
  };

  const totalW = roots.reduce((s, r) => s + leafWeight(r), 0) || 1;
  let cursorR = 0;
  for (const r of roots) {
    const w = (leafWeight(r) / totalW) * 2 * Math.PI;
    place(r, cursorR, cursorR + w);
    cursorR += w;
  }

  // 兜底：仍未放置（如环）
  let fallback = 0;
  for (const n of nodes || []) {
    if (!pos[n.vid]) {
      pos[n.vid] = { x: 0, y: (fallback++) * 26 - 1300 };
    }
  }
  return { pos, level: levels };
}

/** 树状模式用：自上而下（根在顶部）种子坐标。x=子树内水平带（子层围绕父节点展开）；y=层级×行距。之后节点自由拖动。 */
function computeTreePositions(nodes, edges, centerMode) {
  const byId = new Map((nodes || []).map((n) => [n.vid, n]));
  const levels = buildTreeLevels(nodes, edges);
  const children = new Map(); // parent(vid) -> [child...]（双向层级边统一为 父→子）
  const addChild = (p, c) => {
    if (!p || !c || p === c) return;
    if (!children.has(p)) children.set(p, []);
    if (!children.get(p).includes(c)) children.get(p).push(c);
  };
  for (const e of edges || []) {
    if (e.edge_type === "belongs_to") addChild(e.dst_vid, e.src_vid);
    if (e.edge_type === "supports") addChild(e.dst_vid, e.src_vid);
  }
  for (const list of children.values()) {
    list.sort((a, b) => {
      const ta = byId.get(a)?.tag || "";
      const tb = byId.get(b)?.tag || "";
      const ra = LAYER_RANK[ta] ?? 9;
      const rb = LAYER_RANK[tb] ?? 9;
      return ra - rb || nodeDisplayName(byId.get(a) || {}).localeCompare(nodeDisplayName(byId.get(b) || {}), "zh");
    });
  }
  const hasParent = new Set();
  children.forEach((cs) => cs.forEach((c) => hasParent.add(c)));
  const roots = (nodes || [])
    .filter((n) => n.tag === "vehicle" || n.tag === "domain" || !hasParent.has(n.vid))
    .map((n) => n.vid)
    .sort((a, b) => nodeDisplayName(byId.get(a) || {}).localeCompare(nodeDisplayName(byId.get(b) || {}), "zh"));

  const ROW_H = 200; // 层级垂直间距
  const COL_W = 36;  // 同层兄弟最小水平间距
  const pos = {};
  let cursor = 0;

  const place = (vid) => {
    const kids = children.get(vid) || [];
    let left;
    let right;
    if (!kids.length) {
      left = cursor;
      right = cursor;
      cursor += COL_W;
    } else {
      const bands = [];
      for (const k of kids) {
        if (!pos[k] || !pos[k]._b) {
          place(k);
        }
        bands.push(pos[k]._b);
      }
      left = Math.min(...bands.map((b) => b.left));
      right = Math.max(...bands.map((b) => b.right));
    }
    const y = ((levels.get(vid) ?? 1) - 1) * ROW_H;
    // centerMode=true：父节点在自己子树水平带居中（初始"居中展开"）；false：左对齐"挂载式"
    const x = centerMode ? (left + right) / 2 : left;
    pos[vid] = { x, y, _b: { left, right } };
    return pos[vid]._b;
  };

  const seen = new Set();
  const mark = (vid) => {
    if (seen.has(vid)) return;
    seen.add(vid);
    (children.get(vid) || []).forEach(mark);
  };
  roots.forEach(mark);
  roots.forEach((r) => {
    if (!pos[r]) place(r);
  });
  // 兜底：仍未被放置的节点（如环）追加在默认行，列推进
  for (const n of nodes || []) {
    if (!pos[n.vid]) {
      pos[n.vid] = { x: cursor, y: ((levels.get(n.vid) ?? 1) - 1) * ROW_H };
      cursor += COL_W;
    }
  }
  // 同层去重：多父节点共享子块时可能出现同层同位，强制同层水平间距 >= COL_W
  const byRow = new Map();
  for (const p of Object.values(pos)) {
    if (!byRow.has(p.y)) byRow.set(p.y, []);
    byRow.get(p.y).push(p);
  }
  for (const list of byRow.values()) {
    list.sort((a, b) => a.x - b.x);
    for (let i = 1; i < list.length; i++) {
      const gap = list[i].x - list[i - 1].x;
      if (gap < COL_W) list[i].x = list[i - 1].x + COL_W;
    }
  }
  for (const k of Object.keys(pos)) {
    const { x, y } = pos[k];
    pos[k] = { x, y };
  }
  return pos;
}

/** 三维树状「环形」的 z：每个领域独占一层水平约束面（有高度差），车辆在最上层垂直轴上。
 * 返回 vid -> z 的映射。同一领域的整棵子树（含文档）落在同一平面（平面约束呈现）。 */
function computeTreePlaneZ(nodes, edges) {
  const byId = new Map((nodes || []).map((n) => [n.vid, n]));
  const parentOf = new Map();
  for (const e of edges || []) {
    // 归属与支撑都向上爬，确保文档也能定位到所属领域平面
    if (e.edge_type === "belongs_to" || e.edge_type === "supports") parentOf.set(e.src_vid, e.dst_vid);
  }
  const domainOf = (vid) => {
    let cur = vid;
    const seen = new Set();
    while (cur && !seen.has(cur)) {
      const t = byId.get(cur)?.tag;
      if (t === "domain") return cur;
      if (!parentOf.has(cur)) return null;
      seen.add(cur);
      cur = parentOf.get(cur);
    }
    return null;
  };
  const domains = (nodes || [])
    .filter((n) => n.tag === "domain")
    .sort((a, b) => nodeDisplayName(a).localeCompare(nodeDisplayName(b), "zh"));
  const indexBy = new Map();
  domains.forEach((d, i) => indexBy.set(d.vid, i));
  const zMap = new Map();
  const PLANE_GAP = 340;
  const orphanZ = -(domains.length + 2) * PLANE_GAP;
  for (const n of nodes || []) {
    if (n.tag === "vehicle") {
      zMap.set(n.vid, 0);
      continue;
    }
    const d = domainOf(n.vid);
    const i = d ? indexBy.get(d) : undefined;
    zMap.set(n.vid, i != null ? -(i + 1) * PLANE_GAP : orphanZ);
  }
  return zMap;
}

/** 三维树状「环形」的 XY：各领域球对齐到同一垂直轴上（XY 保持一致），
 * 每个领域整棵子树（含文档）以其领域球为圆心、在该领域平面上环形铺开。 */
function computeTreePlaneXY(nodes, edges) {
  const radialAll = computeRadialPositions(nodes || [], edges || []);
  const byId = new Map((nodes || []).map((n) => [n.vid, n]));
  const parentOf = new Map();
  for (const e of edges || []) {
    // 归属与支撑都向上爬，确保文档也能定位到所属领域中心
    if (e.edge_type === "belongs_to" || e.edge_type === "supports") parentOf.set(e.src_vid, e.dst_vid);
  }
  const domainOf = (vid) => {
    let cur = vid;
    const seen = new Set();
    while (cur && !seen.has(cur)) {
      const t = byId.get(cur)?.tag;
      if (t === "domain") return cur;
      if (!parentOf.has(cur)) return null;
      seen.add(cur);
      cur = parentOf.get(cur);
    }
    return null;
  };
  const out = {};
  for (const n of nodes || []) {
    if (n.tag === "vehicle") {
      out[n.vid] = { x: 0, y: 0 };
      continue;
    }
    const base = radialAll[n.vid] || { x: 0, y: 0 };
    if (n.tag === "domain") {
      out[n.vid] = { x: 0, y: 0 };
      continue;
    }
    const d = domainOf(n.vid);
    const c = (d && radialAll[d]) || { x: 0, y: 0 };
    out[n.vid] = { x: (base.x || 0) - (c.x || 0), y: (base.y || 0) - (c.y || 0) };
  }
  return out;
}

/** 三维树状「分层」：空间三个轴——车辆在原点 (0,0,0)。
 * 领域球沿 Y 交错、同高 Z 往下：奇数个领域时其中一个在 (0,0,-Z)，其余沿 ±Y 以固定 510 间隔展开；
 * 偶数个领域时全部沿 ±Y 以固定 510 间隔展开（都不在中心轴）。
 * 每个领域球作为其子树的根，子树 x 以领域节点为中心向左右居中发散、沿 -Z 逐层向下平铺展开，
 * 文档等叶子也按同样逻辑挂到上层球下面居中展开。
 * 返回 { vid: {x,y,z} }，坐标已含 z，直接使用。 */
function computeTree3DDown(nodes, edges) {
  const byId = new Map((nodes || []).map((n) => [n.vid, n]));
  // 复用二维垂直树的排布：x=子树水平带，y=深度行（×ROW_H），centerMode 下父节点居于子树带中心
  const tree2d = computeTreePositions(nodes || [], edges || [], treeCenterLayout);
  const parentOf = new Map();
  for (const e of edges || []) {
    // 归属(技术/子域→上层)与支撑(文档→模块/技术点)都向上爬，确保文档也能定位到所属领域
    if (e.edge_type === "belongs_to" || e.edge_type === "supports") parentOf.set(e.src_vid, e.dst_vid);
  }
  const domainOf = (vid) => {
    let cur = vid;
    const seen = new Set();
    while (cur && !seen.has(cur)) {
      const t = byId.get(cur)?.tag;
      if (t === "domain") return cur;
      if (!parentOf.has(cur)) return null;
      seen.add(cur);
      cur = parentOf.get(cur);
    }
    return null;
  };
  const ROW_H = 200;   // 二维树每行的垂直落差 → 3D 里即每层向下的步长
  const Z_BASE = 510;  // 领域球相对车辆的固定高度（所有领域同高，靠 Y 交错错开）
  const Y_OFF = 510;   // 领域的 Y 交错间隔
  const domains = (nodes || [])
    .filter((n) => n.tag === "domain")
    .sort((a, b) => nodeDisplayName(a).localeCompare(nodeDisplayName(b), "zh"));
  // 领域 Y 偏移：奇数留一个居中(0)，其余 ±510 交错；偶数全部 ±510 交错（不含 0）
  const ks = [];
  if (domains.length % 2 === 1) {
    for (let j = 1; j <= Math.floor(domains.length / 2); j++) ks.push(-j, j);
    ks.push(0);
  } else {
    for (let j = 1; j <= domains.length / 2; j++) ks.push(-j, j);
  }
  ks.sort((a, b) => a - b);
  const domainIdx = new Map();
  domains.forEach((d, i) => domainIdx.set(d.vid, i));
  const domainY = (vid) => {
    const i = domainIdx.get(vid);
    return i != null && ks[i] != null ? ks[i] * Y_OFF : 0;
  };
  // 领域在全局二维树里的 x（子树带中心），用于把子树以领域为轴心居中
  const centerX = new Map();
  domains.forEach((d) => centerX.set(d.vid, (tree2d[d.vid] || { x: 0 }).x || 0));

  const pos = {};
  for (const n of nodes || []) {
    if (n.tag === "vehicle") {
      pos[n.vid] = { x: 0, y: 0, z: 0 };
      continue;
    }
    const t = tree2d[n.vid] || { x: 0, y: 0 };
    if (n.tag === "domain") {
      pos[n.vid] = { x: 0, y: domainY(n.vid), z: -Z_BASE };
      continue;
    }
    const d = domainOf(n.vid);
    const x = (t.x || 0) - (d ? centerX.get(d) || 0 : 0);
    const y = d ? domainY(d) : 0; // 子树（含文档）平铺在领域自身所在的 Y 平面上
    const z = -Z_BASE - (t.y || 0);
    pos[n.vid] = { x, y, z };
  }
  // 兜底：孤立节点（不属于任何领域树）
  let fallback = 0;
  for (const n of nodes || []) {
    if (!pos[n.vid]) {
      const t = tree2d[n.vid] || { x: 0, y: 0 };
      pos[n.vid] = { x: t.x || 0, y: (fallback++) * 30, z: t.y || 0 };
    }
  }
  return pos;
}

/** 分类树（侧栏）：由 belongs_to / supports 边构建 parent -> [children] 索引。 */
function buildTreeChildren(nodes, edges) {
  const byId = new Map((nodes || []).map((n) => [n.vid, n]));
  const children = new Map();
  const add = (parent, child) => {
    if (!parent || !child || parent === child) return;
    if (!children.has(parent)) children.set(parent, []);
    if (!children.get(parent).includes(child)) children.get(parent).push(child);
  };
  for (const e of edges || []) {
    if (e.edge_type === "belongs_to") add(e.dst_vid, e.src_vid);
    if (e.edge_type === "supports") add(e.dst_vid, e.src_vid);
  }
  for (const [k, v] of children) {
    v.sort((a, b) => {
      const ta = byId.get(a)?.tag || "";
      const tb = byId.get(b)?.tag || "";
      const ra = LAYER_RANK[ta] ?? 9;
      const rb = LAYER_RANK[tb] ?? 9;
      return ra - rb || nodeDisplayName(byId.get(a) || {}).localeCompare(nodeDisplayName(byId.get(b) || {}), "zh");
    });
  }
  return { byId, children };
}

function treeNodeHTML(item) {
  const vid = item.vid;
  const kids = (classificationIndex.children?.get(vid) || []).filter(
    (c) => classificationIndex.byId?.has(c)
  );
  const open = treeExpanded.has(vid);
  const isActive = detailVid === vid;
  const name = nodeDisplayName(item);
  const inner = [];
  if (kids.length) {
    inner.push(
      `<span class="tree-caret ${open ? "open" : ""}" data-tree-caret="${escAttr(vid)}" title="${open ? "折叠" : "展开"}">${open ? "▾" : "▸"}</span>`
    );
  } else {
    inner.push('<span class="tree-caret leaf"></span>');
  }
  inner.push(
    `<span class="tree-tag" style="background:${TAG_COLOR[item.tag] || "#64748b"}">${escHtml(TAG_LABEL[item.tag] || item.tag)}</span>`
  );
  inner.push(`<span class="tree-name">${escHtml(name)}</span>`);
  if (kids.length) {
    inner.push(`<span class="tree-count">${kids.length}</span>`);
  }
  const kidsHtml = open && kids.length
    ? `<ul>${kids.map((c) => treeNodeHTML(classificationIndex.byId.get(c))).join("")}</ul>`
    : "";
  return `<li><div class="tree-row${isActive ? " active" : ""}" data-tree-vid="${escAttr(vid)}" title="${escHtml(TAG_LABEL[item.tag] || item.tag)} · ${escHtml(name)}">${inner.join("")}</div>${kidsHtml}</li>`;
}

function renderClassificationTree() {
  const el = $("treePanel");
  if (!el || !classificationIndex.byId) return;
  const byId = classificationIndex.byId;
  const hasParent = new Set();
  classificationIndex.children.forEach((kids) => kids.forEach((c) => hasParent.add(c)));
  const roots = [...byId.values()]
    .filter((n) => n.tag === "domain" || !hasParent.has(n.vid))
    .sort((a, b) => nodeDisplayName(a).localeCompare(nodeDisplayName(b), "zh"));
  const html = roots.map((r) => treeNodeHTML(r)).join("");
  el.innerHTML = `<ul class="tree">${html}</ul>`;
}

async function refreshClassificationTree() {
  const el = $("treePanel");
  if (!el) return;
  el.innerHTML = '<span class="muted">加载中…</span>';
  try {
    const data = await api("/overview?limit_nodes=1000&limit_edges=3000");
    classificationIndex = buildTreeChildren(data.nodes || [], data.edges || []);
    renderClassificationTree();
  } catch (err) {
    el.innerHTML = `<span class="muted">分类树加载失败：${escHtml(String(err.message || err))}</span>`;
  }
}

function resolveSectorKey(vid, byId, parents) {
  let cur = vid;
  const seen = new Set();
  while (cur && !seen.has(cur)) {
    seen.add(cur);
    const n = byId.get(cur);
    if (!n) break;
    if (n.tag === "subdomain") return cur;
    if (n.tag === "domain") return "__domain__";
    const ps = parents.get(cur) || [];
    cur =
      ps.find((p) => byId.get(p)?.tag === "subdomain") ||
      ps.find((p) => byId.get(p)?.tag === "module") ||
      ps.find((p) => byId.get(p)?.tag === "technology") ||
      ps[0];
  }
  return "__orphan__";
}

function placeInSector(list, radius, a0, a1) {
  const pos = {};
  const n = list.length;
  if (!n) return pos;
  const pad = Math.min(0.2, (a1 - a0) * 0.22);
  list.forEach((node, i) => {
    const t = n === 1 ? 0.5 : i / (n - 1);
    const angle = a0 + pad + (a1 - a0 - 2 * pad) * t - Math.PI / 2;
    pos[node.vid] = {
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
    };
  });
  return pos;
}

/** 同心圆（太阳系式）：车辆在最中心；领域在车辆外圈环形布置；
 * 每个领域球又作为它自己子体系的圆心——子域/模块/技术点/文档都以该领域为圆心环形布置，
 * 不同领域的同级节点不再绕车辆转圈，而是各回各领域中心。单领域视图行为一致。 */
function computeRadialPositions(nodes, edges) {
  const { byId, parents } = buildParentIndex(nodes, edges);
  const vehicles = [];
  const domains = [];
  const subs = [];
  const mods = [];
  const techs = [];
  const mats = [];
  for (const n of nodes || []) {
    if (n.tag === "vehicle") vehicles.push(n);
    else if (n.tag === "domain") domains.push(n);
    else if (n.tag === "subdomain") subs.push(n);
    else if (n.tag === "module") mods.push(n);
    else if (n.tag === "technology") techs.push(n);
    else if (n.tag === "material") mats.push(n);
  }
  const sortZh = (arr) =>
    arr.sort((a, b) => nodeDisplayName(a).localeCompare(nodeDisplayName(b), "zh"));
  sortZh(vehicles);
  sortZh(domains);
  sortZh(subs);
  sortZh(mods);
  sortZh(techs);
  sortZh(mats);

  const domainOf = (vid) => {
    let cur = vid;
    const seen = new Set();
    while (cur && !seen.has(cur)) {
      const t = byId.get(cur)?.tag;
      if (t === "domain") return cur;
      const ps = parents.get(cur) || [];
      if (!ps.length) return null;
      seen.add(cur);
      cur = ps[0];
    }
    return null;
  };

  const pos = {};
  vehicles.forEach((n) => {
    pos[n.vid] = { x: 0, y: 0 };
  });

  // 领域环形布置在车辆外圈（半径足够容纳各自子体系）
  const N = Math.max(domains.length, 1);
  const RD = Math.max(560, 260 + N * 250);
  const domainsBy = new Map(); // domainVid -> { cx, cy }
  domains.forEach((d, i) => {
    const ang = (2 * Math.PI * i) / N;
    const cx = Math.cos(ang) * RD;
    const cy = Math.sin(ang) * RD;
    domainsBy.set(d.vid, { cx, cy });
    pos[d.vid] = { x: cx, y: cy };
  });

  // 局部环半径：围绕领域球的本体系
  const LR1 = 150; // 子域
  const LR2 = 270; // 模块
  const LR3 = 420; // 技术点
  const LR4 = 560; // 文档

  // 每个领域本体系子域的角带（全 360° 均匀划分）
  const domainSubs = new Map(); // domainVid -> [subs]
  for (const s of subs) {
    const d = domainOf(s.vid) || "__none__";
    if (!domainSubs.has(d)) domainSubs.set(d, []);
    domainSubs.get(d).push(s);
  }
  const bandOf = new Map(); // subdomainVid -> {a0,a1,mid}
  for (const [d, list] of domainSubs) {
    const n = list.length;
    list.forEach((s, j) => {
      const a0 = (2 * Math.PI * j) / n;
      const a1 = (2 * Math.PI * (j + 1)) / n;
      bandOf.set(s.vid, { a0, a1, mid: (a0 + a1) / 2 });
      const ang = (a0 + a1) / 2 - Math.PI / 2;
      const c = domainsBy.get(d);
      if (c) {
        pos[s.vid] = {
          x: c.cx + Math.cos(ang) * LR1,
          y: c.cy + Math.sin(ang) * LR1,
        };
      }
    });
  }
  const fullBand = { a0: 0, a1: 2 * Math.PI, mid: Math.PI };

  const placeLocal = (list, radius, resolveKey) => {
    const groups = new Map(); // key -> { d, band, items }
    for (const node of list) {
      const k = resolveKey(node);
      const d = domainOf(node.vid);
      let band;
      let key;
      if (d && k !== "__domain__" && k !== "__orphan__" && bandOf.has(k)) {
        band = bandOf.get(k);
        key = d + ":" + k;
      } else if (d) {
        band = fullBand;
        key = d + ":__dom__";
      } else {
        band = fullBand;
        key = "__orphan__";
      }
      if (!groups.has(key)) groups.set(key, { d, band, items: [] });
      groups.get(key).items.push(node);
    }
    for (const { d, band, items } of groups.values()) {
      sortZh(items);
      const c = domainsBy.get(d);
      if (!c) {
        // 无领域的孤儿：放在车辆外圈更远处
        const base = 1050 + radius * 0.9;
        Object.assign(pos, placeInSector(items, base, band.a0, band.a1));
      } else {
        // 以父（子域）为中心收窄：内容越少越聚在父球方向（下属贴在上方节点下方），
        // 但绝不越出子域自己的扇区；内容多时自然展开填满扇区
        let a0 = band.a0;
        let a1 = band.a1;
        const n = items.length;
        if (band !== fullBand) {
          const mid = band.mid;
          const bw = band.a1 - band.a0;
          const spread = Math.min(0.5, 0.14 + 0.055 * n); // rad
          const half = Math.min(spread, bw * 0.5 - 1e-6);
          a0 = mid - half;
          a1 = mid + half;
        }
        const local = placeInSector(items, radius, a0, a1);
        for (const vid of Object.keys(local)) {
          pos[vid] = { x: c.cx + local[vid].x, y: c.cy + local[vid].y };
        }
      }
    }
  };

  placeLocal(subs, LR1, (s) => s.vid);
  placeLocal(mods, LR2, (m) => resolveSectorKey(m.vid, byId, parents));
  placeLocal(techs, LR3, (t) => resolveSectorKey(t.vid, byId, parents));
  placeLocal(mats, LR4, (m) => {
    const k = resolveSectorKey(m.vid, byId, parents);
    if (k === "__domain__") {
      const ps = parents.get(m.vid) || [];
      const mid = ps.find((p) => byId.get(p)?.tag === "technology") || ps.find((p) => byId.get(p)?.tag === "module");
      if (mid) return resolveSectorKey(mid, byId, parents);
    }
    return k;
  });

  // 兜底：仍未放置的节点（如环）追加在外圈
  let orphanCursor = 0;
  for (const n of nodes || []) {
    if (!pos[n.vid]) {
      const ang = (orphanCursor++ * 0.618033988749895) * 2 * Math.PI;
      pos[n.vid] = { x: Math.cos(ang) * 1250, y: Math.sin(ang) * 1250 };
    }
  }
  return pos;
}

function applyNodeSelection(vid) {
  if (vid) detailEdge = null;
  detailVid = vid || detailVid;
  applyGraphSelection();
}

function drawGraph(data, centerVid) {
  const view = filterGraphPayload(data);
  lastGraphPayload = { data, centerVid, view };
  updateCanvasBudgetBadge(view);
  const nodeCount = (view.nodes || []).length;
  if (!nodeCount) {
    setGraphHint(
      overviewMode
        ? "当前筛选下无节点，试试调整层级或关掉「只看选中」"
        : "该节点暂无子图数据",
      false
    );
    return;
  }
  if (lastCanvasTruncated) {
    setGraphHint(
      `图元较多，已按 Nebula Explorer 建议做截断展示（2D 建议 ≤${CANVAS_HARD_LIMIT}）`,
      false
    );
  } else {
    setGraphHint("");
  }
  if (viewMode === "3d") {
    drawGraph3d(view, centerVid);
  } else {
    drawGraph2d(view, centerVid);
  }
}

function redrawCurrentGraph() {
  if (!lastGraphPayload?.data) return;
  drawGraph(lastGraphPayload.data, lastGraphPayload.centerVid);
  const center = (lastGraphPayload.view?.nodes || []).find((n) => n.vid === focusVid);
  updateFocusMetaAfterDraw(center || null);
}

function drawGraph2d(data, centerVid) {
  if (typeof vis === "undefined" || !vis.Network) {
    setGraphHint("图引擎未加载。请强制刷新页面（Ctrl+F5）", true);
    return;
  }
  setGraphHint("");
  updateGraphLegend();

  const edgeSel = detailEdge;
  const selectedVid = edgeSel ? null : detailVid || centerVid || focusVid || null;
  const neigh = edgeSel
    ? new Set([edgeSel.src_vid, edgeSel.dst_vid])
    : selectedVid
      ? neighborSet(selectedVid, data.edges || [])
      : null;
  // 树状/同心圆坐标都只是初始种子坐标——物理关闭，节点可自由上下左右拖动，不做行列约束
  // 同心圆/力导向：领域围绕车辆向外拉开作为种子（力导向物理开启前也用它避免开局拥挤）
  const radial =
    layoutMode === "radial" || layoutMode === "force"
      ? computeRadialPositions(data.nodes || [], data.edges || [])
      : null;
  const treePos = layoutMode === "tree"
    ? computeTreePositions(data.nodes || [], data.edges || [], treeCenterLayout)
    : null;
  const degrees = weightByDegree ? computeDegrees(data.edges || []) : null;
  const isTree = layoutMode === "tree";
  const lightTheme = isLightTheme();
  // 树状模式：层级边反向成「父→子」用于布局辅助（种子坐标已含层级关系）
  const displayEdges = isTree ? treeEdgesFor(data.edges || []) : data.edges || [];

  let savedView = null;
  let savedPositions = null;
  if (network && !forceFitNext) {
    try {
      savedView = {
        scale: network.getScale(),
        position: network.getViewPosition(),
      };
      savedPositions = network.getPositions();
    } catch (_) {
      savedView = null;
      savedPositions = null;
    }
  }

  const nodes = new vis.DataSet(
    (data.nodes || []).map((n) => {
      const nm = nodeDisplayName(n);
      const base = TAG_COLOR[n.tag] || "#64748b";
      const showLabel = shouldShow3dDefaultLabel(n); // 标注分级：仅勾选层显示（二维复用）
      const labelText = showLabel ? breakLabel(nm) : "";
      const isSel = edgeSel
        ? n.vid === edgeSel.src_vid || n.vid === edgeSel.dst_vid
        : !!(selectedVid && n.vid === selectedVid);
      const isNear = !neigh || neigh.has(n.vid);
      const isSearchHit = highlightSearch && searchResultVids.has(n.vid);
      const isReview = reviewHighlightOn && reviewVids.has(n.vid);
      const highlightBorder = isSearchHit ? "#22d3ee" : "#fde68a";
      const dimFilter = (highlightSearch && !isSearchHit) || (reviewHighlightOn && !isReview && !isNear); // 高亮开启时，未命中节点变暗
      const sizeBase = NODE_SIZE[n.tag] || 12;
      const deg = degrees?.get(n.vid) || 0;
      const degBoost = weightByDegree ? Math.min(14, deg * 1.15) : 0;
      const mass = nodePhysicsMass(n, deg);
      const kept = savedPositions?.[n.vid];
      const seed = isTree ? treePos?.get?.(n.vid) || treePos?.[n.vid] : radial?.[n.vid];
      // 仅作初始种子，物理关闭 → 之后可自由拖动到任意位置（拖动结果在重绘时自动保留）
      const xy = kept || seed || null;
      // 节点最终尺寸（含选中/搜索/审阅加粗与度加权），保持不变
      const sizeFinal =
        (isSel ? sizeBase + 8 : isSearchHit ? sizeBase + 6 : isReview ? sizeBase + 5 : sizeBase) + degBoost;
      const fontSize = isSel ? 16 : n.tag === "vehicle" ? 16 : n.tag === "domain" ? 15 : n.tag === "module" ? 12 : 11;
      const labelLines = labelText ? labelText.split("\n").length : 0;
      // 二维同心圆：把标签从节点下方上移到圆心（不改 shape/size，靠字体垂直偏移）
      const centerLabel = layoutMode === "radial" && !!labelText;
      const labelVadjust = centerLabel
        ? -(sizeFinal + (labelLines * fontSize * 1.15) / 2 + 4)
        : 0;
      return {
        id: n.vid,
        label: labelText,
        color: {
          background: isReview ? REVIEW_HL : base,
          border: isReview ? "#67e8f9" : isSel ? "#fde68a" : isSearchHit ? "#22d3ee" : isNear ? "#0f172a" : "#334155",
          highlight: { background: isReview ? REVIEW_HL : base, border: highlightBorder },
          hover: { background: isReview ? REVIEW_HL : base, border: "#fbbf24" },
        },
        font: {
          color: centerLabel ? "#ffffff" : lightTheme ? "#1f2937" : isNear ? "#e2e8f0" : "#64748b",
          face: "Segoe UI",
          size: fontSize,
          strokeWidth: 3,
          strokeColor: centerLabel ? "#0b1220" : lightTheme ? "#ffffff" : "#0b1220",
          align: "middle",
          // 同心圆压在彩色圆上的标签：两主题都白字深描边、不要底矩形
          background: centerLabel ? "rgba(0,0,0,0)" : "rgba(11,18,32,0.55)",
          ...(centerLabel ? { vadjust: labelVadjust } : {}),
        },
        borderWidth: isReview ? 4 : isSel ? 4 : isSearchHit ? 4 : isNear ? 2 : 1,
        opacity: dimFilter ? 0.18 : isReview ? 1 : isNear ? 1 : 0.22,
        shape: "dot",
        size: sizeFinal,
        // vis Barnes-Hut: repulsion ∝ mass_i * mass_j — hubs shove neighbors out
        mass,
        title: (() => {
          const full = n.props?.title && n.props.title !== nm ? `\n${n.props.title}` : "";
          return `${nm}\n${TAG_LABEL[n.tag] || n.tag}${full}\n关联度 ${deg} · 质量 ${mass.toFixed(1)}`;
        })(),
        ...(xy ? { x: xy.x, y: xy.y } : {}),
        fixed: false,
      };
    })
  );

  const edges = new vis.DataSet(
    displayEdges.map((e) => {
      const id = edgeKey(e);
      const isEdgeSel = !!(edgeSel && edgeSel.id === id);
      const near = edgeSel
        ? isEdgeSel || (neigh && (neigh.has(e.src_vid) || neigh.has(e.dst_vid)))
        : !neigh || neigh.has(e.src_vid) || neigh.has(e.dst_vid);
      const col = isEdgeSel ? "#f59e0b" : EDGE_COLOR[e.edge_type] || "#64748b";
      const hot =
        isEdgeSel ||
        (selectedVid && (e.src_vid === selectedVid || e.dst_vid === selectedVid));
      const count = e.count || 1;
      const isReviewEdge = reviewHighlightOn && reviewEdgeKeys.has(id);
      let label = REL_LABEL[e.edge_type] || (e.edge_type === "relates_to" ? "关联" : "");
      if (count > 1) {
        label = label ? `${label}×${count}` : `×${count}`;
      }
      return {
        id,
        from: e.src_vid,
        to: e.dst_vid,
        label: isEdgeSel || hot ? label : e.edge_type === "relates_to" || count > 1 ? label : "",
        arrows: { to: { enabled: true, scaleFactor: isEdgeSel ? 1 : 0.7 } },
        color: {
          color: isReviewEdge ? REVIEW_HL : near || isEdgeSel ? col : lightTheme ? "#cbd5e1" : "#1e293b",
          highlight: "#f59e0b",
          opacity: isEdgeSel ? 1 : isReviewEdge ? 1 : near ? 0.85 : 0.12,
        },
        width: isReviewEdge ? 3 : (isEdgeSel ? 4.2 : hot ? 2.4 : 1) + (count > 1 ? Math.min(3, count * 0.35) : 0),
        // longer springs around hubs so leaves (materials) get pushed farther
        length: layoutMode === "force" ? edgeSpringLength(e, degrees) : undefined,
        font: {
          color: isEdgeSel ? (lightTheme ? "#b45309" : "#fde68a") : lightTheme ? "#475569" : "#94a3b8",
          size: isEdgeSel ? 12 : 10,
          strokeWidth: 0,
          face: "Segoe UI",
        },
        smooth: layoutMode === "radial" || isTree ? false : { type: "continuous" },
        title: `${REL_LABEL[e.edge_type] || e.edge_type}${count > 1 ? ` · 聚合 ${count} 条` : ""} · 点击查看`,
      };
    })
  );

  const container = $("network");

  const runPhysics = layoutMode === "force" && (forceFitNext || !savedPositions);
  const options = {
    autoResize: true,
    // 树状/同心圆：关闭物理，仅给初始种子坐标 → 节点可完全自由上下左右拖动，无行列约束
    physics: layoutMode === "radial" || isTree ? false : runPhysics ? forcePhysicsOptions() : false,
    layout: { hierarchical: { enabled: false } },
    edges: {
      selectionWidth: 8,
      hoverWidth: 3,
    },
    interaction: {
      hover: true,
      tooltipDelay: 80,
      zoomView: true,
      dragView: true,
      dragNodes: true,
      selectConnectedEdges: false,
      keyboard: { enabled: true, bindToWindow: false },
      multiselect: false,
      navigationButtons: false,
    },
  };

  if (!network) {
    network = new vis.Network(container, { nodes, edges }, options);
    network.on("stabilizationIterationsDone", () => {
      try {
        network.setOptions({ physics: false });
      } catch (_) {
        /* ignore */
      }
      // Fit only after physics settled — early fit captures a collapsed bbox and looks tiny
      if (forceFitNext) {
        forceFitNext = false;
        requestAnimationFrame(() => {
          resizeGraphViewport();
          network.fit({ animation: false, padding: 56 });
        });
      }
    });
    network.on("click", (params) => {
      const vid = params.nodes?.[0];
      const eid = params.edges?.[0];
      if (vid) {
        openDetail(vid, { focusGraph: false }).catch(alertError);
        return;
      }
      if (eid) {
        const [src_vid, edge_type, dst_vid] = String(eid).split("|");
        const raw = (lastGraphPayload?.view?.edges || lastGraphPayload?.data?.edges || []).find(
          (e) => edgeKey(e) === eid
        );
        openEdgeDetail(
          raw || {
            id: eid,
            src_vid,
            dst_vid,
            edge_type: edge_type || "other",
            count: 1,
          }
        ).catch(alertError);
        return;
      }
      detailVid = null;
      detailEdge = null;
      syncDrawerActionLabels();
      redrawCurrentGraph();
    });
    const refit = () => resizeGraphViewport();
    window.addEventListener("resize", refit);
    if (typeof ResizeObserver !== "undefined") {
      networkResizeObs = new ResizeObserver(() => refit());
      networkResizeObs.observe(container);
      const stage = document.querySelector(".graph-stage");
      if (stage) networkResizeObs.observe(stage);
    }
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) setTimeout(refit, 50);
    });
  } else {
    network.setOptions(options);
    network.setData({ nodes, edges });
  }

  requestAnimationFrame(() => {
    resizeGraphViewport();
    network.redraw();
    if (runPhysics) {
      // physics path: fit on stabilizationIterationsDone
      if (!forceFitNext && savedView) {
        try {
          network.moveTo({
            position: savedView.position,
            scale: savedView.scale,
            animation: false,
          });
        } catch (_) {
          /* ignore */
        }
      } else if (forceFitNext) {
        // Fallback if stabilize event is skipped (e.g. tiny graphs)
        setTimeout(() => {
          if (!forceFitNext || viewMode !== "2d" || !network) return;
          forceFitNext = false;
          try {
            network.setOptions({ physics: false });
          } catch (_) {
            /* ignore */
          }
          resizeGraphViewport();
          network.fit({ animation: false, padding: 56 });
        }, 900);
      }
    } else if (forceFitNext || !savedView) {
      network.fit({ animation: false, padding: 56 });
      forceFitNext = false;
    } else {
      try {
        network.moveTo({
          position: savedView.position,
          scale: savedView.scale,
          animation: false,
        });
      } catch (_) {
        /* ignore */
      }
    }
    applyGraphSelection();
  });
}

function shouldShow3dDefaultLabel(n) {
  return !!(label3dEnabled && n?.tag && label3dTags.has(n.tag));
}

function refresh3dLabels() {
  clear3dHtmlLabels();
  sync3dHtmlLabels();
}

/** 按当前标注分级刷新：二维重绘节点标注，三维重绘浮动标注。 */
function refreshLabels() {
  if (viewMode === "3d") {
    refresh3dLabels();
  } else if (lastGraphPayload?.data) {
    redrawCurrentGraph();
  }
}

function shorten3dLabel(text, tag) {
  const s = String(text || "").replace(/\s+/g, " ").trim();
  const max = tag === "domain" ? 14 : tag === "subdomain" ? 12 : 10;
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1)}…`;
}

function ensure3dLabelLayer() {
  const host = $("network3d");
  if (!host) return null;
  let layer = host.querySelector(".graph3d-labels");
  if (!layer) {
    layer = document.createElement("div");
    layer.className = "graph3d-labels";
    layer.setAttribute("aria-hidden", "true");
    host.appendChild(layer);
  }
  return layer;
}

function clear3dHtmlLabels() {
  $("network3d")?.querySelector(".graph3d-labels")?.replaceChildren();
}

function sync3dHtmlLabels() {
  if (!graph3d || viewMode !== "3d") return;
  if (typeof graph3d.graph2ScreenCoords !== "function") return;
  const layer = ensure3dLabelLayer();
  if (!layer) return;
  if (!label3dEnabled || label3dTags.size === 0) {
    layer.replaceChildren();
    return;
  }
  const nodes = graph3d.graphData?.().nodes || [];
  const keep = new Set();
  for (const n of nodes) {
    if (!shouldShow3dDefaultLabel(n) || n.x == null || n.y == null || n.z == null) continue;
    keep.add(n.id);
    let el = layer.querySelector(`[data-vid="${CSS.escape(String(n.id))}"]`);
    if (!el) {
      el = document.createElement("div");
      el.className = `graph3d-label tag-${n.tag || "other"}`;
      el.dataset.vid = n.id;
      el.textContent = shorten3dLabel(n.name || n.id, n.tag);
      layer.appendChild(el);
    }
    const p = graph3d.graph2ScreenCoords(n.x, n.y, n.z);
    if (!p || !Number.isFinite(p.x) || !Number.isFinite(p.y)) {
      el.style.visibility = "hidden";
      continue;
    }
    el.style.visibility = "visible";
    // Label sits centered on its sphere (anchored at the sphere center), offset up by one line
    el.style.transform = `translate(${p.x}px, ${p.y}px) translate(-50%, -115%)`;
  }
  for (const el of [...layer.children]) {
    if (!keep.has(el.dataset.vid)) el.remove();
  }
}

function destroyGraph3d() {
  if (!graph3d) return;
  try {
    graph3d.controls?.()?.removeEventListener?.("change", sync3dHtmlLabels);
  } catch (_) {
    /* ignore */
  }
  try {
    graph3d._destructor?.();
  } catch (_) {
    /* ignore */
  }
  try {
    graph3d.pauseAnimation?.();
  } catch (_) {
    /* ignore */
  }
  const el = $("network3d");
  if (el) el.innerHTML = "";
  graph3d = null;
}

function drawGraph3d(data, centerVid) {
  const ForceGraph3D = window.ForceGraph3D;
  if (typeof ForceGraph3D !== "function") {
    setGraphHint("3D 图引擎未加载。请强制刷新（Ctrl+F5）", true);
    viewMode = "2d";
    $("network").hidden = false;
    $("network3d").hidden = true;
    syncViewControls();
    return;
  }
  setGraphHint("");
  const el = $("network3d");
  if (el.hidden) el.hidden = false;
  const box = el.getBoundingClientRect();
  const w = Math.max(40, Math.floor(box.width || el.clientWidth || 800));
  const h = Math.max(40, Math.floor(box.height || el.clientHeight || 500));
  // Recreate if previous instance was born at 0×0 (common after hidden→shown)
  if (graph3d && (w < 40 || h < 40)) {
    destroyGraph3d();
  }

  const deg3 = computeDegrees(data.edges || []);
  const selVid3 = detailVid || focusVid || centerVid || null;
  const isTree3 = layoutMode === "tree";
  const srcEdges3 = isTree3 ? treeEdgesFor(data.edges || []) : data.edges || [];
  // 三维树状：分层=领域球沿 -Z 堆叠、各自子树向下居中树状展开（pos 自带 z）；
  // 环形=不同领域有高度差、每个领域子树在其水平面内围绕领域球环形铺开（x,y + 领域平面 z）
  const tree3dInfo = isTree3
    ? tree3dMode === "layer"
      ? { pos: computeTree3DDown(data.nodes || [], data.edges || []), z: null, level: null }
      : {
          pos: computeTreePlaneXY(data.nodes || [], data.edges || []),
          z: computeTreePlaneZ(data.nodes || [], data.edges || []),
          level: null,
        }
    : null;
  const TAG_Z = { vehicle: 0, domain: 1, subdomain: 2, module: 3, technology: 4, material: 5 };
  const Z_DIST = 150;
  // 3D 非树状（同心圆/力导向）：用领域外拉的径向坐标做初始种子（随后力导向再推演），避免开局挤成一团
  const radial3dSeed = isTree3
    ? null
    : computeRadialPositions(data.nodes || [], data.edges || []);
  const gData = {
    nodes: (data.nodes || []).map((n) => {
      const deg = deg3.get(n.vid) || 0;
      // Keep vals modest — nodeRelSize default makes large val fill the screen
      const baseVal =
        n.tag === "vehicle" ? 10
        : n.tag === "domain" ? 8
        : n.tag === "subdomain" ? 5
        : n.tag === "module" ? 4.2
        : n.tag === "material" ? 2
        : 3.5;
      const isSel = !!n.vid && n.vid === selVid3;
      const isSearchHit = highlightSearch && searchResultVids.has(n.vid);
      const isReviewHit = reviewHighlightOn && reviewVids.has(n.vid);
      let color = TAG_COLOR[n.tag] || "#64748b";
      if (isSel) color = "#f59e0b"; // 选中高亮（琥珀）
      else if (isReviewHit) color = REVIEW_HL; // 校核改动高亮（青）
      else if (isSearchHit) color = "#22d3ee"; // 查找命中高亮（青）
      let val = (isSel ? baseVal + 3 : baseVal) + Math.min(4, deg * 0.25);
      if (isSearchHit || isReviewHit) val += 2;
      const seed3 = !isTree3 && radial3dSeed ? radial3dSeed[n.vid] : null;
      return {
        id: n.vid,
        name: nodeDisplayName(n),
        tag: n.tag,
        chargeWeight: nodePhysicsMass(n, deg),
        val,
        color,
        ...(isTree3 && tree3dInfo
          ? (() => {
              const p = tree3dInfo.pos[n.vid] || { x: 0, y: 0, z: 0 };
              const z =
                tree3dInfo.z != null
                  ? (tree3dInfo.z.get(n.vid) ?? -(TAG_Z[n.tag] ?? 2) * Z_DIST)
                  : (Number.isFinite(p.z) ? p.z : -(TAG_Z[n.tag] ?? 2) * Z_DIST);
              return { x: p.x, y: p.y, z, fx: p.x, fy: p.y, fz: z };
            })()
          : {}),
        ...(seed3 ? { x: seed3.x, y: seed3.y } : {}),
      };
    }),
    links: srcEdges3.map((e) => {
      const id = edgeKey(e);
      const hot = detailEdge && detailEdge.id === id;
      return {
        id,
        source: e.src_vid,
        target: e.dst_vid,
        type: e.edge_type,
        count: e.count || 1,
        distance: Math.max(22, edgeSpringLength(e, deg3) * 0.32),
        color: hot ? "#f59e0b" : "#94a3b8",
        width: hot ? 2.4 : 0.9,
      };
    }),
  };

  if (!graph3d) {
    graph3d = ForceGraph3D()(el)
      .backgroundColor("#0b0f14")
      .showNavInfo(false)
      .nodeId("id")
      .nodeLabel((n) => `${n.name || n.id}\n${TAG_LABEL[n.tag] || n.tag}`)
      .nodeColor((n) => n.color)
      .nodeVal((n) => n.val)
      .nodeOpacity(0.92)
      .nodeRelSize(3.6)
      .linkColor((l) => l.color || "#94a3b8")
      .linkOpacity(0.65)
      .linkDirectionalArrowLength(3.5)
      .linkDirectionalArrowRelPos(1)
      .linkWidth((l) => l.width || 0.9)
      .linkLabel((l) => REL_LABEL[l.type] || l.type || "")
      .warmupTicks(60)
      .cooldownTicks(120)
      .onNodeClick((n) => {
        if (n?.id) openDetail(n.id, { focusGraph: false }).catch(alertError);
      })
      .onLinkClick((l) => {
        const src = typeof l.source === "object" ? l.source.id : l.source;
        const dst = typeof l.target === "object" ? l.target.id : l.target;
        openEdgeDetail({
          id: l.id || `${src}|${l.type}|${dst}`,
          src_vid: src,
          dst_vid: dst,
          edge_type: l.type || "other",
          count: l.count || 1,
        }).catch(alertError);
      })
      .onEngineTick(() => {
        syncGraph3dPositions();
        sync3dHtmlLabels();
      })
      .onEngineStop(() => {
        syncGraph3dPositions();
        sync3dHtmlLabels();
        if (viewMode === "3d") focusGraph3dCamera(centerVid);
      });
    try {
      graph3d.controls?.()?.addEventListener?.("change", sync3dHtmlLabels);
    } catch (_) {
      /* ignore */
    }
  } else {
    clear3dHtmlLabels();
  }

  // 三维树状：不再用 dag 自动分层，改用「按标签定层高 + 钉住坐标」的静态分层树（同标签同高度）
  try {
    graph3d.dagMode(null);
  } catch (_) {
    /* ignore */
  }

  try {
    const linkF = graph3d.d3Force("link");
    if (linkF && typeof linkF.distance === "function") {
      linkF.distance((l) => l.distance || (isTree3 ? 48 : 32));
    }
    const chg = graph3d.d3Force("charge");
    if (chg && typeof chg.strength === "function") {
      chg.strength(isTree3 ? -14 : -30);
    }
    const cent = graph3d.d3Force("center");
    if (cent && typeof cent.strength === "function") {
      cent.strength(isTree3 ? 0.35 : 1);
    }
  } catch (_) {
    /* ignore */
  }

  graph3d.width(w).height(h);
  try { graph3d.backgroundColor(isLightTheme() ? "#f7f9fc" : "#0b0f14"); } catch (_) {}
  try {
    graph3d.graphData(gData);
    graph3d.resumeAnimation?.();
  } catch (err) {
    setGraphHint(`三维渲染失败：${err.message || err}`, true);
    return;
  }
  // Safety: engine/warmup may finish before meshes exist; sync for a short window
  let syncFrames = 0;
  const pump = () => {
    if (viewMode !== "3d" || !graph3d) return;
    syncGraph3dPositions();
    sync3dHtmlLabels();
    syncFrames += 1;
    if (syncFrames === 2 || syncFrames === 20 || syncFrames === 45) {
      focusGraph3dCamera(centerVid);
    }
    if (syncFrames < 90) requestAnimationFrame(pump);
  };
  requestAnimationFrame(pump);
}

function breakLabel(text) {
  const s = String(text || "");
  if (s.length <= 8) return s;
  return s.slice(0, 8) + "\n" + s.slice(8, 16);
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** 「添加节点」表单：各层级的可选上节点/下节点标签池（链接时按此顺序精确匹配名称）。 */
const ADD_PARENT_TAGS = {
  domain: ["vehicle"],
  subdomain: ["domain"],
  module: ["subdomain"],
  technology: ["module", "subdomain"], // 兼容旧结构允许直接挂子域
  material: ["technology", "module"],
};
const ADD_CHILD_TAGS = {
  domain: ["subdomain"],
  subdomain: ["module"],
  module: ["technology"],
  technology: ["material"],
  material: [],
};

/** 固定 6 层架构（来自 /meta/schema），表单的层级/上下节点选项统一读它。 */
let ARCH_SCHEMA = null;

async function loadArchSchema() {
  try {
    ARCH_SCHEMA = await api("/meta/schema");
  } catch (_) {
    ARCH_SCHEMA = null;
  }
  applyArchToAddForm();
}

function applyArchToAddForm() {
  const a = ARCH_SCHEMA && ARCH_SCHEMA.architecture;
  if (!a) return;
  const bParent = a.belongs_to_parent || {};
  const bChildren = a.belongs_to_children || {};
  const supports = a.supports_targets || [];
  const levels = a.levels || [];
  for (const level of levels) {
    ADD_PARENT_TAGS[level] =
      level === "material" ? supports.slice() : (bParent[level] || []).slice();
  }
  for (const level of levels) {
    if (level === "material") {
      ADD_CHILD_TAGS[level] = [];
      continue;
    }
    const kids = (bChildren[level] || []).slice();
    if (supports.includes(level) && !kids.includes("material")) kids.push("material");
    ADD_CHILD_TAGS[level] = kids;
  }
  const sel = $("addLevel");
  if (sel) {
    const labels = a.level_label || {};
    const cur = sel.value;
    // 不含 vehicle 根，避免误建多个根节点
    sel.innerHTML = levels
      .filter((l) => l !== "vehicle")
      .map((l) => `<option value="${l}"${l === cur ? " selected" : ""}>${escapeHtml(labels[l] || l)}</option>`)
      .join("");
  }
  syncAddNodeFields();
}

// ========== 导出知识架构（自定义起点/终点） ==========
const EXPORT_LAYER_ORDER = ["vehicle", "domain", "subdomain", "module", "technology", "material"];

function renderExportNodeList() {
  const el = $("exportNodeList");
  if (!el) return;
  el.innerHTML = Object.keys(pathNodeIndex)
    .sort((a, b) => a.localeCompare(b, "zh"))
    .map((n) => `<option value="${escapeHtml(n)}"></option>`)
    .join("");
}

function exportNodeByName(name) {
  const vid = pathNodeIndex[name];
  if (!vid) return null;
  for (const tag of Object.keys(addPool)) {
    const hit = (addPool[tag] || []).find((x) => x.vid === vid);
    if (hit) return { vid, tag: hit.tag, name: hit.name };
  }
  return { vid, tag: "", name };
}

function syncExportEndMode() {
  const mode = $("exportEndMode")?.value || "level";
  const levelRow = $("exportToLevel");
  const nodeInput = $("exportEndNode");
  if (mode === "node") {
    if (levelRow) levelRow.style.display = "none";
    if (nodeInput) nodeInput.hidden = false;
    if (nodeInput) nodeInput.style.display = "";
  } else {
    if (levelRow) levelRow.style.display = "";
    if (nodeInput) nodeInput.hidden = true;
  }
  syncExportMeta();
}

function rebuildExportToLevel(startTag) {
  const sel = $("exportToLevel");
  if (!sel) return;
  const sRank = EXPORT_LAYER_ORDER.indexOf(startTag);
  const candidates = EXPORT_LAYER_ORDER.filter((l) => {
    const r = EXPORT_LAYER_ORDER.indexOf(l);
    return r < 6 && r > sRank;
  });
  if (startTag === "material") {
    sel.innerHTML = `<option value="material" disabled>起点为文档（无下层）</option>`;
    sel.disabled = true;
    return;
  }
  sel.disabled = false;
  const defaultTo = candidates.includes("material") ? "material" : candidates[candidates.length - 1];
  sel.innerHTML = candidates
    .map((l) => `<option value="${l}"${l === defaultTo ? " selected" : ""}>${TAG_LABEL[l] || l}</option>`)
    .join("");
}

function syncExportMeta() {
  const meta = $("exportMeta");
  if (!meta) return;
  const start = exportNodeByName(($("exportStart")?.value || "").trim());
  const mode = $("exportEndMode")?.value || "level";
  let to = "";
  if (start) {
    to =
      mode === "node"
        ? (() => {
            const e = exportNodeByName(($("exportEndNode")?.value || "").trim());
            return e ? e.tag : "";
          })()
        : $("exportToLevel")?.value || "";
  }
  meta.textContent = start
    ? `将导出：${start.name || start.vid}（${start.tag || "?"}）→ ${to || "(未选终点层级)"}`
    : "";
  meta.hidden = !start;
}

async function exportKnowledge() {
  const msg = $("exportMsg");
  const fmt = $("exportFormat")?.value || "json";
  msg.hidden = false;
  msg.className = "msg";

  const start = exportNodeByName(($("exportStart")?.value || "").trim());
  if (!start || !start.vid) {
    msg.className = "msg err";
    msg.textContent = "请先选择有效的起点节点（名称需与图谱一致）";
    return;
  }
  const sRank = EXPORT_LAYER_ORDER.indexOf(start.tag);
  if (sRank < 0) {
    msg.className = "msg err";
    msg.textContent = "无法识别起点的所属层级，请从下拉候选中选择";
    return;
  }

  const mode = $("exportEndMode")?.value || "level";
  let toTag = "";
  if (mode === "node") {
    const end = exportNodeByName(($("exportEndNode")?.value || "").trim());
    if (!end || !end.vid) {
      msg.className = "msg err";
      msg.textContent = "请选择有效的终点节点（名称需与图谱一致）";
      return;
    }
    toTag = end.tag;
  } else {
    toTag = $("exportToLevel")?.value || "";
  }
  if (!toTag) {
    msg.className = "msg err";
    msg.textContent = "请选择导出终点（层级或终点节点）";
    return;
  }
  if (EXPORT_LAYER_ORDER.indexOf(toTag) < sRank) {
    msg.className = "msg err";
    msg.textContent = `终点层级(${TAG_LABEL[toTag] || toTag})不能高于起点层级(${TAG_LABEL[start.tag] || start.tag})`;
    return;
  }

  msg.textContent = "导出中…";
  try {
    const url =
      `/export/knowledge?root=${encodeURIComponent(start.vid)}&from_level=${start.tag}&to_level=${toTag}&fmt=${encodeURIComponent(fmt)}`;
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || `导出失败（HTTP ${res.status}）`);
    }
    const raw = await res.text();
    const text = fmt === "md" ? raw : JSON.stringify(JSON.parse(raw), null, 2);
    const blob = new Blob([text], { type: fmt === "md" ? "text/markdown;charset=utf-8" : "application/json;charset=utf-8" });
    const a = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 10);
    a.download = `knowledge_${start.vid}_${start.tag}_${toTag}_${stamp}.${fmt}`;
    a.href = URL.createObjectURL(blob);
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    msg.className = "msg";
    msg.textContent = `已下载：${start.name}（${start.tag}）→ ${toTag} · ${fmt.toUpperCase()}`;
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  }
}

// ========== 导入知识架构（与导出同构） ==========
let lastImportPlan = null;
let latestImportResult = null;

async function downloadImportTemplate() {
  const msg = $("importMsg");
  msg.hidden = false;
  msg.className = "msg";
  try {
    const res = await fetch("/import/template");
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || `模板获取失败（HTTP ${res.status}）`);
    }
    const text = JSON.stringify(JSON.parse(await res.text()), null, 2);
    const blob = new Blob([text], { type: "application/json;charset=utf-8" });
    const a = document.createElement("a");
    a.download = "knowledge_import_template.json";
    a.href = URL.createObjectURL(blob);
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    msg.className = "msg";
    msg.textContent = "已下载模板（knowledge_import_template.json），可直接粘贴或交给本地 Agent 编辑后回传";
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  }
}

function loadImportFile() {
  const f = $("importFile")?.files?.[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    $("importInput").value = String(reader.result || "");
    $("importMsg").hidden = true;
    lastImportPlan = null;
  };
  reader.readAsText(f, "utf-8");
}

function renderImportPlan(res) {
  const el = $("importPlan");
  const s = res?.summary || {};
  const issues = res?.issues || [];
  const ok = !!res?.valid;
  el.innerHTML =
    `<div class="rtitle">校验结果：${ok ? "通过 ✓" : "不通过 ✗"} · 错误 ${res?.errors ?? 0} · 告警 ${res?.warns ?? 0}` +
    ` · 新建 ${s.create ?? 0} | 更新 ${s.update ?? 0} | 关联 ${s.link ?? 0} | 跳过 ${s.skip ?? 0}</div>` +
    (issues.length
      ? issues.map((i) => `<div class="rfield" style="color:${i.severity === "error" ? "#f87171" : "#eab308"}">[${i.severity}] ${i.kind}：${i.message}</div>`).join("")
      : `<div class="rfield muted">无问题</div>`);
  el.hidden = false;
}

async function importCheck() {
  const msg = $("importMsg");
  msg.hidden = false;
  msg.className = "msg";
  const raw = ($("importInput").value || "").trim();
  if (!raw) {
    msg.className = "msg err";
    msg.textContent = "请先粘贴或载入导出 JSON";
    return;
  }
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (_) {
    msg.className = "msg err";
    msg.textContent = "JSON 解析失败，请检查文件内容";
    return;
  }
  msg.textContent = "校验中…";
  try {
    const res = await api("/import/knowledge?dry_run=true", { method: "POST", body: JSON.stringify(payload), timeout: 120000 });
    lastImportPlan = res;
    renderImportPlan(res);
    msg.className = res.valid ? "msg" : "msg err";
    msg.textContent = res.valid ? "校验通过，可确认写入" : "存在错误，请修正后再试（告警不阻塞）";
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  }
}

async function importCommit() {
  const msg = $("importMsg");
  const status = $("importStatus");
  msg.hidden = false;
  msg.className = "msg";
  if (!lastImportPlan || !lastImportPlan.valid) {
    msg.className = "msg err";
    msg.textContent = "请先通过「校验（预览计划）」";
    return;
  }
  const raw = ($("importInput").value || "").trim();
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (_) {
    msg.className = "msg err";
    msg.textContent = "JSON 解析失败";
    return;
  }
  msg.textContent = "写入中…";
  if (status) status.textContent = "";
  try {
    const res = await api("/import/knowledge?dry_run=false", { method: "POST", body: JSON.stringify(payload), timeout: 180000 });
    latestImportResult = res;
    const s = res?.summary || {};
    if (res?.ok) {
      msg.className = "msg";
      msg.textContent = `写入完成：新建 ${s.created ?? 0} · 更新 ${s.updated ?? 0} · 关联 ${s.linked ?? 0} · 跳过 ${s.skipped ?? 0}`;
    } else {
      msg.className = "msg err";
      msg.textContent = `写入被拒绝：${res?.message || "校验未通过"}`;
    }
    if (res?.failures?.length) {
      msg.className = "msg err";
      msg.textContent = `部分写入失败 ${res.failures.length} 项：${res.failures.slice(0, 3).join(" | ")}`;
    }
    lastImportPlan = null;
    await refreshAll();
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  }
}

// ========== 最近修改 / 未审阅变更（轻量只读 + 标记已审） ==========
function refreshGraphForRecent() {
  if (overviewMode || !focusVid) showOverview().catch(alertError);
  else showSubgraph(focusVid, { withDetail: false }).catch(alertError);
}

function formatOpWho(g) {
  // 编辑者：优先用户 ID，其次 IP，其次客户端标识
  const user = (g?.user || "").trim();
  const ip = (g?.ip || "").trim();
  if (user) return `【${escHtml(user)}】`;
  if (ip) return `【IP ${escHtml(ip)}】`;
  return "—";
}

function formatOpTime(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString();
}

function fmtOpClock(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function renderPendingGroups(groups) {
  const el = $("recentList");
  if (!el) return;
  const items = groups || [];
  if (!items.length) {
    el.innerHTML = '<div class="rp-empty muted">暂无待审入库变更</div>';
    el.hidden = false;
    return;
  }
  const groupsHtml = items
    .map((g) => {
      const ops = g.ops || [];
      const who = formatOpWho(g);
      const single = ops.length === 1;
      const rows = ops
        .map(
          (o, i) => {
            const text = o.label || o.action.replace(/_/g, " ");
            const time = fmtOpClock(o.time || g.time_end);
            return `<div class="rp-row">
              <span class="rp-idx">${single ? "" : i + 1}</span>
              <span class="rp-time">${time}</span>
              <span class="rp-text" title="${escHtml(text)}">${escHtml(text)}</span>
              <span class="rp-who" title="${who}">${who}</span>
            </div>`;
          }
        )
        .join("");
      const summary = single
        ? ""
        : `<span class="rp-summary" title="${escHtml(g.label)}">${escHtml(g.label)}</span>`;
      return `<div class="rp-group">
        <label class="rp-head">
          <input type="checkbox" class="rp-check" data-mid="${g.max_op_id || 0}" autocomplete="off" />
          ${summary}
        </label>
        <div class="rp-rows">${rows}</div>
      </div>`;
    })
    .join("");
  el.innerHTML =
    `<div class="rtitle">待审入库变更（${items.length} 组）<span class="muted rp-hint">勾选后点「确认已审」；不勾 = 全部确认</span></div>` +
    `<div class="rp-list">${groupsHtml}</div>`;
  el.hidden = false;
}

function selectedReviewUntil() {
  // 返回已勾选组的最大 op id；若都未勾选则返回 0（表示“全部确认”）
  let maxUntil = 0;
  document.querySelectorAll(".rp-check:checked").forEach((cb) => {
    const v = Number(cb.getAttribute("data-mid") || 0);
    if (v > maxUntil) maxUntil = v;
  });
  return maxUntil;
}

function collectHighlightVids(groups) {
  const vids = new Set();
  for (const g of groups || []) {
    for (const v of g.vids || []) if (v) vids.add(v);
  }
  return vids;
}

async function loadPendingReview() {
  const badge = $("recentStatus");
  try {
    const res = await api("/activity/pending");
    const groups = res?.groups ?? [];
    reviewVids = collectHighlightVids(groups);
    reviewEdgeKeys = new Set();
    // 默认不强制打开高亮，交给用户勾选；勾选后重绘一次
    reviewHighlightOn = $("chkRecentHighlight")?.checked ?? true;
    renderPendingGroups(groups);
    if (badge) badge.textContent = groups.length ? `${groups.length} 组待审` : "";
    return true;
  } catch (_) {
    /* 静默：不可用时不打断主界面 */
    return false;
  }
}

async function confirmReviewed() {
  const msg = $("reviewMsg");
  if (!msg) return;
  msg.hidden = false;
  msg.className = "msg";
  msg.textContent = "推进中…";
  try {
    const until = selectedReviewUntil();
    const body = until > 0 ? JSON.stringify({ until }) : "{}";
    const res = await api("/activity/reviewed", { method: "POST", body });
    reviewVids = new Set();
    reviewEdgeKeys = new Set();
    await loadPendingReview();
    if (res) {
      msg.className = "msg";
      msg.textContent = until > 0
        ? `已确认审阅到 #${res.reviewed_until}（勾选的分批确认）`
        : `已确认审阅到 #${res.reviewed_until}，后续仅显示新变更`;
    }
    refreshGraphForRecent();
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  }
}

async function toggleRecentHighlight() {
  const on = $("chkRecentHighlight")?.checked ?? true;
  reviewHighlightOn = on;
  if (on) {
    await loadPendingReview();
    setGraphHint(reviewVids.size ? `已高亮未审阅中新增的 ${reviewVids.size} 个节点` : "当前未审阅中没有新增节点", reviewVids.size === 0);
  }
  refreshGraphForRecent();
}

async function exportHistoryRange() {
  const msg = $("reviewMsg");
  if (msg) {
    msg.hidden = false;
    msg.className = "msg";
    msg.textContent = "导出中…";
  }
  try {
    const startEl = $("historyStart");
    const endEl = $("historyEnd");
    let q = "";
    if (startEl?.value) q += `&start_ts=${encodeURIComponent(new Date(startEl.value + "T00:00:00").getTime() / 1000)}`;
    if (endEl?.value) q += `&end_ts=${encodeURIComponent(new Date(endEl.value + "T23:59:59").getTime() / 1000)}`;
    const res = await fetch(`/history/export?limit=2000${q}`);
    if (!res.ok) throw new Error(`导出失败（HTTP ${res.status}）`);
    const raw = await res.text();
    const blob = new Blob([raw], { type: "application/json;charset=utf-8" });
    const a = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 10);
    a.download = `ops_${stamp}.json`;
    a.href = URL.createObjectURL(blob);
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    if (msg) {
      const obj = JSON.parse(raw);
      msg.className = "msg";
      msg.textContent = `已导出 ${obj.count} 条操作记录`;
    }
  } catch (err) {
    if (msg) {
      msg.className = "msg err";
      msg.textContent = String(err.message || err);
    }
  }
}



async function refreshClusterOptions() {
  const [vehicles, domains, subdomains, mods, techs, mats] = await Promise.all([
    api("/vertices?tag=vehicle&limit=50"),
    api("/vertices?tag=domain&limit=200"),
    api("/vertices?tag=subdomain&limit=200"),
    api("/vertices?tag=module&limit=200"),
    api("/vertices?tag=technology&limit=200"),
    api("/vertices?tag=material&limit=200"),
  ]);
  addPool = {};
  const bucket = (tag, items) => {
    addPool[tag] = (items || []).map((n) => ({
      name: n.props?.name || n.props?.title,
      vid: n.vid,
      tag,
    })).filter((x) => x.name);
  };
  bucket("vehicle", vehicles.items);
  bucket("domain", domains.items);
  bucket("subdomain", subdomains.items);
  bucket("module", mods.items);
  bucket("technology", techs.items);
  bucket("material", mats.items);
  pathNodeIndex = {};
  for (const tag of Object.keys(addPool)) {
    for (const x of addPool[tag]) pathNodeIndex[x.name] = x.vid;
  }
  $("pathNodeList").innerHTML = Object.keys(pathNodeIndex)
    .sort((a, b) => a.localeCompare(b, "zh"))
    .map((n) => `<option value="${escapeHtml(n)}"></option>`)
    .join("");
  refreshDomainFilterOptions(domains.items || []);
  renderExportNodeList();
  if (!document.hidden) populateAddDatalists();
}

function fillDatalist(id, list) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = list
    .map((x) => `<option value="${escapeHtml(x.name)}"></option>`)
    .join("");
}

function populateAddDatalists() {
  const level = ($("addLevel")?.value) || "technology";
  const parents = [];
  for (const t of ADD_PARENT_TAGS[level] || []) parents.push(...(addPool[t] || []));
  const children = [];
  for (const t of ADD_CHILD_TAGS[level] || []) children.push(...(addPool[t] || []));
  fillDatalist("addParentList", parents);
  fillDatalist("addChildList", children);
}

function syncAddNodeFields() {
  const level = ($("addLevel")?.value) || "technology";
  const isMat = level === "material";
  const hasKw = level === "module" || level === "technology";
  const matType = $("addMatType");
  const docFields = $("addDocFields");
  const common = $("addCommonFields");
  if (matType) matType.hidden = !isMat;
  if (docFields) docFields.hidden = !isMat;
  if (common) common.hidden = isMat;
  if (common) {
    const kw = common.querySelector('[name="keywords"]');
    if (kw) kw.style.display = hasKw ? "" : "none";
    const desc = common.querySelector('[name="description"]');
    if (desc) desc.placeholder = isMat ? "" : (level === "domain" ? "领域一句话描述" : "一句话描述");
  }
  const pname = $("addForm")?.elements?.parent_name;
  if (pname) {
    pname.placeholder =
      level === "material"
        ? "上节点：支撑的技术点/模块（搜索选择，可留空）"
        : level === "domain"
          ? "上节点：车辆（可留空=自动挂整车）"
          : "上节点：所属上层（搜索选择，可留空）";
  }
  const cname = $("addForm")?.elements?.child_name;
  if (cname) {
    cname.placeholder =
      ADD_CHILD_TAGS[level]?.length
        ? `下节点：直接挂在下面的${ADD_CHILD_TAGS[level].map((t) => TAG_LABEL[t]).join("/")}（可留空）`
        : "下节点：本层级为叶子，无需填写";
    cname.readOnly = !ADD_CHILD_TAGS[level]?.length;
  }
  populateAddDatalists();
}

/** 在指定标签集中按精确名称找到节点（优先缓存池，其次后端模糊匹配）。 */
async function resolveNodeByName(tags, name) {
  for (const t of tags) {
    const hit = (addPool[t] || []).find((x) => x.name === name);
    if (hit) return { vid: hit.vid, tag: t, props: { name } };
  }
  return findNamedAny(name, tags);
}

async function findNamedAny(name, tags) {
  for (const tag of tags) {
    const found = await api(
      `/vertices?tag=${encodeURIComponent(tag)}&keyword=${encodeURIComponent(name)}&limit=50`
    );
    const hit = (found.items || []).find((n) => n.props?.name === name);
    if (hit) return hit;
  }
  return null;
}

/** 通用「添加节点」：按所属层级建节点，并挂上/下节点关系。 */
async function submitAdd(ev) {
  ev.preventDefault();
  const form = $("addForm");
  const fd = new FormData(form);
  const level = String(fd.get("level") || "technology").trim();
  const body = {
    level,
    name: String(fd.get("name") || "").trim(),
    parent_name: String(fd.get("parent_name") || "").trim(),
    child_name: String(fd.get("child_name") || "").trim(),
    material_type: String(fd.get("material_type") || "doc").trim(),
    title: String(fd.get("title") || "").trim(),
    summary: String(fd.get("summary") || "").trim(),
    source_url: String(fd.get("source_url") || "").trim(),
    description: String(fd.get("description") || "").trim(),
    keywords: String(fd.get("keywords") || "").trim(),
  };
  const msg = $("formMsg");
  msg.hidden = false;
  msg.className = "msg";
  if (!TAG_LABEL[level]) {
    msg.className = "msg err";
    msg.textContent = "请选择正确的所属层级";
    return;
  }
  if (!body.name) {
    msg.className = "msg err";
    msg.textContent = "请填写节点名称";
    return;
  }
  msg.textContent = "写入中…";
  try {
    const props =
      level === "material"
        ? {
            name: body.name,
            material_type: body.material_type,
            title: body.title || body.name,
            summary: body.summary,
            source_url: body.source_url,
            published_at: "",
          }
        : {
            name: body.name,
            description: body.description,
            keywords: level === "module" || level === "technology" ? body.keywords : "",
            status: "active",
          };
    const node = await api("/vertices", {
      method: "POST",
      body: JSON.stringify({ tag: level, props }),
    });

    const linked = []; // 记录已建立的关联
    // 上节点：文档用 supports（支撑对象），其余用 belongs_to（所属上层）
    if (body.parent_name) {
      const parent = await resolveNodeByName(ADD_PARENT_TAGS[level] || [], body.parent_name);
      if (!parent?.vid) throw new Error(`未找到上节点：${body.parent_name}`);
      const et = level === "material" ? "supports" : "belongs_to";
      await api("/edges", {
        method: "POST",
        body: JSON.stringify({ edge_type: et, src_vid: node.vid, dst_vid: parent.vid, props: { weight: 1.0 } }),
      });
      linked.push(`${TAG_LABEL[parent.tag] || parent.tag}「${parent.props?.name || body.parent_name}」`);
    } else if (level === "domain") {
      // 领域留空上节点时自动挂整车（若有）
      const veh = (addPool.vehicle || [])[0];
      if (veh?.vid) {
        await api("/edges", {
          method: "POST",
          body: JSON.stringify({ edge_type: "belongs_to", src_vid: node.vid, dst_vid: veh.vid, props: { weight: 1.0 } }),
        });
        linked.push(`车辆「${veh.name}」`);
      }
    }
    // 下节点：直接挂在本节点之下（belongs_to；若下节点是文档则用 supports）
    if (body.child_name) {
      const child = await resolveNodeByName(ADD_CHILD_TAGS[level] || [], body.child_name);
      if (!child?.vid) throw new Error(`未找到下节点：${body.child_name}`);
      const et = child.tag === "material" ? "supports" : "belongs_to";
      await api("/edges", {
        method: "POST",
        body: JSON.stringify({ edge_type: et, src_vid: child.vid, dst_vid: node.vid, props: { weight: 1.0 } }),
      });
      linked.push(`${TAG_LABEL[child.tag] || child.tag}「${child.props?.name || body.child_name}」`);
    }

    msg.className = "msg";
    msg.textContent = `已写入${TAG_LABEL[level] || level}：${node.props?.name || body.name}${linked.length ? " → 关联 " + linked.join("、") : ""}`;
    form.reset();
    syncAddNodeFields();
    await loadStats();
    await searchNodes();
    await refreshClusterOptions();
    await showSubgraph(node.vid);
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  }
}

async function addConnectionFromDetail(thisVid) {
  const edge_type = $("relType").value;
  const dir = $("relDir").value;
  const target = $("relTarget").value;
  const relMsg = $("relMsg");
  relMsg.hidden = false;
  if (!target) {
    relMsg.className = "msg err";
    relMsg.textContent = "请选择目标节点";
    return;
  }
  let src, dst;
  if (dir === "this_to_target") {
    src = thisVid;
    dst = target;
  } else {
    src = target;
    dst = thisVid;
  }
  relMsg.className = "msg";
  relMsg.textContent = "建立中…";
  try {
    await api("/edges", {
      method: "POST",
      body: JSON.stringify({ edge_type, src_vid: src, dst_vid: dst, props: { weight: 1.0 } }),
    });
    relMsg.className = "msg";
    relMsg.textContent = `已建立 ${REL_LABEL[edge_type] || edge_type} 关联`;
    await openDetail(thisVid, { focusGraph: false });
    if (overviewMode) await showOverview();
    else if (focusVid) await showSubgraph(focusVid, { withDetail: false });
  } catch (err) {
    relMsg.className = "msg err";
    relMsg.textContent = String(err.message || err);
  }
}

async function deleteCurrentNode() {
  if (detailEdge) {
    const { edge_type, src_vid, dst_vid } = detailEdge;
    const rel = REL_LABEL[edge_type] || edge_type;
    if (!confirm(`确认删除关系「${rel}」？\n${src_vid} → ${dst_vid}`)) return;
    await api("/edges", {
      method: "DELETE",
      body: JSON.stringify({ edge_type, src_vid, dst_vid }),
    });
    closeDrawer();
    if (overviewMode) await showOverview();
    else if (focusVid) await showSubgraph(focusVid, { withDetail: false });
    else await refreshAll();
    setGraphHint("已删除关系", false);
    return;
  }
  const vid = $("btnDeleteNode").dataset.vid || detailVid;
  if (!vid) return;
  const name = $("drawerTitle").textContent || vid;
  const info = await api(`/vertices/${encodeURIComponent(vid)}/cascade`);
  const kids = (info.nodes || []).filter((n) => n.vid !== vid);
  const choice = await confirmCascadeDelete({ name, vid, only: info.count <= 1, kids });
  if (choice === "only") {
    await api(`/vertices/${encodeURIComponent(vid)}`, { method: "DELETE" });
  } else if (choice === "cascade") {
    // 子先父后删除，降低中途失败留下孤儿节点的风险；一次性请求归为同一 batch，可整批「撤回」
    const order = (info.nodes || []).slice().reverse();
    const vids = order.map((n) => n.vid);
    await api("/vertices/batch-delete", {
      method: "POST",
      body: JSON.stringify({ vids }),
    });
  } else {
    return;
  }
  if (focusVid === vid) focusVid = null;
  if (detailVid === vid) closeDrawer();
  overviewMode = true;
  await refreshAll();
  setGraphHint(choice === "cascade" ? `已级联删除 ${info.count} 个节点` : "已删除节点", false);
}

/** 删除确认对话框：可选「仅删除该节点」或「连带其独占管控的下层节点一并删除」（内联样式，自包含）。 */
function confirmCascadeDelete({ name, vid, only, kids }) {
  return new Promise((resolve) => {
    const byTag = {};
    (kids || []).forEach((n) => {
      byTag[n.tag] = (byTag[n.tag] || 0) + 1;
    });
    const tags = Object.keys(byTag);
    const preview = only
      ? ""
      : `<p style="color:#8ba3c7;font-size:12px;margin:6px 0 10px">将连同下层「只归本节点管控」的节点一起删除：` +
        tags.map((t) => `${TAG_LABEL[t] || t} ${byTag[t]} 个`).join("、") +
        `（共 ${kids.length} 个）</p>` +
        `<p style="color:#5f7ea8;font-size:11px;margin:0 0 6px">同时被其它节点管控的下层节点会保留（例如同时支撑两个技术点的文档不会被删）。</p>`;
    const mask = document.createElement("div");
    mask.style.cssText =
      "position:fixed;inset:0;background:rgba(4,10,20,.66);z-index:60;display:flex;align-items:center;justify-content:center";
    const box = document.createElement("div");
    box.style.cssText =
      "background:#0e1726;border:1px solid #2c3b55;border-radius:10px;padding:18px 20px;max-width:440px;width:92%;box-shadow:0 10px 40px rgba(0,0,0,.5)";
    box.innerHTML =
      `<h3 style="margin:0 0 6px;color:#e6edf7;font-size:15px">删除节点「${escHtml(name)}」</h3>` +
      (only
        ? `<p style="color:#8ba3c7;font-size:12px;margin:4px 0 0">该节点下没有仅归它管控的节点。</p>`
        : "") +
      preview +
      `<div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px;flex-wrap:wrap">` +
      `<button data-act="only" style="cursor:pointer;background:#1b2b44;border:1px solid #31445f;color:#c7d9f5;border-radius:6px;padding:7px 16px">仅删除该节点</button>` +
      (only
        ? ""
        : `<button data-act="cascade" style="cursor:pointer;background:#b91c1c;border:1px solid #ef4444;color:#fff;border-radius:6px;padding:7px 16px;font-weight:600">级联删除（${kids.length + 1}）</button>`) +
      `<button data-act="cancel" style="cursor:pointer;background:transparent;border:1px solid #31445f;color:#8ba3c7;border-radius:6px;padding:7px 16px">取消</button>` +
      `</div>`;
    mask.appendChild(box);
    document.body.appendChild(mask);
    const done = (act) => {
      mask.remove();
      resolve(act);
    };
    mask.addEventListener("click", (e) => {
      if (e.target === mask) done("cancel");
    });
    mask.querySelectorAll("button[data-act]").forEach((b) => {
      b.addEventListener("click", () => done(b.dataset.act));
    });
  });
}

let llmReady = false;

async function loadAiStatus() {
  try {
    const st = await api("/ai/status");
    llmReady = !!st.llm_ready;
    $("aiStatus").textContent = llmReady ? "推理服务已就绪" : "推荐 Cursor 协作";
    $("aiStatus").title = llmReady
      ? "企业推理接口可用，可使用「自动抽取」"
      : "未连通企业推理服务时，请使用「生成协作提示词」或在 Cursor 中直接对话入库";
    $("btnAiExtract").disabled = !llmReady;
    $("btnAiExtract").title = llmReady
      ? "调用已配置的企业推理服务进行结构化抽取"
      : "企业推理服务未就绪（未配置或网络不可达）";
  } catch (_) {
    llmReady = false;
    $("aiStatus").textContent = "推荐 Cursor 协作";
    $("btnAiExtract").disabled = true;
  }
}

function buildImportTemplate() {
  return `【AI4KnowledgeNet 批量入库格式模板】
用于让本地 AI 按本库的入库格式，把一份份技术资料处理成结构化 JSON。
请把下面的"JSON 格式"发给本地 AI，让它对照资料填写；可直接粘贴，或写入 .md 文件后导入（支持一次多份，用 \`\`\`json 代码块分隔均可）。

JSON 格式（一份资料一个对象）:
{
  "domain": "上一层技术簇，≤12字，必填",
  "subdomain": "中间层技术簇，≤12字，最小技术点可留空字符串",
  "tech_points": [
    {"name": "技术点名称（≤16字）", "description": "一句话描述"}
  ],
  "materials": [
    {
      "name": "文档简称（≤20字）",
      "type": "paper|patent|news|doc|standard",
      "title": "原始标题",
      "summary": "摘要（≤100字）",
      "source_url": ""
    }
  ],
  "tech_material_links": [
    {"tech": "技术点名称", "material": "文档简称"}
  ],
  "notes": "可选：交叉技术或不确定处说明"
}

填表说明:
- 网络可多分支向下；一份资料可对应多个技术点（多写法）
- 一个文档可支撑多个技术点（在 links 里写多条）
- 已有技术点/文档入库时会自动复用，不必担心重复；
  领域尽量复用已知顶层（如：底盘结构、电驱与功率电子、热管理、动力电池、轻量化材料等）

示例（一份资料）:
{
  "domain": "电驱与功率电子",
  "subdomain": "电力电子",
  "tech_points": [
    {"name": "碳化硅MOSFET", "description": "SiC MOSFET 用于电驱逆变器，降低开关损耗"},
    {"name": "三相桥式逆变器", "description": "将直流电转换为三相交流驱动电机"}
  ],
  "materials": [
    {"name": "SiC电驱综述", "type": "paper", "title": "SiC MOSFET in traction inverters", "summary": "综述SiC在电驱中的应用与损耗对比", "source_url": ""}
  ],
  "tech_material_links": [
    {"tech": "碳化硅MOSFET", "material": "SiC电驱综述"},
    {"tech": "三相桥式逆变器", "material": "SiC电驱综述"}
  ],
  "notes": ""
}`;
}

function showBatchTemplate() {
  const msg = $("batchMsg");
  const area = $("batchTemplateArea");
  const template = buildImportTemplate();
  area.hidden = false;
  area.textContent = template;
  msg.hidden = false;
  msg.className = "msg";
  try {
    navigator.clipboard.writeText(template).then(() => {
      msg.textContent = "入库格式模板已复制到剪贴板，请发给本地 AI 使用。";
    }).catch(() => {
      msg.textContent = "模板已显示在上方，请手动复制给本地 AI。";
    });
  } catch (_) {
    msg.textContent = "模板已显示在上方，请手动复制给本地 AI。";
  }
}

async function importMdFile() {
  const input = $("mdFile");
  const msg = $("batchMsg");
  input.click();
  input.onchange = async () => {
    const file = input.files && input.files[0];
    input.value = "";
    if (!file) return;
    msg.hidden = false;
    msg.className = "msg";
    try {
      const text = await file.text();
      $("batchInput").value = text;
      msg.textContent = `已读入「${file.name}」（${text.length} 字），点「加载到入库预览」解析。`;
    } catch (err) {
      msg.className = "msg err";
      msg.textContent = "读取文件失败：" + String(err.message || err);
    }
  };
}

function parseBatchPayloads(raw) {
  const text = (raw || "").trim();
  const out = [];
  // 1) 提取所有 ```json / ``` 代码块
  const fences = [...text.matchAll(/```(?:json)?\s*([\s\S]*?)```/gi)].map((m) => m[1].trim());
  const chunks = fences.length ? fences : [text];
  for (const c of chunks) {
    if (!c) continue;
    let firstCand = c;
    // 若整段不是 JSON，尝试从中截取从第一个 { 到最后一个 }
    if (!/^\s*(\{|\[)/.test(firstCand)) {
      const s = firstCand.indexOf("{");
      const e = firstCand.lastIndexOf("}");
      if (s >= 0 && e > s) firstCand = firstCand.slice(s, e + 1);
    }
    try {
      const parsed = JSON.parse(firstCand);
      if (Array.isArray(parsed)) {
        parsed.forEach((p) => { if (p && typeof p === "object") out.push(p); });
      } else if (parsed && typeof parsed === "object") {
        out.push(parsed);
      }
    } catch (_) { /* 跳过不可解析片段 */ }
  }
  return out;
}

function loadBatchToPreview() {
  const msg = $("batchMsg");
  const raw = ($("batchInput").value || "").trim();
  msg.hidden = false;
  msg.className = "msg";
  if (!raw) {
    msg.className = "msg err";
    msg.textContent = "请先粘贴内容或导入 .md 文档";
    return;
  }
  const payloads = parseBatchPayloads(raw);
  if (!payloads.length) {
    msg.className = "msg err";
    msg.textContent = "未解析到有效的入库 JSON，请检查格式（是否含 domain / tech_points）";
    return;
  }
  if (payloads.length === 1) {
    loadPayloadToPreview(payloads[0]);
    msg.textContent = "已加载到下方入库预览，请核对后点「确认写入」";
  } else {
    renderBatchList(payloads);
    msg.textContent = `检测到 ${payloads.length} 份资料，请在下方逐份核对 / 写入`;
  }
}

function loadPayloadToPreview(payload) {
  lastExtract = payload;
  const preview = $("aiPreview");
  preview.hidden = false;
  $("batchList").hidden = true;
  const ready = ((payload.domain || "").trim() && Array.isArray(payload.tech_points));
  $("btnAiCommit").disabled = !ready;
  try {
    api("/ai/match", { method: "POST", body: JSON.stringify({ payload }) })
      .then((match) => renderAICards(match || {}))
      .catch(() => renderAICards({}));
  } catch (_) {
    renderAICards({});
  }
}

function renderBatchList(payloads) {
  const list = $("batchList");
  const html = payloads.map((p, i) => {
    const techs = (p.tech_points || []).length;
    const mats = (p.materials || []).length;
    return `<div class="rgroup"><div class="rfield"><label>#${i + 1}. ${escHtml((p.domain || "").toString() || "未填领域")}${p.subdomain ? " / " + escHtml(p.subdomain.toString()) : ""}</label>
      <button type="button" class="btn-add" data-batch-preview="${i}">编辑</button>
      <button type="button" class="btn-add" data-batch-commit="${i}" title="直接写入图谱">写入</button>
      <span data-batch-state="${i}" class="muted"></span></div>
      <div class="rfield" style="padding-left:0;font-size:12px;color:#8ba3c7">技术点 ${techs} · 文档 ${mats}</div></div>`;
  }).join("");
  list.innerHTML = `<div class="rgroup"><div class="rtitle">批量入库清单（${payloads.length} 份）</div></div>` + html;
  list.hidden = false;
  list.querySelectorAll("[data-batch-preview]").forEach((b) => {
    b.onclick = () => loadPayloadToPreview(payloads[+b.dataset.batchPreview]);
  });
  list.querySelectorAll("[data-batch-commit]").forEach((b) => {
    b.onclick = () => commitBatchPayload(payloads[+b.dataset.batchCommit], b);
  });
}

async function commitBatchPayload(payload, btn) {
  const state = btn.parentElement.querySelector("[data-batch-state]");
  btn.disabled = true;
  state.textContent = "写入中…";
  try {
    const written = await api("/ai/commit", { method: "POST", body: JSON.stringify({ payload }) });
    const n = (written.technologies || []).length;
    const m = (written.materials || []).length;
    state.textContent = `已写入 技术点${n}·文档${m}·支撑边${written.supports_links || 0}`;
    btn.disabled = false;
    btn.textContent = "已写入";
    btn.style.opacity = "0.5";
    btn.onclick = null;
    await loadStats();
  } catch (err) {
    state.textContent = "写入失败";
    btn.disabled = false;
    $("batchMsg").className = "msg err";
    $("batchMsg").textContent = String(err.message || err);
  }
}

// ========== 自动采集 ==========
function collectStatusText(st) {
  const s = st || {};
  if (s.running) return `采集中… 已处理 ${s.processed} / 新增 ${s.added}`;
  return s.message || "—";
}

async function loadCollectList() {
  const wrap = $("collectList");
  const msg = $("collectMsg");
  try {
    const data = await api("/collect/candidates?status=pending&limit=200");
    const items = data.items || [];
    wrap.hidden = false;
    if (!items.length) {
      wrap.innerHTML = '<div class="rgroup"><div class="rfield"><span class="muted">暂无待入库候选。点「立即采集」或等待定时任务。</span></div></div>';
      return;
    }
    wrap.innerHTML = items.map((it, i) => {
      const d = new Date(it.created_at * 1000);
      const t = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
      const pl = it.payload || {};
      const cleanUrl = String(it.url || "").split("#sub=")[0];
      const detail = [];
      if ((pl.subdomain || "") && Array.isArray(pl.tech_points)) {
        const techs = (pl.tech_points || []).map((tp) => tp.name || "").filter(Boolean).join("、");
        detail.push(`<span class="muted" style="font-size:11px">${escHtml(pl.subdomain)} · 技术点：${escHtml(techs)}</span>`);
      }
      if (pl.notes) {
        detail.push(`<span class="muted" style="font-size:11px">${escHtml(String(pl.notes).slice(0, 120))}</span>`);
      }
      return `<div class="rgroup">
        <div class="rfield" style="align-items:flex-start;flex-direction:column">
          <label>#${i + 1} · ${escHtml(it.kind || "")}（${escHtml(it.site || "")}）</label>
          <span style="font-size:12px;color:#c7d9f5">${escHtml(it.title || "(无标题)")}</span>
          ${detail.join("")}
          <span class="muted" style="font-size:11px">${t} · <a href="${escAttr(cleanUrl)}" target="_blank" rel="noreferrer">原文链接</a></span>
        </div>
        <div class="rfield"><button type="button" class="btn-add" data-collect-commit="${it.id}" title="AI抽取结果写入图谱">入库</button>
        <button type="button" class="btn-add" data-collect-reject="${it.id}" title="忽略此条">删除</button></div>
      </div>`;
    }).join("");
    wrap.querySelectorAll("[data-collect-commit]").forEach((b) => {
      b.onclick = () => collectCommit(+b.dataset.collectCommit, b);
    });
    wrap.querySelectorAll("[data-collect-reject]").forEach((b) => {
      b.onclick = () => collectReject(+b.dataset.collectReject, b);
    });
  } catch (err) {
    msg.hidden = false;
    msg.className = "msg err";
    msg.textContent = "加载候选失败：" + String(err.message || err);
  }
}

async function refreshCollectStatus() {
  try {
    const st = await api("/collect/status");
    $("collectStatus").textContent = collectStatusText(st);
  } catch (_) { /* ignore */ }
}

async function runCollect() {
  const msg = $("collectMsg");
  msg.hidden = false;
  msg.className = "msg";
  try {
    const r = await api("/collect/run", { method: "POST", body: "{}" });
    msg.textContent = r.message || "后台采集已启动";
    refreshCollectStatus();
    loadCollectList();
    // 轮询状态直至完成
    const timer = setInterval(async () => {
      try {
        const st = await api("/collect/status");
        $("collectStatus").textContent = collectStatusText(st);
        if (!st.running) {
          clearInterval(timer);
          msg.textContent = `${st.message || "采集完成"}，已刷新清单`;
          loadCollectList();
        }
      } catch (_) { clearInterval(timer); }
    }, 5000);
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = "启动采集失败：" + String(err.message || err);
  }
}

async function collectCommit(id, btn) {
  const msg = $("collectMsg");
  if (!window.confirm("确认将这条 AI 抽取结果写入图谱？")) return;
  btn.disabled = true;
  btn.textContent = "写入中…";
  try {
    const r = await api(`/collect/candidates/${id}/commit`, { method: "POST", body: "{}" });
    if (!r.ok) throw new Error(r.reason || "写入失败");
    const w = r.written || {};
    msg.hidden = false;
    msg.className = "msg";
    msg.textContent = `已入库：技术点${(w.technologies || []).length} · 文档${(w.materials || []).length} · 支撑边${w.supports_links || 0}`;
    await loadStats();
    loadCollectList();
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
    btn.disabled = false;
    btn.textContent = "入库";
  }
}

async function collectReject(id, btn) {
  const msg = $("collectMsg");
  if (!window.confirm("删除此候选？")) return;
  try {
    await api(`/collect/candidates/${id}/reject`, { method: "POST", body: "{}" });
    msg.hidden = true;
    loadCollectList();
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  }
}

async function doUndoRedo(path) {
  const msg = "撤回中…";
  try {
    const r = await api(path, { method: "POST", body: "{}" });
    if (r.ok) {
      const op = r.op || {};
      const label = (op.action || "").replaceAll("_", " ");
      alert(`已${path.includes("undo") ? "撤回" : "重做"}：${label}`);
      await refreshAll();
      if (overviewMode) await showOverview(); else if (focusVid) await showSubgraph(focusVid, { withDetail: false });
    } else {
      alert(r.reason || "无法撤回");
    }
  } catch (err) {
    alert(String(err.message || err));
  }
}

async function runFetchUrl() {
  const url = $("fetchUrl").value.trim();
  const msg = $("fetchMsg");
  const status = $("fetchStatus");
  msg.hidden = false;
  msg.className = "msg";
  if (!url) {
    msg.className = "msg err";
    msg.textContent = "请先输入网页 URL";
    return;
  }
  status.textContent = "抓取中…";
  msg.textContent = "";
  const btn = $("btnFetch");
  btn.disabled = true;
  try {
    const data = await api("/ai/fetch", { method: "POST", body: JSON.stringify({ url }) });
    if (data.title) $("aiTitle").value = data.title;
    if (data.text) {
      $("aiText").value = data.text;
      msg.className = "msg";
      msg.textContent = `已抓取「${data.title || url}」（${data.text.length} 字），可点「自动抽取」或直接编辑上方文本。`;
    }
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  } finally {
    status.textContent = "";
    btn.disabled = false;
  }
}

async function runAiExtract() {
  const text = $("aiText").value.trim();
  const msg = $("aiMsg");
  const preview = $("aiPreview");
  msg.hidden = false;
  msg.className = "msg";
  if (!text) {
    msg.className = "msg err";
    msg.textContent = "请先粘贴资料文本";
    return;
  }
  msg.textContent = "抽取中…";
  $("btnAiExtract").disabled = true;
  try {
    const data = await api("/ai/extract", {
      method: "POST",
      body: JSON.stringify({
        text,
        title: $("aiTitle").value.trim(),
        translate: $("aiTranslate").checked,
        save: false,
      }),
    });
    lastExtract = data.extracted;
    // 标注哪些技术点/文档已存在（可复用）或将新建
    let match = { tech_points: [], materials: [] };
    try {
      match = await api("/ai/match", { method: "POST", body: JSON.stringify({ payload: lastExtract }) });
    } catch (_) { /* 忽略标注失败，仍可编辑提交 */ }
    renderAICards(match);
    preview.hidden = false;
    $("btnAiCommit").disabled = false;
    msg.textContent = "抽取完成，请核对下方内容后点「确认写入」";
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  } finally {
    $("btnAiExtract").disabled = false;
  }
}

function renderAICards(match) {
  const wrap = $("aiPreview");
  const ex = lastExtract || {};
  const domain = (ex.domain || "").toString();
  const subdomain = (ex.subdomain || "").toString();
  const techs = Array.isArray(ex.tech_points) ? ex.tech_points : [];
  const mats = Array.isArray(ex.materials) ? ex.materials : [];
  const links = Array.isArray(ex.tech_material_links) ? ex.tech_material_links : [];
  const techMatch = new Map((match.tech_points || []).map((t) => [t.name, t.exists]));
  const notes = (ex.notes || "").toString();

  let html = '<div class="rgroup"><div class="rtitle">放置位置</div>';
  html += '<div class="rfield"><label>领域</label><input type="text" data-k="domain" value="' + escAttr(domain) + '"></div>';
  html += '<div class="rfield"><label>子领域</label><input type="text" data-k="subdomain" value="' + escAttr(subdomain) + '"></div></div>';

  // 技术点
  html += '<div class="rgroup"><div class="rtitle">技术点</div>';
  techs.forEach((tp, i) => {
    const exists = techMatch.get(tp.name);
    const badge = exists ? '<span class="badge badge-exists">已存在·复用</span>' : '<span class="badge badge-new">将新建</span>';
    html += '<div class="rfield">' + badge +
      '<input type="text" data-tt="name" data-i="' + i + '" value="' + escAttr(tp.name || "") + '" placeholder="技术点名称">' +
      '<button type="button" class="btn-add" data-del-tech="' + i + '" title="删除">✕</button></div>';
    html += '<div class="rfield" style="padding-left:52px"><label>描述</label><textarea data-tt="description" data-i="' + i + '" rows="1">' + escHtml(tp.description || "") + '</textarea></div>';
  });
  html += '<button type="button" class="btn-add" id="aiAddTech">＋ 添加技术点</button></div>';

  // 文档 + 支撑
  html += '<div class="rgroup"><div class="rtitle">文档（支撑哪些技术点请勾选）</div>';
  mats.forEach((m, mi) => {
    html += '<div class="rfield"><label>名称</label><input type="text" data-mt="name" data-mi="' + mi + '" value="' + escAttr(m.name || "") + '">' +
      '<button type="button" class="btn-add" data-del-mat="' + mi + '" title="删除">✕</button></div>';
    html += '<div class="rfield" style="padding-left:52px"><label>类型</label><input type="text" data-mt="type" data-mi="' + mi + '" value="' + escAttr(m.type || "doc") + '"></div>';
    html += '<div class="rfield" style="padding-left:52px;flex-direction:column;align-items:stretch"><label style="width:auto">摘要</label><textarea data-mtt="summary" data-mi="' + mi + '" rows="1">' + escHtml(m.summary || "") + '</textarea></div>';
    html += '<div class="rfield" style="padding-left:52px"><label>支撑</label><div class="chips">' +
      techs.map((tp) => {
        const on = links.some((l) => l.material === m.name && l.tech === tp.name);
        return '<span class="chip' + (on ? " on" : "") + '" data-support data-mi="' + mi + '" data-tech="' + escAttr(tp.name) + '">' + escHtml(tp.name) + '</span>';
      }).join("") +
      '</div></div>';
  });
  html += '<button type="button" class="btn-add" id="aiAddMat">＋ 添加文档</button></div>';

  // 备注
  html += '<div class="rgroup ai-note"><div class="rtitle">备注</div><textarea data-k="notes" rows="1">' + escHtml(notes) + '</textarea></div>';

  wrap.innerHTML = html;
  $("aiAddTech").onclick = () => {
    lastExtract.tech_points = lastExtract.tech_points || [];
    lastExtract.tech_points.push({ name: "", description: "" });
    renderAICards({});
  };
  $("aiAddMat").onclick = () => {
    lastExtract.materials = lastExtract.materials || [];
    lastExtract.materials.push({ name: "", type: "doc", title: "", summary: "" });
    renderAICards({});
  };
  wrap.querySelectorAll("[data-del-tech]").forEach((b) => {
    b.onclick = () => { lastExtract.tech_points.splice(+b.dataset.delTech, 1); collectAICards(); renderAICards({}); };
  });
  wrap.querySelectorAll("[data-del-mat]").forEach((b) => {
    b.onclick = () => { lastExtract.materials.splice(+b.dataset.delMat, 1); lastExtract.tech_material_links = (lastExtract.tech_material_links || []).filter((l) => l.material !== lastExtract.materials[+b.dataset.delMat]?.name); collectAICards(); renderAICards({}); };
  });
  wrap.querySelectorAll("[data-tt]").forEach((inp) => {
    inp.addEventListener("input", () => {
      const i = +inp.dataset.i;
      lastExtract.tech_points[i] = lastExtract.tech_points[i] || {};
      lastExtract.tech_points[i][inp.dataset.tt] = inp.value;
    });
  });
  wrap.querySelectorAll("[data-mt]").forEach((inp) => {
    inp.addEventListener("input", () => {
      const i = +inp.dataset.mi;
      lastExtract.materials[i] = lastExtract.materials[i] || {};
      lastExtract.materials[i][inp.dataset.mt] = inp.value;
    });
  });
  wrap.querySelectorAll("[data-mtt]").forEach((inp) => {
    inp.addEventListener("input", () => {
      const i = +inp.dataset.mi;
      lastExtract.materials[i] = lastExtract.materials[i] || {};
      lastExtract.materials[i][inp.dataset.mtt] = inp.value;
    });
  });
  wrap.querySelectorAll("[data-k]").forEach((inp) => {
    inp.addEventListener("input", () => { lastExtract[inp.dataset.k] = inp.value; });
  });
  wrap.querySelectorAll("[data-support]").forEach((chip) => {
    chip.onclick = () => {
      const mi = +chip.dataset.mi;
      const tech = chip.dataset.tech;
      const matName = lastExtract.materials[mi]?.name;
      lastExtract.tech_material_links = lastExtract.tech_material_links || [];
      const idx = lastExtract.tech_material_links.findIndex((l) => l.material === matName && l.tech === tech);
      if (idx >= 0) lastExtract.tech_material_links.splice(idx, 1);
      else lastExtract.tech_material_links.push({ material: matName, tech });
      chip.classList.toggle("on", idx < 0);
    };
  });
}

function collectAICards() {
  // 从 DOM 读回所有已编辑字段（在增删后调用以保留编辑）
  const wrap = $("aiPreview");
  lastExtract = lastExtract || {};
  wrap.querySelectorAll("[data-k]").forEach((inp) => { lastExtract[inp.dataset.k] = inp.value; });
}


async function runAiCommit() {
  const msg = $("aiMsg");
  if (!lastExtract) {
    msg.hidden = false;
    msg.className = "msg err";
    msg.textContent = "请先抽取";
    return;
  }
  collectAICards();
  if (!(lastExtract.domain || "").trim()) {
    msg.hidden = false;
    msg.className = "msg err";
    msg.textContent = "请填写「领域」（文档要挂到哪个上层技术簇）";
    return;
  }
  msg.hidden = false;
  msg.className = "msg";
  msg.textContent = "写入中…";
  $("btnAiCommit").disabled = true;
  try {
    const written = await api("/ai/commit", {
      method: "POST",
      body: JSON.stringify({ payload: lastExtract }),
    });
    const n = (written.technologies || []).length;
    const m = (written.materials || []).length;
    msg.textContent = `已写入：技术点 ${n} · 文档 ${m} · 支撑边 ${written.supports_links || 0}`;
    await loadStats();
    await searchNodes();
    await showOverview();
    const first = (written.technologies || [])[0];
    if (first?.vid) await showSubgraph(first.vid, { withDetail: true });
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
    $("btnAiCommit").disabled = false;
  }
}

async function runFormAssist(mode) {
  const form = $("addForm");
  const desc = form.elements.description;
  const text = (desc.value || form.elements.name.value || "").trim();
  const msg = $("formMsg");
  msg.hidden = false;
  msg.className = "msg";
  if (!text) {
    msg.className = "msg err";
    msg.textContent = "请先填写名称或描述";
    return;
  }
  msg.textContent = mode === "translate" ? "翻译中…" : "提炼中…";
  try {
    const data = await api("/ai/assist", {
      method: "POST",
      body: JSON.stringify({ text, mode }),
    });
    if (data.text) desc.value = data.text;
    if (data.keywords && form.elements.keywords) {
      form.elements.keywords.value = data.keywords;
    }
    msg.textContent = "已填入协助结果，可再编辑后写入";
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  }
}

function resolvePathEndpoint(text) {
  const t = String(text || "").trim();
  if (!t) return null;
  if (pathNodeIndex[t]) return pathNodeIndex[t];
  // allow raw vid
  if (/^[A-Za-z0-9_\-:.]{3,64}$/.test(t)) return t;
  return null;
}

async function runPathQuery() {
  const msg = $("pathMsg");
  msg.hidden = false;
  msg.className = "msg";
  const src = resolvePathEndpoint($("pathSrc").value);
  const dst = resolvePathEndpoint($("pathDst").value);
  if (!src || !dst) {
    msg.className = "msg err";
    msg.textContent = "请从下拉选择已有节点作为起点/终点";
    return;
  }
  msg.textContent = "查询中…";
  try {
    const data = await api(`/path?src=${encodeURIComponent(src)}&dst=${encodeURIComponent(dst)}`);
    if (!data.found || !data.path?.nodes?.length) {
      msg.className = "msg err";
      msg.textContent = "未找到路径（可换方向或检查是否连通）";
      return;
    }
    const names = (data.path.nodes || []).map((n) => n.props?.name || n.vid).join(" → ");
    msg.textContent = `路径 ${data.path.length || 0} 跳：${names}`;
    overviewMode = false;
    focusVid = src;
    drawGraph(
      { nodes: data.path.nodes, edges: data.path.edges || [] },
      src
    );
    const ft = $("focusTitle"); if (ft) ft.textContent = "";
    const fm = $("focusMeta"); if (fm) fm.textContent = "";
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = String(err.message || err);
  }
}

async function boot() {
  // URL hash 快捷入口：如 #view=2d&layout=tree / #view=3d&layout=tree，便于分享指定视图
  try {
    const h = new URLSearchParams((location.hash || "").replace(/^#/, ""));
    const l = h.get("layout");
    if (l === "tree" || l === "radial" || l === "force") layoutMode = l;
    const t3 = h.get("tree3d");
    if (t3 === "ring" || t3 === "layer") tree3dMode = t3;
    const v = h.get("view");
    if (v === "2d") setViewMode("2d");
    else if (v === "3d") setViewMode("3d");
  } catch (_) {
    /* ignore */
  }
  // 打开/刷新默认展示全部领域（领域下拉保持“全部”）
  domainFilter = "";
  $("btnSearch").addEventListener("click", () => searchNodes().catch(alertError));
  $("btnHighlightSearch")?.addEventListener("click", () => {
    // 仅当“要开启高亮但尚无查找结果”时拦截；关闭高亮始终允许（可随时恢复整图亮度）
    if (!searchResultVids.size && !highlightSearch) {
      setGraphHint("请先输入关键词查找，再点此在图谱中高亮命中节点", true);
      return;
    }
    highlightSearch = !highlightSearch;
    $("btnHighlightSearch")?.classList.toggle("active", highlightSearch);
    setGraphHint(highlightSearch ? "已在图谱中高亮查找结果" : "已取消查找结果高亮", false);
    if (!highlightSearch && viewMode === "3d") {
      // 取消高亮时保持当前视图，直接重绘即可
      redrawCurrentGraph();
      return;
    }
    // 高亮命中在 2D 呈现更清晰，自动切到二维
    focusIn2D(() => {
      forceFitNext = false;
      redrawCurrentGraph();
    });
  });
  $("btnRefresh").addEventListener("click", () => refreshAll().catch(alertError));
  $("btnOverview").addEventListener("click", () => showOverview().catch(alertError));
  const onViewFilterChange = () => {
    readViewControls();
    syncViewControls();
    forceFitNext = true;
    renderList(nodesCache);
    // Overview 数据预算取决于所选层（材料层需要更大配额）；只有重新拉取才能补上材料
    if (overviewMode) showOverview().catch(alertError);
    else redrawCurrentGraph();
  };
  $("layerCap")?.addEventListener("change", onViewFilterChange);
  $("layerScope")?.addEventListener("change", onViewFilterChange);
  $("domainFilter")?.addEventListener("change", onViewFilterChange);
  $("btnLayoutForce")?.addEventListener("click", () => {
    layoutMode = "force";
    forceFitNext = true;
    syncViewControls();
    redrawCurrentGraph();
  });
  $("btnLayoutRadial")?.addEventListener("click", () => {
    layoutMode = "radial";
    forceFitNext = true;
    syncViewControls();
    if (!overviewMode) showOverview().catch(alertError);
    else redrawCurrentGraph();
  });
  $("btnLayoutTree")?.addEventListener("click", () => {
    layoutMode = "tree";
    forceFitNext = true;
    syncViewControls();
    if (!overviewMode) showOverview().catch(alertError);
    else redrawCurrentGraph();
  });
  $("btnTreeReset")?.addEventListener("click", () => {
    if (layoutMode !== "tree" || viewMode !== "2d") return;
    forceFitNext = true;
    syncViewControls();
    redrawCurrentGraph();
  });
  $("btnTreeCenter")?.addEventListener("click", () => {
    if (layoutMode !== "tree" || viewMode !== "2d") return;
    treeCenterLayout = !treeCenterLayout;
    forceFitNext = true;
    syncViewControls();
    redrawCurrentGraph();
  });
  $("btnTree3dMode")?.addEventListener("click", () => {
    if (layoutMode !== "tree" || viewMode !== "3d") return;
    tree3dMode = tree3dMode === "ring" ? "layer" : "ring";
    syncViewControls();
    redrawCurrentGraph();
  });
  $("btnTreeExpandAll")?.addEventListener("click", () => {
    if (!classificationIndex.children) return;
    treeExpanded = new Set(classificationIndex.children.keys());
    renderClassificationTree();
  });
  $("btnTreeCollapseAll")?.addEventListener("click", () => {
    treeExpanded.clear();
    renderClassificationTree();
  });
  $("btnTreeRefresh")?.addEventListener("click", () => refreshClassificationTree().catch(alertError));
  $("treePanel")?.addEventListener("click", (e) => {
    const caret = e.target.closest("[data-tree-caret]");
    if (caret) {
      const vid = caret.getAttribute("data-tree-caret");
      if (treeExpanded.has(vid)) treeExpanded.delete(vid);
      else treeExpanded.add(vid);
      renderClassificationTree();
      return;
    }
    const row = e.target.closest("[data-tree-vid]");
    if (!row) return;
    openDetail(row.getAttribute("data-tree-vid"), { focusGraph: false })
      .then(() => renderClassificationTree())
      .catch(alertError);
  });
  $("btnReheat")?.addEventListener("click", () => reheatForceLayout());
  $("btnFitGraph")?.addEventListener("click", () => fitCurrentGraph());
  $("btnLabels3d")?.addEventListener("click", () => {
    label3dEnabled = !label3dEnabled;
    syncViewControls();
    refreshLabels();
    setGraphHint(label3dEnabled ? "已显示节点标注" : "已隐藏节点标注", false);
  });
  document.querySelectorAll("[data-label3d-tag]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!label3dEnabled) return;
      const tag = btn.getAttribute("data-label3d-tag");
      if (!tag) return;
      if (label3dTags.has(tag)) label3dTags.delete(tag);
      else label3dTags.add(tag);
      syncViewControls();
      refreshLabels();
    });
  });
  const syncIsolateToggle = () => {
    $("btnIsolate")?.classList.toggle("active", isolateSelection);
  };
  $("btnIsolate")?.addEventListener("click", () => {
    isolateSelection = !isolateSelection;
    if (isolateSelection && !(detailVid || focusVid || detailEdge)) {
      isolateSelection = false;
      setGraphHint("先选中一个节点，再开「只看选中」", true);
      syncIsolateToggle();
      return;
    }
    syncIsolateToggle();
    forceFitNext = true;
    redrawCurrentGraph();
  });
  syncIsolateToggle();
  const layoutEl = $("mainLayout");
  const setPanelCollapsed = (collapsed) => {
    layoutEl?.classList.toggle("panel-collapsed", !!collapsed);
    const exp = $("btnExpandPanel");
    const expTop = $("btnExpandPanelTop");
    if (exp) exp.hidden = !collapsed;
    if (expTop) expTop.hidden = !collapsed;
    setTimeout(() => {
      if (network && viewMode === "2d") {
        const c = $("network");
        const boxn = c.getBoundingClientRect();
        if (boxn.width >= 40 && boxn.height >= 40) {
          network.setSize(`${Math.floor(boxn.width)}px`, `${Math.floor(boxn.height)}px`);
          network.redraw();
        }
      }
    }, 40);
  };
  // Ensure we never boot into a stuck collapsed blank state
  setPanelCollapsed(false);
  $("btnCollapsePanel")?.addEventListener("click", () => setPanelCollapsed(true));
  $("btnExpandPanel")?.addEventListener("click", () => setPanelCollapsed(false));
  $("btnExpandPanelTop")?.addEventListener("click", () => setPanelCollapsed(false));
  // 折叠面板：点标题展开/收起
  document.querySelectorAll(".acc-toggle").forEach((t) => {
    t.addEventListener("click", () => t.parentElement.classList.toggle("open"));
  });
  // 一键清空「手动填写」的标题与文本
  $("btnClearAi")?.addEventListener("click", () => {
    const t = $("aiTitle"); if (t) t.value = "";
    const x = $("aiText"); if (x) x.value = "";
    const m = $("aiMsg"); if (m) { m.hidden = true; m.textContent = ""; }
  });
  // 视图与布局已移入侧栏手风琴（默认展开），无顶部工具条折叠逻辑
  const splitter = $("panelSplitter");
  if (splitter && layoutEl) {
    let dragging = false;
    splitter.addEventListener("mousedown", (ev) => {
      dragging = true;
      splitter.classList.add("dragging");
      ev.preventDefault();
    });
    window.addEventListener("mousemove", (ev) => {
      if (!dragging) return;
      const rect = layoutEl.getBoundingClientRect();
      const w = Math.min(560, Math.max(240, ev.clientX - rect.left));
      layoutEl.style.setProperty("--panel-w", `${w}px`);
      if (network && viewMode === "2d") {
        const c = $("network");
        const boxn = c.getBoundingClientRect();
        network.setSize(`${Math.floor(boxn.width)}px`, `${Math.floor(boxn.height)}px`);
        network.redraw();
      }
    });
    window.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      splitter.classList.remove("dragging");
    });
  }

  syncViewControls();
  updateGraphLegend();
  $("btnView2d").addEventListener("click", () => setViewMode("2d"));
  $("btnView3d").addEventListener("click", () => setViewMode("3d"));
  $("btnCloseDrawer").addEventListener("click", closeDrawer);
  $("btnFocusNode").addEventListener("click", () => {
    const vid = $("btnFocusNode").dataset.vid || detailVid;
    if (vid) showSubgraph(vid, { withDetail: true }).catch(alertError);
  });
  $("btnDeleteNode").addEventListener("click", () => deleteCurrentNode().catch(alertError));
  $("btnPath").addEventListener("click", () => runPathQuery().catch(alertError));
  $("btnAiExtract").addEventListener("click", () => runAiExtract());
  $("btnAiCommit").addEventListener("click", () => runAiCommit());
  $("btnBatchTemplate").addEventListener("click", showBatchTemplate);
  $("btnImportMd").addEventListener("click", importMdFile);
  $("btnLoadPreview").addEventListener("click", loadBatchToPreview);
  $("btnCollectRun")?.addEventListener("click", () => runCollect());
  $("btnCollectRefresh")?.addEventListener("click", () => loadCollectList());
  $("btnFetch")?.addEventListener("click", () => runFetchUrl());
  $("fetchUrl")?.addEventListener("keydown", (e) => { if (e.key === "Enter") runFetchUrl(); });
  $("btnLogin")?.addEventListener("click", () => { if (writeToken) logout(); else openLoginModal(""); });
  $("btnLoginOk")?.addEventListener("click", () => doLogin());
  $("btnLoginCancel")?.addEventListener("click", () => { const m = $("loginMask"); if (m) m.hidden = true; });
  $("loginPwd")?.addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
  $("btnUndo")?.addEventListener("click", () => doUndoRedo("/history/undo"));
  $("btnRedo")?.addEventListener("click", () => doUndoRedo("/history/redo"));
  $("btnTheme")?.addEventListener("click", () => applyTheme(isLightTheme() ? "dark" : "light"));
  $("btnAssistRefine").addEventListener("click", () => runFormAssist("refine"));
  $("btnAssistTranslate").addEventListener("click", () => runFormAssist("translate"));
  $("drawerBody").addEventListener("click", (e) => {
    const jump = e.target.closest("[data-jump-source]");
    if (jump) {
      e.preventDefault();
      e.stopPropagation();
      openSourceLink(jump).catch(alertError);
      return;
    }
    const del = e.target.closest("[data-del-edge]");
    if (del) {
      deleteEdgeFromDetail(del).catch(alertError);
      return;
    }
    const main = e.target.closest(".rel-main[data-vid]");
    if (main) {
      openDetail(main.dataset.vid, { focusGraph: false }).catch(alertError);
      return;
    }
  });
  $("keyword").addEventListener("keydown", (e) => {
    if (e.key === "Enter") searchNodes().catch(alertError);
  });
  $("nodeList").addEventListener("click", (e) => {
    const li = e.target.closest("li[data-vid]");
    if (!li) return;
    // List click: switch to 2D for a crisp highlight, then open detail / subgraph.
    focusIn2D(() => {
      if (overviewMode) {
        openDetail(li.dataset.vid, { focusGraph: false }).catch(alertError);
      } else {
        showSubgraph(li.dataset.vid, { withDetail: true }).catch(alertError);
      }
    });
  });
  $("addForm").addEventListener("submit", submitAdd);
  $("addLevel")?.addEventListener("change", syncAddNodeFields);
  $("exportEndMode")?.addEventListener("change", syncExportEndMode);
  $("exportToLevel")?.addEventListener("change", syncExportMeta);
  $("exportStart")?.addEventListener("input", () => {
    const n = exportNodeByName(($("exportStart")?.value || "").trim());
    rebuildExportToLevel(n ? n.tag : "");
    syncExportMeta();
  });
  $("exportEndNode")?.addEventListener("input", syncExportMeta);
  $("btnExport")?.addEventListener("click", exportKnowledge);
  $("btnImportLoadFile")?.addEventListener("click", loadImportFile);
  $("btnImportTemplate")?.addEventListener("click", downloadImportTemplate);
  $("btnImportCheck")?.addEventListener("click", importCheck);
  $("btnImportCommit")?.addEventListener("click", importCommit);
  $("btnRecentRefresh")?.addEventListener("click", loadPendingReview);
  $("btnRecentHighlight")?.addEventListener("click", toggleRecentHighlight);
  $("btnReviewConfirm")?.addEventListener("click", confirmReviewed);
  $("btnHistoryExport")?.addEventListener("click", exportHistoryRange);
  $("chkRecentHighlight")?.addEventListener("change", toggleRecentHighlight);
  loadPendingReview();
  reviewHighlightOn = $("chkRecentHighlight")?.checked ?? true;
  syncAddNodeFields();
  syncExportEndMode();  await loadArchSchema().catch(() => {});
  await Promise.all([refreshAll(), loadAiStatus(), refreshClusterOptions().catch(() => {})]);
  refreshClassificationTree().catch(() => {});
  syncAddNodeFields();
  initTheme();
  updateLoginButtons();
  if (document.activeElement && typeof document.activeElement.blur === "function") {
    document.activeElement.blur();
  }
}

async function refreshAll() {
  await loadStats();
  await searchNodes();
  await refreshClusterOptions().catch(() => {});
  if (overviewMode || !focusVid) {
    await showOverview();
  } else {
    await showSubgraph(focusVid, { withDetail: !!detailVid });
  }
}

function alertError(err) {
  console.error(err);
  setGraphHint(String(err.message || err), true);
}

boot().catch(alertError);
