# -*- coding: utf-8 -*-
# ECharts · 知识图谱可视化（针对你提出的3点修复版｜防抖动）
# ① 线条样式更顺滑（直线、柔和颜色）
# ② 力导向参数防“粘团”（repulsion↑，edgeLength区间）
# ③ 指标视图点击指标 → 反查“案例→对应→该指标”的所有案例，并合并这些案例的整条问题链
# ④ 主题切换移除，默认亮色

from py2neo import Graph
import os, json, math, traceback, io, re

# ===== 连接参数 =====
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "dsm123456")
NEO4J_DB   = os.getenv("NEO4J_DB", "neo4j")

def read_echarts_inline():
    for p in ["echarts.min.js", os.path.join(os.path.dirname(__file__), "echarts.min.js")]:
        try:
            with io.open(p, "r", encoding="utf-8") as f:
                return f.read()
        except:
            pass
    return ""
EJS = read_echarts_inline()

# ===== 拉 Neo4j 数据（带 DISTINCT 去重） =====
diag_error, node_total, rel_total = "", 0, 0
rows = []
try:
    graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS), name=NEO4J_DB)
    node_total = int(graph.run("MATCH (n) RETURN count(n)").evaluate() or 0)
    rel_total  = int(graph.run("MATCH ()-[r]->() RETURN count(r)").evaluate() or 0)
    if rel_total > 0:
        rows = list(graph.run("""
            MATCH (a)-[r]->(b)
            RETURN DISTINCT id(a) AS aid, a, TYPE(r) AS rt, id(b) AS bid, b
        """))
except Exception as e:
    diag_error = f"{type(e).__name__}: {e}"
    traceback.print_exc()

def label_of(n):
    for k in ("name","desc","code","title"):
        v = n.get(k)
        if isinstance(v,str) and v.strip():
            return v.strip()
    labs = list(n.labels)
    return labs[0] if labs else "节点"

def group_of(n):
    wanted = {"Center","Indicator","Case","Problem","Action","Result","Reflection","Stage","Role","Project"}
    labs = list(n.labels)
    for lab in labs:
        if lab in wanted: return lab
    return "Other"

# ===== 构建（含“属于”连通过滤） =====
NODES, LINKS, DEG = {}, [], {}
CENTER_IDS = set()
CODE_RE = re.compile(r"^\d+(?:\.\d+)*")

if rows:
    SEEN = set()
    for row in rows:
        aid, a = row["aid"], row["a"]
        bid, b = row["bid"], row["b"]
        rt     = row["rt"]

        if aid not in NODES:
            full = label_of(a); grp = group_of(a)
            code = CODE_RE.match(full).group(0) if grp=="Indicator" and CODE_RE.match(full) else ""
            NODES[aid] = {"id": str(aid), "full": full, "group": grp, "code": code}
            if grp == "Center": CENTER_IDS.add(str(aid))
        if bid not in NODES:
            full = label_of(b); grp = group_of(b)
            code = CODE_RE.match(full).group(0) if grp=="Indicator" and CODE_RE.match(full) else ""
            NODES[bid] = {"id": str(bid), "full": full, "group": grp, "code": code}
            if grp == "Center": CENTER_IDS.add(str(bid))

        key = (str(aid), str(bid), rt)
        if key not in SEEN:
            SEEN.add(key)
            LINKS.append({"source": str(aid), "target": str(bid), "rt": rt})
            DEG[aid] = DEG.get(aid,0)+1
            DEG[bid] = DEG.get(bid,0)+1

# 可选的“属于”连通：剔除不挂在中心下的脏指标
allowed_indicator_ids = set()
if CENTER_IDS:
    belongs_adj = {}
    def add_adj(u,v):
        belongs_adj.setdefault(u, []).append(v)
    for e in LINKS:
        if e["rt"] == "属于":
            add_adj(e["source"], e["target"])
            add_adj(e["target"], e["source"])
    vis = set(CENTER_IDS); q = list(CENTER_IDS)
    while q:
        u = q.pop(0)
        for v in belongs_adj.get(u, []):
            if v not in vis:
                vis.add(v); q.append(v)
    for nid in vis:
        try:
            nd = NODES.get(int(nid))
            if nd and nd["group"] == "Indicator":
                allowed_indicator_ids.add(str(int(nid)))
        except:
            pass

