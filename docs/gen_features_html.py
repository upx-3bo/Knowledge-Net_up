# -*- coding: utf-8 -*-
"""生成《功能清单_可编辑版.html》：把功能清单 md 解析为可编辑 HTML（contenteditable + localStorage）。"""
import io, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SRC = r"C:\Users\x30085681\Desktop\up_X\AI4KnowledgeNet\docs\功能清单.md"
OUT = r"C:\Users\x30085681\Desktop\up_X\AI4KnowledgeNet\docs\功能清单_可编辑版.html"

text = open(SRC, encoding="utf-8").read()
lines = text.splitlines()

sections = []
i, n = 0, len(lines)
while i < n:
    line = lines[i]
    if not line.strip():
        i += 1; continue
    m = re.match(r"^(#{1,3})\s+(.*)$", line)
    if m:
        sections.append({"type": f"h{len(m.group(1))}", "title": m.group(2).strip()}); i += 1; continue
    if line.lstrip().startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
        header = [c.strip() for c in line.strip().strip("|").split("|")]
        i += 2
        rows = []
        while i < n and lines[i].lstrip().startswith("|"):
            cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            if len(cells) >= 2:
                rows.append({"title": cells[0], "desc": cells[1]})
            i += 1
        sections.append({"type": "table", "title": header[0] if header else "功能", "rows": rows})
        continue
    if line.startswith("- ") or line.startswith("* "):
        items = []
        while i < n and (lines[i].startswith("- ") or lines[i].startswith("* ")):
            items.append(lines[i][2:].strip()); i += 1
        sections.append({"type": "list", "items": items}); continue
    if line.lstrip().startswith(">"):
        items = []
        while i < n and lines[i].lstrip().startswith(">"):
            items.append(lines[i].lstrip()[1:].strip()); i += 1
        sections.append({"type": "quote", "items": items}); continue
    buf = [line]; i += 1
    while i < n and lines[i].strip() and not lines[i].startswith(("#", "|", "- ", "* ", ">")):
        buf.append(lines[i]); i += 1
    sections.append({"type": "p", "text": " ".join(x.strip() for x in buf)})

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s