if allowed_indicator_ids:
    keep_nodes = set()
    for k, nd in NODES.items():
        if nd["group"] != "Indicator" or nd["id"] in allowed_indicator_ids:
            keep_nodes.add(nd["id"])
    NODES = {int(nid): nd for nid, nd in NODES.items() if nd["id"] in keep_nodes}
    LINKS = [e for e in LINKS if (e["source"] in keep_nodes and e["target"] in keep_nodes)]
    DEG = {}
    for e in LINKS:
        a = int(e["source"]); b = int(e["target"])
        DEG[a] = DEG.get(a,0)+1
        DEG[b] = DEG.get(b,0)+1

# ===== 配色与分类 =====
ORDER = ["Center","Indicator","Case","Problem","Action","Result","Reflection","Stage","Role","Project","Other"]
CN    = {"Center":"指标中心","Indicator":"能力指标","Case":"案例","Problem":"问题","Action":"解决方法",
         "Result":"整改结果","Reflection":"反思","Stage":"试验阶段","Role":"岗位职责","Project":"试验项目","Other":"其他"}
COLOR = {
    "Center":    "#FFE082",  # 原 #FFC107 → 更浅的琥珀
    "Indicator": "#A7C5EB",  # 原 #4E79A7 → 浅蓝
    "Case":      "#F9C99B",  # 原 #F28E2B → 浅橙
    "Problem":   "#F4A6A6",  # 原 #E15759 → 浅红
    "Action":    "#A8DADC",  # 原 #76B7B2 → 浅青
    "Result":    "#A9D6A4",  # 原 #59A14F → 浅绿
    "Reflection":"#F6E08D",  # 原 #EDC948 → 浅黄
    "Stage":     "#D5B3D8",  # 原 #B07AA1 → 浅紫
    "Role":      "#FFC2CC",  # 原 #FF9DA7 → 浅粉
    "Project":   "#C9B6A3",  # 原 #9C755F → 浅棕
    "Other":     "#C0D1D1"   # 原 #93A1A1 → 浅灰蓝
}


present = set(nd["group"] for nd in NODES.values())
ORDER_USED = [k for k in ORDER if k in present]
cat_index = {k:i for i,k in enumerate(ORDER_USED)}
categories = [{"name": CN[k], "key": k, "itemStyle":{"color": COLOR[k]}} for k in ORDER_USED]

def short6(s):  # 指标只显示编号；其它显示前6字
    return (s or "").replace(" ", "").replace("\n","")[:6] or "—"

nodes_e = []
for nid, nd in NODES.items():
    deg = DEG.get(int(nid),1)
    size = max(34, min(52, round(3.8*math.sqrt(deg) + 22)))
    show = nd["code"] if nd["group"]=="Indicator" and nd["code"] else short6(nd["full"])
    nodes_e.append({
        "id": nd["id"], "name": show, "full": nd["full"], "group": nd["group"],
        "category": cat_index[nd["group"]],
        "symbol": "circle", "symbolSize": size,
        "itemStyle": {"color": COLOR[nd["group"]]}
    })
links_e = LINKS