html = []
html.append("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI4KnowledgeNet 功能清单 · 使用手册（可编辑）</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Microsoft YaHei',system-ui,sans-serif;background:#f5f7fb;color:#2b3443;line-height:1.7;padding:0}
.wrap{max-width:960px;margin:0 auto;padding:36px 30px 80px;background:#fff;min-height:100vh;box-shadow:0 0 30px rgba(0,0,0,.06)}
.toolbar{position:sticky;top:0;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);border-bottom:1px solid #e2e8f0;padding:12px 0;margin-bottom:18px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;z-index:20}
.toolbar .lbl{font-size:13px;color:#64748b}
.toolbar button{background:#2563eb;border:1px solid #3b82f6;color:#fff;border-radius:6px;padding:6px 14px;font-size:13px;cursor:pointer}
.toolbar button.ghost{background:#fff;border-color:#cbd5e1;color:#334155}
.toolbar .status{font-size:12px;color:#16a34a}
h1{font-size:26px;color:#111827;margin:8px 0 4px}
h2{font-size:21px;color:#1d4ed8;border-left:5px solid #2563eb;padding-left:12px;margin:30px 0 14px}
h3{font-size:17px;color:#334155;margin:22px 0 8px}
p{margin:10px 0;color:#374151}
code{background:#eef2f7;border:1px solid #dbe2ec;border-radius:4px;padding:1px 6px;font-size:.9em;color:#b91c1c}
.quote{background:#eff6ff;border-left:4px solid #3b82f6;padding:10px 14px;border-radius:0 6px 6px 0;color:#1e3a8a;margin:10px 0}
.quote p{margin:0;color:inherit}
ul{margin:8px 0 8px 22px;color:#374151}
li{margin:4px 0}
.func{display:flex;gap:12px;align-items:flex-start;border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px;margin-bottom:8px;background:#fff}
.func .name{width:190px;flex-shrink:0;font-weight:600;color:#1e293b}
.func .body{flex:1}
.func .desc{color:#475569;font-size:14px}
.func .note{margin-top:6px;display:none}
.func .note.show-note{display:block}
[contenteditable]{outline:none}
.editing [contenteditable]{background:#f8fafc;border:1px solid #cbd5e1;border-radius:6px;padding:4px 6px;cursor:text}
.func .name[contenteditable], .func .desc[contenteditable]{transition:background .15s}
.func .note-input{width:100%;background:#fffbeb;border:1px dashed #d97706;border-radius:6px;padding:6px 8px;font-size:12.5px;color:#78350f;resize:vertical;font-family:inherit;min-height:22px}
.func .edited{font-size:11px;color:#d97706;margin-left:6px;display:none}
.func[data-edited="1"] .edited{display:inline}
hr{border:none;border-top:1px solid #e2e8f0;margin:24px 0}
a{color:#2563eb}
.tip{color:#94a3b8;font-size:12px}
</style></head><body><div class="wrap">
<div class="toolbar">
  <span class="lbl">使用手册（可编辑）</span>
  <button id="btnEdit" class="ghost" type="button">✎ 编辑模式</button>
  <button id="btnExport" class="ghost" type="button">⬇ 导出 JSON</button>
  <button id="btnReset" class="ghost" type="button">↺ 重置本页</button>
  <span class="status" id="status">仅查看（改动自动存本机）</span>
  <span class="tip">编辑模式下可直接改「功能 / 说明」，下方可加「备注」。点击空白添加备注。</span>
</div>
""")

for sec in sections:
    t = sec.get("type")
    if t == "h1":
        html.append(f'<h1>{inline(sec["title"])}</h1>')
    elif t == "h2":
        html.append(f'<h2>{inline(sec["title"])}</h2>')
    elif t == "h3":
        html.append(f'<h3>{inline(sec["title"])}</h3>')
    elif t == "table":
        html.append('<div class="funcs">')
        for idx, row in enumerate(sec["rows"]):
            uid = f"{sec.get('title','')}|{idx}"
            html.append(f'''<div class="func" data-uid="{esc(uid)}" data-edited="0">
  <div class="name" contenteditable="false">{inline(row["title"])}</div>
  <div class="body">
    <div class="desc" contenteditable="false">{inline(row["desc"])}</div>
    <div class="note"><textarea class="note-input" placeholder="＋ 添加备注…（点击输入）"></textarea></div>
    <span class="edited">已改</span>
  </div>
</div>''')
        html.append('</div>')
    elif t == "list":
        html.append('<ul>' + "".join(f'<li>{inline(x)}</li>' for x in sec["items"]) + '</ul>')
    elif t == "quote":
        html.append('<div class="quote">' + "".join(f'<p>{inline(x)}</p>' for x in sec["items"]) + '</div>')
    elif t == "p":
        html.append(f'<p>{inline(sec["text"])}</p>')

html.append("""
<div style="margin-top:40px;padding-top:16px;border-top:1px solid #e2e8f0;color:#94a3b8;font-size:12px;text-align:center">
AI4KnowledgeNet 知识图谱工作台 · 功能清单与使用手册（可编辑版，修改自动存本机浏览器）</div>
</div>

<script>
const KEY = "akn_features_v1";
let edits = {};
try { edits = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch(e){ edits = {}; }
let editing = false;
const $ = (id) => document.getElementById(id);

function clamp(s){ return (s||"").replace(/\\s+/g," ").trim(); }

function noteInput(el){ return el.querySelector(".note-input"); }

function syncNote(el){
  const d = edits[el.dataset.uid] || {};
  const hasNote = !!(d.note);
  const noteEl = el.querySelector(".note");
  // 非编辑模式：有备注才显示；编辑模式：全部显示以添加新备注
  noteEl.classList.toggle("show-note", editing || hasNote);
}
function refreshNotes(){
  document.querySelectorAll(".func").forEach(syncNote);
}
function applyEdits(){
  document.querySelectorAll(".func").forEach(el=>{
    const d = edits[el.dataset.uid] || {};
    if (d.name != null) el.querySelector(".name").textContent = d.name;
    if (d.desc != null) el.querySelector(".desc").textContent = d.desc;
    const ta = noteInput(el); ta.value = d.note || "";
    el.dataset.edited = (d.name||d.desc||d.note) ? "1" : "0";
  });
  refreshNotes();
}
function markEdited(el){
  const d = edits[el.dataset.uid] || (edits[el.dataset.uid] = {});
  d.name = clamp(el.querySelector(".name").textContent);
  d.desc = clamp(el.querySelector(".desc").textContent);
  d.note = clamp(noteInput(el).value);
  el.dataset.edited = (d.name||d.desc||d.note) ? "1" : "0";
  localStorage.setItem(KEY, JSON.stringify(edits));
  syncNote(el);
}
function toggleEdit(){
  editing = !editing;
  document.body.classList.toggle("editing", editing);
  $("btnEdit").textContent = editing ? "✓ 完成编辑" : "✎ 编辑模式";
  $("status").textContent = editing ? "编辑中：直接改功能/说明文字；下方备注可加。改动自动保存" : "仅查看（改动自动存本机）";
  document.querySelectorAll(".func").forEach(el=>{
    el.querySelector(".name").setAttribute("contenteditable", String(editing));
    el.querySelector(".desc").setAttribute("contenteditable", String(editing));
  });
  refreshNotes();
}
$("btnEdit").addEventListener("click", toggleEdit);
document.addEventListener("input", (e)=>{
  const el = e.target.closest ? e.target.closest(".func") : null;
  if (el) markEdited(el);
});
document.addEventListener("blur", (e)=>{
  const el = e.target.closest ? e.target.closest(".func") : null;
  if (el) markEdited(el);
}, true);
$("btnExport").addEventListener("click", ()=>{
  const out = {};
  document.querySelectorAll(".func").forEach(el=>{ out[el.dataset.uid] = edits[el.dataset.uid] || {}; });
  const blob = new Blob([JSON.stringify(out,null,2)], {type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="features_edits.json"; a.click();
});
$("btnReset").addEventListener("click", ()=>{
  if(confirm("重置本页所有修改（恢复为原始功能说明）？")){ localStorage.removeItem(KEY); edits={}; applyEdits(); }
});
applyEdits();
</script>
</body></html>
""")

open(OUT, "w", encoding="utf-8").write("".join(html))
print("生成:", OUT, f"({len(''.join(html))} 字节)")