# ===== HTML =====
inline_echarts = f"<script>\n{EJS}\n</script>" if EJS else ""
html = f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>知识图谱</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    /* 直接使用亮色主题变量 */
    --bg:#F8FAFC; --panel:#FFFFFF; --border:#E5E7EB; --shadow:rgba(0,0,0,.08);
    --text:#111827; --accent:#355C8A;
  }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Microsoft YaHei"; }}
  .topbar {{ position:sticky; top:0; z-index:3; display:flex; gap:12px; align-items:center; padding:10px 14px; background:var(--panel); border-bottom:1px solid var(--border); }}
  .brand{{ font-weight:700; margin-right:8px; }}
  .search {{ flex:1; display:flex; gap:8px; }}
  .search input{{ flex:1; padding:8px 10px; border-radius:10px; border:1px solid var(--border); background:var(--bg); color:var(--text); box-shadow:0 1px 0 var(--shadow) inset; }}
  .btn{{ padding:6px 10px; border-radius:10px; border:1px solid var(--border); background:var(--panel); cursor:pointer; color:var(--text); box-shadow:0 2px 8px var(--shadow); }}
  .btn:hover{{ border-color:var(--accent); }}

  #kg{{ width:100%; height: calc(100vh - 56px); }}

  /* 顶部横向图例（保持原样） */
  .legend-bar {{
    position:absolute; left:50%; transform:translateX(-50%);
    top:12px; z-index:2; background:var(--panel); border:1px solid var(--border);
    border-radius:12px; padding:6px 10px; display:flex; align-items:center; gap:10px;
    white-space:nowrap; overflow-x:auto; overflow-y:hidden; max-width:88vw; scrollbar-width:thin;
  }}
  .legend-item{{ display:inline-flex; align-items:center; gap:6px; font-size:12px; padding:2px 8px; border:1px solid var(--border); border-radius:999px; background:rgba(0,0,0,0.02); }}
  .dot{{ width:10px;height:10px;border-radius:50%;display:inline-block; box-shadow:0 0 0 1px var(--border) inset; }}

  /* 左下详情（保持不变） */
  #detail{{ position:absolute; left:10px; bottom:10px; width:440px; max-height:44vh; overflow:auto; background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:10px; z-index:2; box-shadow:0 6px 24px var(--shadow); }}
  #detail h4{{ margin:0 0 8px 0; font-size:14px; display:flex; justify-content:space-between; align-items:center; }}
  #detail table{{ width:100%; font-size:13px; border-collapse:collapse; }}
  #detail th{{ width:92px; color:#6B7280; text-align:left; padding:6px; }}
  #detail td{{ padding:6px; color:var(--text); }}
  #detail.collapsed table{{ display:none; }}

  .count{{ position:absolute; left:10px; top:10px; padding:6px 10px; font-size:12px; border:1px solid var(--border); border-radius:10px; background:var(--panel); z-index:2; box-shadow:0 4px 16px var(--shadow); }}
</style>
</head>
<body class="light">
<div class="topbar">
  <div class="brand">知识图谱</div>
  <div class="search">
    <input id="q" placeholder="搜索关键词 / 案例编号 / 指标编号(如 2.1.1 )">
    <button class="btn" onclick="doSearch()">搜索</button>
  </div>
  <button class="btn" onclick="viewAll()">全图</button>
  <button class="btn" onclick="indicatorView()">指标视图</button>
  <button class="btn" onclick="caseView()">案例视图</button>
  <button class="btn" onclick="exportPNG()">导出PNG</button>
  <button class="btn" onclick="undoView()">⟲ 上一步</button>
  <button class="btn" onclick="redoView()">下一步 ⟳</button>
  <!-- 移除主题切换按钮 -->
</div>

<div style="position:relative">
  <div id="legendBar" class="legend-bar">
    {"".join([f'<div class="legend-item"><span class="dot" style="background:{COLOR[k]};"></span>{CN[k]}</div>' for k in ORDER_USED])}
  </div>

  <div id="kg"></div>
  <div id="count" class="count">节点 {node_total} · 关系 {rel_total}</div>

  <div id="detail">
    <h4>具体内容 <button id="detailBtn" class="btn" style="padding:2px 8px" onclick="toggleDetail()">▾</button></h4>
    <table>
      <tr><th>类别</th><td>点击节点查看</td></tr>
      <tr><th>短标签</th><td>—</td></tr>
      <tr><th>完整文本</th><td>—</td></tr>
    </table>
  </div>
</div>

{inline_echarts}
{"<script src='echarts.min.js'></script>" if not EJS else ""}

<script>
const DATA = {{
  nodes: {json.dumps(nodes_e, ensure_ascii=False)},
  links: {json.dumps(links_e, ensure_ascii=False)},
  categories: {json.dumps(categories, ensure_ascii=False)},
  cnMap: {json.dumps(CN, ensure_ascii=False)}
}};

/* ========= Tooltip 自动换行 ========= */
function wrapText(s, limit=12){{
  if(!s) return '';
  const arr = Array.from(String(s));
  let out = '', cnt = 0;
  for(const ch of arr){{ out += ch; if(++cnt >= limit){{ out += '<br/>'; cnt = 0; }} }}
  return out;
}}

/* ========= 有/无向邻接 ========= */
const OUT = (() => {{
  const m = {{}};
  for (const e of DATA.links) {{
    (m[e.source]||(m[e.source]=[])).push({{v:e.target, rt:e.rt}});
  }}
  return m;
}})();
const UND = (() => {{
  const a = {{}};
  for(const e of DATA.links){{
    (a[e.source]||(a[e.source]=[])).push(e.target);
    (a[e.target]||(a[e.target]=[])).push(e.source);
  }}
  return a;
}})();

/* ========= 从案例构建“问题链”子图 ========= */
function buildCaseSubgraph(caseId){{
  const keep = new Set([caseId]);
  for(const nb of (UND[caseId]||[])) keep.add(nb);
  const byId = Object.fromEntries(DATA.nodes.map(n=>[n.id,n]));
  const direct = (OUT[caseId]||[]);
  const problems = direct.filter(x=> byId[x.v] && byId[x.v].group==='Problem');

  // 问题 → 采用 → 产生（结果）
  for(const p of problems){{
    keep.add(p.v);
    const a1 = (OUT[p.v]||[]).find(x=> x.rt==='采用' && byId[x.v] && byId[x.v].group==='Action');
    if(a1) keep.add(a1.v);
    if(a1){{
      const r1 = (OUT[a1.v]||[]).find(x=> x.rt==='产生' && byId[x.v] && byId[x.v].group==='Result');
      if(r1) keep.add(r1.v);
    }}
  }}

  // 反思：由 案例 —形成→ 反思
  const refls = direct.filter(x=> x.rt==='形成' && byId[x.v] && byId[x.v].group==='Reflection');
  for (const f of refls) keep.add(f.v);

  const allowed = new Set(['对应','处于','涉及','来源','出现','采用','产生','形成','属于']);
  const nodes = DATA.nodes.filter(n=> keep.has(n.id));
  const keepSet = new Set(nodes.map(n=>n.id));
  const links = DATA.links.filter(e=> keepSet.has(e.source) && keepSet.has(e.target) && allowed.has(e.rt));
  return {{nodes, links}};
}}

/* ========= 撤销/重做 & 计数 ========= */
const historyStack = [];
const futureStack  = [];
function snapshot(){{
  const opt = chart.getOption(); if(!opt||!opt.series||!opt.series[0]) return null;
  const s = opt.series[0];
  return {{
    nodes:(s.data||[]).map(n=>({{id:n.id,name:n.name,full:n.full,group:n.group,category:n.category,symbol:'circle',symbolSize:n.symbolSize,itemStyle:n.itemStyle}})),
    links:(s.links||[]).map(e=>({{source:e.source,target:e.target,rt:e.rt}}))
  }};
}}
function saveState(){{
  const snap = snapshot(); if(snap){{ historyStack.push(snap); futureStack.length=0; }}
}}
function applyState(st){{
  render(st.nodes, st.links, true);
}}
function undoView(){{
  if(!historyStack.length) return;
  const cur=snapshot(), prev=historyStack.pop();
  if(cur) futureStack.push(cur); applyState(prev);
}}
function redoView(){{
  if(!futureStack.length) return;
  const cur=snapshot(), nxt=futureStack.pop();
  if(cur) historyStack.push(cur); applyState(nxt);
}}
function updateCount(nodes, links){{
  document.getElementById('count').innerText = `节点 ${{nodes.length}} · 关系 ${{links.length}}`;
}}

/* ========= 线条样式：直线 + 柔和色 ========= */
function edgeStyle(){{
  return {{
    width:0.9, opacity:0.7, curveness:0.0,
    color:'#B8BFC7'
  }};
}}

/* ========= 渲染/主题 ========= */
let chart, theme='light', mode='all';

function currentTextColor(){{
  return getComputedStyle(document.body).getPropertyValue('--text').trim();
}}

function render(nodes, links, keepLayout=false){{
  const series = [{{
    type:'graph',
    layout:'force',
    data: nodes,
    links: links,
    categories: DATA.categories,
    roam:true, draggable:true, animation:false,
    lineStyle: edgeStyle(),
    edgeSymbol:['none','arrow'], edgeSymbolSize:6,
    emphasis: {{ focus:'adjacency' }},
    label: {{
      show:true, position:'inside',
      color: currentTextColor(),
      fontWeight: 'bold',
      fontSize: 12,
      formatter: '{{b}}'
    }},
    force: {{
      repulsion: 720,
      gravity: 0.05,
      edgeLength: [60, 120]
    }}
  }}];
  const opt = {{
    backgroundColor: getComputedStyle(document.body).getPropertyValue('--bg').trim(),
    tooltip: {{
      confine:true,
      backgroundColor: getComputedStyle(document.body).getPropertyValue('--panel').trim(),
      borderColor: getComputedStyle(document.body).getPropertyValue('--border').trim(),
      textStyle: {{ color: getComputedStyle(document.body).getPropertyValue('--text').trim() }},
      formatter: p => p.dataType==='node'
        ? `<div style="max-width:960px;line-height:1.7">${{wrapText(p.data.full,12)}}</div>`
        : '关系：'+(p.data.rt||'→')
    }},
    series: series
  }};
  chart.setOption(opt, !keepLayout);
  updateCount(nodes, links);
}}

function applyTheme(mode){{
  // 固定为亮色，仅刷新颜色，不改布局
  chart.setOption({{
    backgroundColor: getComputedStyle(document.body).getPropertyValue('--bg').trim(),
    tooltip: {{
      backgroundColor: getComputedStyle(document.body).getPropertyValue('--panel').trim(),
      borderColor: getComputedStyle(document.body).getPropertyValue('--border').trim(),
      textStyle: {{ color: getComputedStyle(document.body).getPropertyValue('--text').trim() }}
    }},
    series:[{{
      lineStyle: edgeStyle(),
      label: {{ color: currentTextColor() }}
    }}]
  }}, false);
}}

function init(){{
  chart = echarts.init(document.getElementById('kg'));
  render(DATA.nodes, DATA.links);
  applyTheme(theme); // 固定亮色
  bindEvents();
}}
window.addEventListener('resize', () => chart && chart.resize());

/* ========= 交互 ========= */
function bindEvents(){{
  chart.on('click', (p) => {{
    if(p.dataType!=='node') return;
    const n = p.data, gname = DATA.cnMap ? (DATA.cnMap[n.group]||'其他') : n.group;
    document.querySelector('#detail table').innerHTML =
      `<tr><th>类别</th><td>${{gname}}</td></tr>`+
      `<tr><th>短标签</th><td>${{n.name}}</td></tr>`+
      `<tr><th>完整文本</th><td>${{n.full}}</td></tr>`;

    // 案例视图：点击案例 → 展开整条问题链
    if((mode==='case' || mode==='case-focus') && n.group==='Case'){{
      saveState();
      const sub = buildCaseSubgraph(n.id);
      render(sub.nodes, sub.links);
      mode = 'case-focus';
      const idx = sub.nodes.findIndex(x=>x.id===n.id);
      chart.dispatchAction({{type:'downplay',seriesIndex:0}});
      if(idx>=0){{
        chart.dispatchAction({{type:'highlight',seriesIndex:0,dataIndex:idx}});
        chart.dispatchAction({{type:'showTip',seriesIndex:0,dataIndex:idx}});
      }}
    }}

    // 指标视图：点击“指标” → 合并相关案例的整条问题链
    if(mode==='indicator' && n.group==='Indicator'){{
      saveState();
      const caseEdges = DATA.links.filter(e => e.rt==='对应' && e.target===n.id);
      const caseIds   = Array.from(new Set(caseEdges.map(e=>e.source)));
      const nodeMap = new Map(); const linkKey = new Set(); const linksAcc = [];
      nodeMap.set(n.id, n);
      for(const cid of caseIds){{
        const sub = buildCaseSubgraph(cid);
        for(const nd of sub.nodes) nodeMap.set(nd.id, nd);
        for(const lk of sub.links){{
          const k = lk.source+'|'+lk.target+'|'+(lk.rt||'');
          if(!linkKey.has(k)){{ linkKey.add(k); linksAcc.push(lk); }}
        }}
      }}
      const nodesAcc = Array.from(nodeMap.values());
      render(nodesAcc, linksAcc);
      const ii = nodesAcc.findIndex(x=>x.id===n.id);
      chart.dispatchAction({{type:'downplay',seriesIndex:0}});
      if(ii>=0){{
        chart.dispatchAction({{type:'highlight',seriesIndex:0,dataIndex:ii}});
        chart.dispatchAction({{type:'showTip',seriesIndex:0,dataIndex:ii}});
      }}
    }}
  }});
}}

/* ========= 顶栏功能 ========= */
function viewAll(){{
  mode='all';
  saveState();
  render(DATA.nodes, DATA.links);
}}
function doSearch(){{
  const q=(document.getElementById('q').value||'').trim().toLowerCase();
  if(!q) return;
  const idx=DATA.nodes.findIndex(n => (n.full||'').toLowerCase().includes(q) || (n.name||'').toLowerCase().includes(q));
  if(idx>=0){{
    chart.dispatchAction({{type:'downplay',seriesIndex:0}});
    chart.dispatchAction({{type:'highlight',seriesIndex:0,dataIndex:idx}});
    chart.dispatchAction({{type:'showTip',seriesIndex:0,dataIndex:idx}});
  }}
}}
function indicatorView(){{
  mode='indicator';
  saveState();
  const keep = new Set(DATA.nodes.filter(n => n.group==='Indicator' || n.group==='Center').map(n=>n.id));
  const nodes = DATA.nodes.filter(n => keep.has(n.id));
  const keepSet = new Set(nodes.map(n=>n.id));
  const links = DATA.links.filter(e => keepSet.has(e.source) && keepSet.has(e.target));
  render(nodes, links);
  const centerIdx = nodes.findIndex(n => n.group==='Center' && (n.full||'').includes('CRC实践核心能力评价指标'));
  if(centerIdx >= 0){{
    chart.dispatchAction({{type:'highlight', seriesIndex:0, dataIndex:centerIdx}});
    chart.dispatchAction({{type:'showTip', seriesIndex:0, dataIndex:centerIdx}});
  }}
}}
function caseView(){{
  const q=(document.getElementById('q').value||'').trim().toLowerCase();
  if(q){{
    saveState();
    const target = DATA.nodes.find(n => n.group==='Case' && (n.full||'').toLowerCase().includes(q));
    if(!target) return;
    const sub = buildCaseSubgraph(target.id);
    render(sub.nodes, sub.links);
    mode='case-focus';
    const idx = sub.nodes.findIndex(x => x.id===target.id);
    if(idx>=0){{
      chart.dispatchAction({{type:'highlight',seriesIndex:0,dataIndex:idx}});
      chart.dispatchAction({{type:'showTip',seriesIndex:0,dataIndex:idx}});
    }}
  }} else {{
    saveState();
    mode='case';
    const nodes = DATA.nodes.filter(n=>n.group==='Case');
    render(nodes, []);   // 只显示案例；点击案例再展开
  }}
}}
function exportPNG(){{
  const bg=getComputedStyle(document.body).getPropertyValue('--bg').trim();
  const url=chart.getDataURL({{type:'png', pixelRatio:2, backgroundColor:bg}});
  const a=document.createElement('a'); a.href=url; a.download='knowledge_graph.png'; a.click();
}}
function toggleDetail(){{
  const box = document.getElementById('detail');
  const btn = document.getElementById('detailBtn');
  box.classList.toggle('collapsed');
  btn.innerText = box.classList.contains('collapsed') ? '▸' : '▾';
}}

init();
</script>
</body>
</html>
"""

with open("../scripts/knowledge_graph.html", "w", encoding="utf-8") as f:
    f.write(html)

print("✅ 已生成 knowledge_graph.html（默认亮色，已移除主题切换）")
