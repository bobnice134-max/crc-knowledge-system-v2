# -*- coding: utf-8 -*-
# CRC实践核心能力智能评估系统 · 指标驱动讲评与复训（题面隐指标 / 紧凑讲评 / 选项均衡 / 交卷锁卷 / 覆盖7大一级）

import os
import re
import sys
import json
import csv
import random
import hashlib
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px

# ==== 可选：如你安装并运行了 Ollama，本地 LLM 问答会更强 ====
try:
    import ollama  # type: ignore
    HAVE_OLLAMA = True
except Exception:
    HAVE_OLLAMA = False

# ---------------- 页面基本设置（必须在任何 st.* 之前） ----------------
st.set_page_config(
    page_title="CRC实践核心能力智能评估系统",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"Get help": None, "Report a Bug": None, "About": None},
)

st.markdown('''
<style>
/* 固定显示侧栏，不可折叠 */
[data-testid="stSidebar"] {
    visibility: visible !important;
    display: block !important;
    opacity: 1 !important;
    position: relative !important;
    transform: none !important;
    min-width: 260px !important;
    max-width: 300px !important;
    z-index: 100 !important;
}

/* 隐藏左上角折叠按钮（全兼容写法） */
button[title*="收起"], button[title*="折叠"],
button[aria-label*="收起"], button[aria-label*="折叠"],
button[title*="collapse"], button[aria-label*="collapse"],
[data-testid="collapsedControl"],
[aria-label="Toggle sidebar"],
button:has(svg[data-testid="stIconCaretLeft"]),
button:has(svg[data-testid="stIconDoubleCaretLeft"]),
div[data-testid="stSidebarHeader"] button {
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
}

/* 页面顶部与表格样式微调 */
header { visibility: hidden; }
section[data-testid="stSidebarContent"] { padding-top: 0.5rem; }
.stDataFrame td div {
    white-space: normal !important;
    overflow-wrap:anywhere !important;
    line-height:1.5;
}
</style>
''', unsafe_allow_html=True)

# ---- Streamlit 兼容 rerun（新旧版本都能用）----
def _st_rerun():
    try:
        if hasattr(st, "rerun"):
            st.rerun()
    except Exception:
        pass

# 让同目录模块可导入（auth_code.py）
sys.path.insert(0, os.path.dirname(__file__))
from auth_code import require_login, login_status_bar, is_logged_in

# ---------------- 基础路径 ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # 自动定位当前文件所在路径
DATA_XLSX = os.path.join(BASE_DIR, "..", "data", "cases.xlsx") # 向上一级找到 data 文件夹
GRAPH_HTML = os.path.join(BASE_DIR, "knowledge_graph.html")    # 当前目录下的 HTML 文件
RESULTS_CSV = os.path.join(BASE_DIR, "results.csv")            # 兼容旧版（已由 user_paths 替代）
RESULTS_DIR = os.path.join(BASE_DIR, "results_runs")           # 兼容旧版（已由 user_paths 替代）

# ====【新增】每个用户的独立存储路径 ====
def _current_user():
    return st.session_state.get("auth_user", {})  # {"user_id","name","role"}

def user_paths():
    """返回当前登录用户的数据根目录/成绩CSV/明细目录/问答日志"""
    u = _current_user()
    uid = (u.get("user_id") or "anon").strip()
    root = os.path.join(BASE_DIR, "user_data", uid)  # 形如 app/user_data/001/
    return {
        "uid": uid,
        "root": root,
        "results_csv": os.path.join(root, "results.csv"),
        "results_dir": os.path.join(root, "results_runs"),
        "qa_log": os.path.join(root, "qa_log.jsonl"),
    }

# 仅保留一处登录门栓（未登录直接 stop，不渲染下方内容）
require_login("users.json")
if not is_logged_in():
    st.stop()

# ---------------- 主题与全局样式（固定亮色 + 紧凑讲评卡） ----------------
def inject_theme_css():
    bg, panel, border, text, accent, table_bg, hint = \
        "#F8FAFC", "#FFFFFF", "#E5E7EB", "#111827", "#355C8A", "#FFFFFF", "#6B7280"
    st.markdown(f"""
    <style>
      html, body, [data-testid="stAppViewContainer"]{{background:{bg};color:{text};font-family:"Microsoft YaHei",Inter,system-ui,-apple-system,Segoe UI,Roboto,"Helvetica Neue",Arial,"PingFang SC","Noto Sans SC","Source Han Sans SC",sans-serif}}
      .soft-panel{{background:{panel};border:1px solid {border};border-radius:14px;padding:16px;box-shadow:0 6px 24px rgba(0,0,0,.08)}}
      .section-title{{font-size:28px;font-weight:800;margin:12px 0 8px}}
      .question-card{{background:{panel};border:1px solid {border};border-radius:14px;padding:16px;margin-bottom:14px}}
      .question-title{{font-size:18px;font-weight:700;margin-bottom:10px}}
      .stDataFrame thead tr th{{background:{table_bg};color:{text}}}
      .review-card{{background:{panel};border:1px solid {border};border-radius:12px;padding:10px 12px;margin-bottom:10px;font-size:15px;line-height:1.65}}
      .review-hd{{font-weight:700}}
      .muted{{color:{hint}}}
      .chat-wrap {{ display:flex; flex-direction:column; gap:12px; }}
      .bubble {{
        max-width: 80%; padding: 10px 14px; border-radius:14px; line-height:1.6;
        border:1px solid {border}; box-shadow:0 3px 14px rgba(0,0,0,.06);
      }}
      .bubble-user {{ align-self:flex-end; background:#EEF2FF; border-color:#C7D2FE; }}
      .bubble-bot  {{ align-self:flex-start; background:{panel}; }}
    </style>
    """, unsafe_allow_html=True)
inject_theme_css()

# ---------------- 读取数据（优化：预建搜索列 _search_blob） ----------------
@st.cache_data(show_spinner=False)
def load_cases(path):
    need = ["案例", "能力指标", "试验项目", "试验阶段", "岗位职责", "问题", "解决方法", "整改结果", "反思"]
    if not os.path.exists(path):
        df = pd.DataFrame({c: [] for c in need})
        df["_search_blob"] = ""
        return df[need + ["_search_blob"]].copy()

    df = pd.read_excel(path)
    for c in need:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].fillna("").astype(str)
    df["_search_blob"] = (df["案例"] + " " + df["能力指标"] + " " + df["试验项目"] + " " + df["试验阶段"] + " " + df["问题"]).str.lower()
    return df[need + ["_search_blob"]].copy()

df = load_cases(DATA_XLSX)
if len(df) == 0:
    st.warning(f"未找到案例库文件：{DATA_XLSX}。请先上传/放置该文件。")

# ---------------- 工具函数 ----------------
def shorten(s, n=80):
    s = str(s or "").strip()
    return s if len(s) <= n else s[:n-1] + "…"

def parse_indicator(text):
    """从'能力指标'解析编号和名称，支持多种写法：'5.2.3 XXX' / 'XXX(5.2.3)' / 'XXX'"""
    t = str(text).strip()
    if not t: return "", ""
    m = re.search(r'(\d+(?:\.\d+){0,3})', t)
    id_ = m.group(1) if m else ""
    name = re.sub(r'^\s*\d+(?:\.\d+){0,3}\s*[-．。\s]*', '', t)
    name = re.sub(r'[\(（]\s*\d+(?:\.\d+){0,3}\s*[\)）]', '', name).strip()
    return id_, name or t

def parse_first_level(id_str: str) -> str:
    """从 '5.2.3' 取一级 '5'；不合法则返空"""
    m = re.match(r'^\s*(\d+)', str(id_str).strip())
    return m.group(1) if m else ""

ERROR_CATS = ["延后处理", "口头代替", "越权修改", "不留痕或不同步"]

def pick_error_distractors(rng: random.Random):
    return rng.sample(ERROR_CATS, 3)

def _normalize_end_punct(s: str) -> str:
    return re.sub(r'[。；;.\s]+$', '', s)

def _stable_seed(*parts) -> int:
    """稳定随机种子：重启/不同机器一致"""
    s = "||".join(str(p) for p in parts)
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:12], 16)

def craft_correct_sentence(soln_text, result_text, issue_text):
    """把解决方法+整改结果动作化（不提指标），并限制为两要素并行句式"""
    base = (soln_text or "") + "；" + (result_text or "")
    base = _normalize_end_punct(base)
    want = []
    cand = ["由研究者复核签名", "纸质与系统同步修订", "注明修改原因与日期", "依据原始证据核对", "按访视窗口处理"]
    for c in cand:
        if c in base:
            want.append(c)
    if not want:
        want = ["由研究者复核签名", "纸质与系统同步修订"]
    want = list(dict.fromkeys(want))[:2]  # 最多两项
    return f"应{want[0]}，并{want[1]}；同时依据原始记录完善留痕"

def craft_distractor_sentence(kind):
    if kind == "延后处理":
        return "应暂缓修订并待下次集中处理，并保持现有记录不变；同时通过口头沟通提醒窗口"
    if kind == "口头代替":
        return "应先口头告知研究者留意并记录讨论要点，并在必要时再考虑修订；同时不做纸质与系统同步"
    if kind == "越权修改":
        return "应由CRC直接在系统更正并定稿，并在备注说明原因；同时纸质记录日后再补"
    if kind == "不留痕或不同步":
        return "应在EDC备注一次并上传截图，并保持纸质记录原状；同时无需另行说明原因与日期"
    return "应简要记录情况并持续观察，并避免影响当前流程；同时不做额外处理"

def balance_option_lengths(opts, rng: random.Random):
    """拉齐四个选项长度与结构：目标 40±10 字；差异 ≤12；统一双分句"""
    tail_bank = ["；同时记录讨论要点", "；同时保留沟通时间", "；同时更新工作清单"]
    def ensure_two_clause(s):
        s = _normalize_end_punct(s)
        return s if "；" in s else s + "；同时完善记录"
    opts = [ensure_two_clause(o) for o in opts]
    L = [len(o) for o in opts]
    target = max(min(int(sum(L)/len(L)), 48), 36)
    out = []
    for s in opts:
        if len(s) > target + 12:
            s = re.sub(r'立即|尽快|务必|严格|重点', '', s)
            s = s.replace("并且", "并").replace("以及", "并").replace("随后", "同时")
            s = re.sub(r'；.*$', '；同时完善记录', s)
        elif len(s) < target - 12:
            s += random.choice(tail_bank)
        out.append(s)
    return out

def make_stem(project=None, phase=None, issue=None):
    """题干：试验项目 + 试验阶段 + 问题 + 提问句"""
    pj = f"在“{str(project).strip()}”" if project else "在研究现场"
    ph = f"的{str(phase).strip()}中" if phase else "中"
    detail = (str(issue or "记录与要求不一致")).strip()
    detail = re.sub(r"。+$", "", detail)
    stem = f"{pj}{ph}，{detail}。下一步最合适的处置是？"
    stem = re.sub(r"阶段阶段", "阶段", stem)
    stem = re.sub(r"。。+", "。", stem)
    return stem

def build_question_from_row(row, idx):
    """核心出题：题面隐指标 + 均衡选项 + 追踪正确项（稳定种子）"""
    indicator_id, indicator_name = parse_indicator(getattr(row, "能力指标", ""))
    stem = make_stem(getattr(row, "试验项目", ""), getattr(row, "试验阶段", ""), getattr(row, "问题", ""))

    # 稳定随机种子，避免 rerun 抖动
    qseed = _stable_seed(getattr(row, "案例", ""), getattr(row, "问题", ""), getattr(row, "整改结果", ""))
    rng_local = random.Random(qseed)

    raw = [(craft_correct_sentence(getattr(row,"解决方法",""), getattr(row,"整改结果",""), getattr(row,"问题","")), True)]
    kinds = pick_error_distractors(rng_local)
    raw += [(craft_distractor_sentence(k), False) for k in kinds]

    balanced_texts = balance_option_lengths([t for t,_ in raw], rng_local)
    balanced = list(zip(balanced_texts, [ok for _, ok in raw]))

    order = list(range(4))
    rng_local.shuffle(order)
    shuffled = [balanced[i] for i in order]
    options_text = [t for t,_ in shuffled]
    correct_idx = [i for i,(_,ok) in enumerate(shuffled) if ok][0]
    answer_letter = "ABCD"[correct_idx]

    label_order = ["A","B","C","D"]
    why_wrong_map = {}
    for i, lab in enumerate(label_order):
        _, is_right = shuffled[i]
        why_wrong_map[lab] = "正确项。" if is_right else "常见误区：仅备注或口头说明、延后处理、CRC越权或单端修补。"

    explanation = {
        "why_right": "补齐原始依据并由研究者复核签名，纸质与系统同步修订并注明原因/日期，确保可追溯。",
        "how_to": ["核对原始证据","补填纸质并研究者签名日期","EDC同步修订并填写修改原因","卷宗归档与版本控制"],
        "why_wrong": why_wrong_map,
        "edge": "如涉主要终点/安全事件，应按方案触发上报流程。"
    }

    return {
        "idx": idx,
        "stem": stem,
        "options": {"A": options_text[0], "B": options_text[1], "C": options_text[2], "D": options_text[3]},
        "answer": answer_letter,
        "meta": {
            "indicator_id": indicator_id, "indicator_name": indicator_name,
            "phase": getattr(row, "试验阶段", "") or "", "project": getattr(row, "试验项目", "") or "",
            "error_cats": kinds,
            "first_level": parse_first_level(indicator_id)
        },
        "explain": explanation
    }

def generate_exam(df_src, n=20, seed=None, filter_indicator=None, filter_phase=None):
    """随机卷（保留）：可按指标文本/阶段过滤"""
    rng = random.Random(seed if seed is not None else 2025)
    view = df_src.copy()
    if filter_indicator:
        view = view[view["能力指标"].str.contains(filter_indicator, regex=False)]
    if filter_phase:
        view = view[view["试验阶段"] == filter_phase]
    if len(view) == 0:
        view = df_src.copy()
    rows = view.sample(n=min(n, len(view)), random_state=rng.randint(0, 10**9))
    return [build_question_from_row(row, i) for i, row in enumerate(rows.itertuples(), 1)]

def generate_exam_cover7(df_src, n=20, seed=None, filter_indicator=None, filter_phase=None):
    """
    “尽量覆盖七大一级指标”的出题器：
    - 先按能力编号的一级（1/2/3/…）分桶
    - 均匀轮询各桶抓题，保证题目尽量覆盖到不同一级
    - 如题量 > 桶数，继续轮询补齐
    """
    rng = random.Random(seed if seed is not None else 2026)
    view = df_src.copy()
    if filter_indicator:
        view = view[view["能力指标"].str.contains(filter_indicator, regex=False)]
    if filter_phase:
        view = view[view["试验阶段"] == filter_phase]
    if len(view) == 0:
        view = df_src.copy()

    valid_head = set(list("1234567"))
    buckets = {}
    for row in view.itertuples():
        iid, _ = parse_indicator(getattr(row, "能力指标", ""))
        lvl = parse_first_level(iid) or "X"
        if lvl not in valid_head:
            lvl = "X"
        buckets.setdefault(lvl, []).append(row)

    for k in list(buckets.keys()):
        rng.shuffle(buckets[k])

    order = sorted(buckets.keys(), key=lambda x: ("X" in x, x))  # 把无编号桶放最后
    if not order:
        rows = view.sample(n=min(n, len(view)), random_state=rng.randint(0, 10**9))
        return [build_question_from_row(r, i) for i, r in enumerate(rows.itertuples(), 1)]

    picked = []
    ptr = {k:0 for k in order}
    while len(picked) < min(n, len(view)):
        for k in order:
            if len(picked) >= min(n, len(view)): break
            p = ptr[k]
            if p < len(buckets[k]):
                picked.append(buckets[k][p])
                ptr[k] += 1
    return [build_question_from_row(r, i) for i, r in enumerate(picked[:n], 1)]

# —— 段落化个性化建议（总评 + 指标段落）——
def build_paragraph_advice(detail_rows, top_k=3):
    ERROR_CATS = ["延后处理","口头代替","越权修改","不留痕或不同步"]
    total = len(detail_rows)
    correct = sum(1 for r in detail_rows if r["your_answer"] == r["correct"])
    score100 = correct * 5
    wrong_rows = [r for r in detail_rows if r["your_answer"] != r["correct"]]

    cat_count = {c:0 for c in ERROR_CATS}
    for r in wrong_rows:
        for c in r.get("error_cats", []):
            cat_count[c] += 1
    cat_desc = []
    if any(cat_count.values()):
        if cat_count["延后处理"]:
            cat_desc.append("【延后处理】纠偏不及时，易扩大时间窗/依从性风险。落地做法：为关键窗口与里程碑设置提醒，尽量实现当日闭环。")
        if cat_count["口头代替"]:
            cat_desc.append("【口头代替】记录不可追溯。落地做法：所有沟通转化为书面/系统留痕，统一标注日期与责任人。")
        if cat_count["越权修改"]:
            cat_desc.append("【越权修改】CRC 代替研究者批注/修改不合规。落地做法：严格执行“研究者复核+签名”，并记录修改原因与日期。")
        if cat_count["不留痕或不同步"]:
            cat_desc.append("【不留痕/不同步】纸质与系统不同步。落地做法：双端同步修订并完成版本控制。")
    cat_text = " ".join(cat_desc) if cat_desc else "本次未见明显共性误区。"

    agg = {}
    for r in wrong_rows:
        key = (r.get("indicator_id",""), r.get("indicator_name","未标注指标"))
        ph = r.get("phase") or "未标注阶段"
        agg.setdefault(key, {"cnt":0, "phase":{}})
        agg[key]["cnt"] += 1
        agg[key]["phase"][ph] = agg[key]["phase"].get(ph,0) + 1
    top_inds = sorted(agg.items(), key=lambda kv: -kv[1]["cnt"])[:top_k]

    weak_list = "、".join([f"{iid or ''} {iname}".strip() for (iid, iname), _ in top_inds]) or "—"
    summary_html = (
        f"<div class='review-card'>"
        f"总评：本次答对 <b>{correct}/{total}</b> 题（<b>{score100} 分/100 分</b>）。"
        f"薄弱能力集中在：<b>{weak_list}</b>。{cat_text}"
        f"</div>"
    )

    def tips_by_indicator(name: str):
        if not name:
            return ["研究者复核签名","纸质与系统同步修订","注明原因与日期","卷宗归档与版本控制"]
        if ("知情" in name) or ("ICF" in name.upper()):
            return ["版本一致与签署先后","谈话要点与撤回/再签记录","签字日期与身份核验","纸质/系统一致"]
        if "样本" in name:
            return ["采集-处理-保存-运输时间链完整","标签与记录双核对","温控/离心参数留痕","交接与异常说明"]
        if ("AE" in name.upper()) or ("不良" in name):
            return ["定义与分级判定","关联性与严重性评估","时限内上报流程","原始依据与记录一致性"]
        return ["研究者复核签名","纸质与系统同步修订","注明原因与日期","按方案与窗口处理"]

    indicator_html_list = []
    for (iid, iname), v in top_inds:
        ph = sorted(v["phase"].items(), key=lambda x: -x[1])[0][0] if v["phase"] else "未标注阶段"
        tips = "；".join(tips_by_indicator(iname)) + "。"
        indicator_html_list.append(
            f"<div class='review-card'>"
            f"<b>{iid or ''} {iname or '未标注指标'}</b>：本次主要在 <b>{ph}</b> 暴露薄弱。"
            f"建议复习路径：到 <b>『案例题库』</b> 中用关键字 “{iname or '相关指标'}” 过滤该阶段的相关案例，先通读再对照 SOP/方案逐项核查；"
            f"操作训练按以下要点完成：{tips} 完成后再做 10 题专项小测巩固。"
            f"</div>"
        )

    return summary_html, indicator_html_list

# ---------------- 成绩CSV读取（鲁棒+可重建） ----------------
def load_results_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame(columns=["time","score","total","mode","run_id"])
    try:
        df = pd.read_csv(path, encoding="utf-8", engine="python", on_bad_lines="skip")
    except Exception:
        df = pd.read_csv(path, encoding="gbk", engine="python", on_bad_lines="skip")
    df = df.rename(columns={"时间":"time","得分":"score","题量":"total","模式":"mode","批次":"run_id"})
    keep = ["time","score","total","mode","run_id"]
    return df[[c for c in keep if c in df.columns]].copy()

def rebuild_results_from_runs(runs_dir: str):
    rows = []
    if os.path.isdir(runs_dir):
        for fn in os.listdir(runs_dir):
            if fn.endswith(".json") and fn.startswith("run_"):
                rid = fn.replace("run_", "").replace(".json", "")
                try:
                    t = datetime.strptime(rid, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    t = ""
                try:
                    with open(os.path.join(runs_dir, fn), "r", encoding="utf-8") as f:
                        detail = json.load(f)
                    total = len(detail)
                    wrong = sum(1 for d in detail if d["your_answer"] != d["correct"])
                    rows.append({"time": t, "score": total-wrong, "total": total, "mode": "FAST", "run_id": rid})
                except Exception:
                    pass
    return pd.DataFrame(rows, columns=["time","score","total","mode","run_id"])

# 只调用一次，避免重复按钮ID
login_status_bar()

# ===== 侧栏导航（放在 login_status_bar() 之后，页面分支之前）=====
uinfo = _current_user()
is_admin = (uinfo.get("role") == "admin")

DEFAULT_ITEMS = ["📚 案例题库", "🌐 知识图谱", "📝 能力评估", "📊 成绩反馈", "🧠 智能问答"]
if is_admin:
    DEFAULT_ITEMS.append("👩‍💼 管理后台")

# 初始选中项
if "menu" not in st.session_state:
    st.session_state["menu"] = DEFAULT_ITEMS[0]

with st.sidebar:
    st.markdown("### 导航")

    # 计算当前索引（防止不在列表时报错）
    _idx = DEFAULT_ITEMS.index(st.session_state["menu"]) if st.session_state["menu"] in DEFAULT_ITEMS else 0

    # 给 radio 一个唯一 key，避免 DuplicateElementId
    m_side = st.radio(
        "导航",
        DEFAULT_ITEMS,
        index=_idx,
        label_visibility="collapsed",
        key="nav_menu_side",
    )

    # 同步到 session
    if m_side != st.session_state["menu"]:
        st.session_state["menu"] = m_side
        st.rerun()  # ✅ 新版写法

# 后续页面分支都用这个变量
menu = st.session_state["menu"]

# ---------------- 页面：案例题库 ----------------
if menu == "📚 案例题库":
    st.markdown("<div class='section-title'>📚 案例题库</div>", unsafe_allow_html=True)

    # —— 顶部筛选 ----
    q = st.text_input("搜索案例 / 问题 / 指标 / 项目", "", placeholder="输入关键词")
    stages = ["全部"] + sorted([s for s in df["试验阶段"].dropna().unique() if str(s).strip()])
    c1, c2, c3 = st.columns([1.2, 1, 1.2])
    with c1:
        stage = st.selectbox("试验阶段", stages, index=0)
    with c2:
        per_page = st.selectbox("每页条数", [10, 20, 30, 50, 100], index=1)
    with c3:
        fullwidth = st.toggle("全宽表格模式（无横向滚动，一页看全）", value=True)

    # —— 过滤 ----
    df_view = df.copy()
    if stage != "全部":
        df_view = df_view[df_view["试验阶段"] == stage]
    if q.strip():
        qs = q.strip().lower()
        try:
            df_view = df_view[df_view["_search_blob"].str.contains(re.escape(qs), regex=True)]
        except Exception:
            df_view = df_view[df_view["_search_blob"].str.contains(qs, regex=False)]

    # —— 页码：用 session_state 保存，并在过滤条件变化时重置到第 1 页 ----
    _filters_key = f"{q.strip()}|{stage}|{per_page}"
    if "case_filters_key" not in st.session_state:
        st.session_state["case_filters_key"] = _filters_key
    if "case_page" not in st.session_state:
        st.session_state["case_page"] = 1
    if st.session_state["case_filters_key"] != _filters_key:
        st.session_state["case_filters_key"] = _filters_key
        st.session_state["case_page"] = 1

    page = st.session_state["case_page"]

    # —— 分页与展示（隐藏 _search_blob；全宽=st.table / 非全宽=st.dataframe）——
    total = len(df_view)
    max_page = max(1, (total + per_page - 1) // per_page)
    if page > max_page:
        page = max_page
        st.session_state["case_page"] = page  # 同步修正

    start = (page - 1) * per_page
    end = min(start + per_page, total)
    page_df = df_view.iloc[start:end].copy()

    # 序号列（全局连续编号）
    page_df.insert(0, "序号", range(start + 1, start + 1 + len(page_df)))

    # 去掉搜索列
    cols = [c for c in page_df.columns if c != "_search_blob"]
    page_df = page_df[cols].set_index("序号")

    # 表格：全宽=静态表（无横向滚动）；非全宽=可滚动表（表头固定）
    if fullwidth:
        st.table(page_df)
    else:
        st.dataframe(page_df, height=560, use_container_width=True, hide_index=False)

    # —— 表格底部分页器 ----
    b1, b2, b3, b4 = st.columns([1, 1, 2, 3])
    with b1:
        if st.button("上一页", use_container_width=True, disabled=page <= 1):
            st.session_state["case_page"] = max(1, page - 1)
            _st_rerun()
    with b2:
        if st.button("下一页", use_container_width=True, disabled=page >= max_page):
            st.session_state["case_page"] = min(max_page, page + 1)
            _st_rerun()
    with b3:
        st.markdown(
            f"<div style='padding-top:6px'>第 <b>{page}</b> / {max_page} 页 · 共 {total} 条</div>",
            unsafe_allow_html=True
        )
    with b4:
        jump = st.number_input(
            "跳转页", min_value=1, max_value=max_page, value=page, step=1, label_visibility="collapsed"
        )
        if jump != page:
            st.session_state["case_page"] = int(jump)
            _st_rerun()

# ---------------- 页面：知识图谱 ----------------
elif menu == "🌐 知识图谱":
    st.markdown("<div class='section-title'>🌐 知识图谱</div>", unsafe_allow_html=True)
    if os.path.exists(GRAPH_HTML):
        with open(GRAPH_HTML, "r", encoding="utf-8") as f:
            raw_html = f.read()
        components.html(raw_html, height=760, scrolling=False)  # 高度≥680，避免留白/滚动条
    else:
        st.warning(f"尚未找到 {GRAPH_HTML}，请先生成。")

# ---------------- 页面：能力评估 ----------------
elif menu == "📝 能力评估":
    st.markdown("<div class='section-title'>📝 能力评估</div>", unsafe_allow_html=True)

    # 状态
    if "paper" not in st.session_state: st.session_state["paper"] = []
    if "user_answers" not in st.session_state: st.session_state["user_answers"] = {}
    if "submitted" not in st.session_state: st.session_state["submitted"] = False
    if "last_detail" not in st.session_state: st.session_state["last_detail"] = []
    if "last_score" not in st.session_state: st.session_state["last_score"] = 0

    with st.expander("🔧 高级筛选（可选）", expanded=False):
        colf1, colf2, colf3 = st.columns([2,1,1])
        with colf1: indicator_filter = st.text_input("专项练习：输入能力指标编号或名称片段","")
        with colf2: phase_filter = st.selectbox("限定试验阶段（可空）", [""] + sorted(df["试验阶段"].unique().tolist()))
        with colf3: n_items = st.selectbox("题量", [10, 15, 20, 25, 30], index=2)

    colA, colB = st.columns([1, 3])
    with colA:
        if st.button("🧾 生成试卷", use_container_width=True, disabled=st.session_state["submitted"] is True):
            st.session_state["paper"] = generate_exam_cover7(
                df, n=n_items,
                filter_indicator=indicator_filter.strip() or None,
                filter_phase=phase_filter.strip() or None
            )
            st.session_state["user_answers"] = {}
            st.session_state["submitted"] = False
            st.session_state["last_detail"] = []
            st.session_state["last_score"] = 0
    with colB:
        st.info("题型：单选；选项长度均衡；交卷后提供基于能力指标的个性化讲评与复训。")

    # 渲染题目（提交后锁定选项）
    if st.session_state["paper"]:
        for q in st.session_state["paper"]:
            st.markdown("<div class='question-card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='question-title'>题目 {q['idx']}</div>", unsafe_allow_html=True)
            st.write(q["stem"])
            key = f"Q_{q['idx']}"

            opts = {"A": q["options"]["A"], "B": q["options"]["B"], "C": q["options"]["C"], "D": q["options"]["D"]}
            label_list = [f"{k}. {v}" for k, v in opts.items()]
            picked_label = st.radio(
                "请选择答案", label_list, index=None, key=key, horizontal=False,
                disabled=st.session_state["submitted"]
            )
            picked_letter = None
            if picked_label:
                m = re.match(r"^([ABCD])\.", picked_label.strip())
                picked_letter = m.group(1) if m else None
            st.session_state["user_answers"][q['idx']] = picked_letter

            st.markdown("</div>", unsafe_allow_html=True)

        # 交卷（必须全答），交卷后立刻 rerun 以锁定选项
        if (not st.session_state["submitted"]) and st.button("✅ 提交整套试卷并评分", type="primary", use_container_width=True):
            unanswered = [q["idx"] for q in st.session_state["paper"] if not st.session_state["user_answers"].get(q["idx"])]
            if unanswered:
                st.error(f"仍有题目未作答（题号：{', '.join(map(str, unanswered))}），请作答后再交卷。")
                st.stop()

            store_rows, score = [], 0
            for q in st.session_state["paper"]:
                ua = st.session_state["user_answers"].get(q["idx"])
                if ua == q["answer"]: score += 1
                store_rows.append({
                    "index": q["idx"], "your_answer": ua, "correct": q["answer"],
                    "stem": q["stem"], "A": q["options"]["A"], "B": q["options"]["B"],
                    "C": q["options"]["C"], "D": q["options"]["D"],
                    "indicator_id": q["meta"]["indicator_id"], "indicator_name": q["meta"]["indicator_name"],
                    "phase": q["meta"]["phase"], "error_cats": q["meta"]["error_cats"], "explain": q["explain"],
                })

            paths = user_paths()
            os.makedirs(paths["results_dir"], exist_ok=True)
            os.makedirs(paths["root"], exist_ok=True)

            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            one = pd.DataFrame([{
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "score": score, "total": len(store_rows), "mode": "FAST", "run_id": run_id
            }])

            csv_path = paths["results_csv"]
            if os.path.exists(csv_path):
                one.to_csv(csv_path, mode="a", header=False, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
            else:
                one.to_csv(csv_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)

            with open(os.path.join(paths["results_dir"], f"run_{run_id}.json"), "w", encoding="utf-8") as f:
                json.dump(store_rows, f, ensure_ascii=False, indent=2)

            st.session_state["submitted"] = True
            st.session_state["last_detail"] = store_rows
            st.session_state["last_score"] = score
            _st_rerun()

    # —— 交卷后的展示（勾/叉、段落化个性化建议）——
    if st.session_state["submitted"] and st.session_state["last_detail"]:
        total = len(st.session_state["last_detail"])
        score = st.session_state["last_score"]
        st.success(f"本次答对 {score}/{total} 题（{score*5} 分 / 100 分）")

        # 逐题精讲：在卡片最前显示 ✓ / ✗
        st.markdown("#### 🧩 逐题精讲", unsafe_allow_html=True)
        for r in st.session_state["last_detail"]:
            ok = (r["your_answer"] == r["correct"])
            flag = "✅" if ok else "❌"
            idn = f"{(r['indicator_id'] + ' ') if r['indicator_id'] else ''}{r['indicator_name'] or '未标注指标'}"
            exp = r["explain"]; steps = "、".join(exp["how_to"])
            explain_map = r["explain"]["why_wrong"]
            wrong_brief = "；".join([f"{lab}：{txt}" for lab, txt in explain_map.items() if lab != r["correct"]])
            line = (
                f"<div class='review-card'>"
                f"{flag} <span class='review-hd'>题 {r['index']}｜能力：</span>{idn}｜"
                f"<b>正确 {r['correct']}</b>（你的选择：{r['your_answer']}）｜"
                f"理由：{exp['why_right']}｜怎么做：{steps}｜边界：{exp['edge']}<br>"
                f"{wrong_brief}"
                f"</div>"
            )
            st.markdown(line, unsafe_allow_html=True)

        summary_html, indicator_html_list = build_paragraph_advice(st.session_state["last_detail"])
        st.markdown("#### 🎯 个性化建议", unsafe_allow_html=True)
        st.markdown(summary_html, unsafe_allow_html=True)
        for html in indicator_html_list:
            st.markdown(html, unsafe_allow_html=True)

        # 再练入口
        wrong_rows = [r for r in st.session_state["last_detail"] if r["your_answer"] != r["correct"]]
        agg = {}
        for r in wrong_rows:
            key = (r["indicator_id"], r["indicator_name"])
            agg[key] = agg.get(key, 0) + 1
        top_inds = sorted(agg.items(), key=lambda kv: -kv[1])[:3]
        if top_inds:
            cols = st.columns(len(top_inds))
            for i, ((iid, iname), _) in enumerate(top_inds):
                with cols[i]:
                    if st.button(f"专项再练10题：{iid or ''} {iname}".strip(), key=f"retrain_{iid}_{iname}"):
                        st.session_state["paper"] = generate_exam(df, n=10, filter_indicator=(iid or iname))
                        st.session_state["user_answers"] = {}
                        st.session_state["submitted"] = False
                        st.session_state["last_detail"] = []
                        _st_rerun()

# ---------------- 页面：成绩反馈 ----------------
elif menu == "📊 成绩反馈":
    st.markdown("<div class='section-title'>📊 成绩反馈</div>", unsafe_allow_html=True)

    paths = user_paths()

    df_runs = rebuild_results_from_runs(paths["results_dir"])
    if df_runs.empty:
        df_csv = load_results_csv(paths["results_csv"])
        if not df_csv.empty:
            if "run_id" not in df_csv.columns:
                df_csv["run_id"] = ""
            df_csv["time"] = pd.to_datetime(df_csv["time"], errors="coerce")
            df_base = df_csv.copy()
        else:
            df_base = pd.DataFrame(columns=["time","score","total","mode","run_id"])
    else:
        df_runs["time"] = pd.to_datetime(df_runs["time"], errors="coerce")
        df_base = df_runs.copy()

    if df_base.empty:
        st.info("还没有成绩记录，先去做一次测评吧～")
    else:
        def has_runfile(rid: str) -> bool:
            return bool(rid) and os.path.exists(os.path.join(paths["results_dir"], f"run_{rid}.json"))

        if "run_id" in df_base.columns:
            df_base = df_base[df_base["run_id"].astype(str).apply(has_runfile)]

        if df_base.empty:
            st.info("找到了成绩汇总，但缺少对应的明细文件（runs）。做一次新的测评即可恢复联动展示。")
            st.stop()

        dft = df_base.sort_values("time", ascending=True).copy()
        dft["时间"] = dft["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        dft["得分题数"] = pd.to_numeric(dft["score"], errors="coerce").fillna(0).astype(int)
        dft["分数"] = dft["得分题数"] * 5
        dft["题量"] = pd.to_numeric(dft["total"], errors="coerce").fillna(0).astype(int)
        dft["答对/题量"] = dft["得分题数"].astype(str) + "/" + dft["题量"].astype(str)

        df_show = dft[["时间","答对/题量","分数"]].reset_index(drop=True)
        df_show.index = range(1, len(df_show)+1)
        st.table(df_show)

        fig = px.line(dft, x="time", y="分数", markers=True, title="成绩趋势",
                      labels={"time":"时间", "分数":"分数"})
        fig.update_layout(height=420, margin=dict(l=20, r=20, t=50, b=10))
        st.plotly_chart(
            fig, use_container_width=True,
            config={
                "locale": "zh-CN",
                "displaylogo": False,
                "modeBarButtonsToRemove": [
                    "lasso2d","select2d","autoScale2d","resetScale2d",
                    "hoverClosestCartesian","hoverCompareCartesian",
                    "toggleSpikelines"
                ],
            },
        )

        options = [(f"测试 {row['时间']}", row["run_id"]) for _, row in dft.iterrows()]
        labels = [x[0] for x in options]
        rids   = [x[1] for x in options]
        pick_label = st.selectbox("选择一次测试查看讲评与建议", labels, index=len(labels)-1)
        rid = rids[labels.index(pick_label)]

        try:
            with open(os.path.join(paths["results_dir"], f"run_{rid}.json"), "r", encoding="utf-8") as f:
                detail = json.load(f)
        except FileNotFoundError:
            st.warning("该记录的明细文件缺失，无法展示讲评。做一次新的测评即可生成新的明细。")
            st.stop()

        st.markdown("#### 🧩 逐题精讲", unsafe_allow_html=True)
        for r in detail:
            idn = f"{(r['indicator_id']+' ') if r['indicator_id'] else ''}{r['indicator_name'] or '未标注指标'}"
            exp = r["explain"]; steps = "、".join(exp["how_to"])
            explain_map = r["explain"]["why_wrong"]
            wrong_brief = "；".join([f"{lab}：{txt}" for lab, txt in explain_map.items() if lab != r["correct"]])
            st.markdown(
                f"<div class='review-card'><span class='review-hd'>题 {r['index']}｜能力：</span>{idn}｜"
                f"<b>正确 {r['correct']}</b>｜理由：{exp['why_right']}｜怎么做：{steps}｜"
                f"{wrong_brief}｜边界：{exp['edge']}</div>", unsafe_allow_html=True
            )

        st.markdown("#### 🎯 个性化建议", unsafe_allow_html=True)
        summary_html, indicator_html_list = build_paragraph_advice(detail)
        st.markdown(summary_html, unsafe_allow_html=True)
        for html in indicator_html_list:
            st.markdown(html, unsafe_allow_html=True)

        wrong_rows = [r for r in detail if r["your_answer"] != r["correct"]]
        agg_ind = {}
        for r in wrong_rows:
            key = (r["indicator_id"], r["indicator_name"])
            agg_ind[key] = agg_ind.get(key, 0) + 1
        top_inds = sorted(agg_ind.items(), key=lambda x:-x[1])[:3]
        if top_inds:
            for (iid, iname), _ in top_inds:
                if st.button(f"专项再练10题：{iid or ''} {iname}".strip(), key=f"re_view_{rid}_{iid}_{iname}"):
                    st.session_state["paper"] = generate_exam(df, n=10, filter_indicator=(iid or iname))
                    st.session_state["user_answers"] = {}
                    st.session_state["submitted"] = False
                    _st_rerun()

# ---------------- 页面：智能问答（对话式） ----------------
elif menu == "🧠 智能问答":
    st.markdown("<div class='section-title'>🧠 智能问答</div>", unsafe_allow_html=True)
    st.markdown("<div class='soft-panel'>", unsafe_allow_html=True)

    if "qa_chat" not in st.session_state:
        st.session_state["qa_chat"] = []

    question = st.text_input("请输入你的问题（例如：V2访视心电图缺签名如何补救？）", "", placeholder="输入你的问题")
    use_llm = st.toggle("使用 AI 润色回答", value=False)

    def simple_retrieve(q, df_src, k=5):
        if not q.strip():
            return []
        qs = q.strip().lower()
        scored = []
        for r in df_src.itertuples():
            bag = " ".join([str(getattr(r,"案例","")), str(getattr(r,"问题","")), str(getattr(r,"解决方法","")),
                            str(getattr(r,"整改结果","")), str(getattr(r,"反思",""))]).lower()
            score = sum(1 for token in re.split(r"[\s,，。；;]+", qs) if token and token in bag)
            if score > 0:
                scored.append((score, r))
        scored.sort(key=lambda x: -x[0])
        return [x[1] for x in scored[:k]]

    def synthesize_answer(q, hits):
        key_points = []
        for r in hits:
            for col in ["解决方法","整改结果","反思"]:
                t = str(getattr(r, col) or "").strip()
                if t:
                    key_points.append(shorten(t, 120))
                    break
        key_points = key_points[:6]
        if not key_points:
            return "建议：对照方案与SOP核对原始依据，按缺失/错误类型完成修订，并保留可追溯留痕。"
        para = "针对你的问题，可落实：" + "；".join(key_points) + "。同时确保纸质与系统一致、研究者复核签名、时间与原因可追溯。"
        return para

    if st.button("回答", type="primary"):
        if not question.strip():
            st.warning("请先输入问题。")
        else:
            hits = simple_retrieve(question, df, k=5)
            answer = synthesize_answer(question, hits)
            if use_llm and HAVE_OLLAMA and hits:
                ctx = "\n\n".join([
                    f"案例：{getattr(h,'案例','')}\n问题：{getattr(h,'问题','')}\n解决方法：{getattr(h,'解决方法','')}\n整改结果：{getattr(h,'整改结果','')}\n反思：{getattr(h,'反思','')}"
                    for h in hits
                ])
                prompt = f"基于下列CRC案例材料，请用一个段落给出规范、清晰、可执行的操作建议（不超过120字）：\n\n{ctx}\n\n用户问题：{question}"
                try:
                    resp = ollama.chat(model="qwen3:1.7b", messages=[{"role":"user","content":prompt}])
                    answer = resp["message"]["content"].strip() or answer
                except Exception as e:
                    st.info(f"AI 润色未成功，已使用本地生成答案。原因：{e}")

            st.session_state["qa_chat"].append(("user", question))
            st.session_state["qa_chat"].append(("bot", answer))
            refs = [f"{i}. {getattr(r,'案例','')}｜问题：{shorten(getattr(r,'问题',''), 80)}｜解决：{shorten(getattr(r,'解决方法',''), 80)}" for i, r in enumerate(hits, 1)]
            if refs:
                st.session_state["qa_chat"].append(("bot_refs", "\n".join(refs)))

            try:
                p = user_paths()
                os.makedirs(p["root"], exist_ok=True)
                with open(p["qa_log"], "a", encoding="utf-8") as fp:
                    fp.write(json.dumps({
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "q": question, "a": answer
                    }, ensure_ascii=False) + "\n")
            except Exception:
                pass

    st.markdown("<div class='chat-wrap'>", unsafe_allow_html=True)
    for role, content in st.session_state["qa_chat"]:
        if role == "user":
            st.markdown(f"<div class='bubble bubble-user'>🧑‍⚕️ {content}</div>", unsafe_allow_html=True)
        elif role == "bot":
            st.markdown(f"<div class='bubble bubble-bot'>🤖 {content}</div>", unsafe_allow_html=True)
        elif role == "bot_refs":
            with st.expander("引用的案例依据"):
                st.markdown(content.replace("\n", "  \n"))
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ---------------- 页面：👩‍💼 管理后台（仅 admin 看到） ----------------
elif menu == "👩‍💼 管理后台":
    if not is_admin:
        st.error("仅管理员可见")
        st.stop()

    st.markdown("<div class='section-title'>👩‍💼 管理后台</div>", unsafe_allow_html=True)

    # 读取 users.json（项目根）
    try:
        with open(os.path.join(BASE_DIR, "..", "users.json"), "r", encoding="utf-8") as f:
            all_users = json.load(f)
    except Exception:
        all_users = []

    if not all_users:
        st.info("未找到用户列表（users.json）。")
        st.stop()

    choices = [f"{u.get('name','')}（{u.get('user_id','')}）" for u in all_users]
    pick = st.selectbox("选择用户查看成绩与明细", choices)
    pick_uid = all_users[choices.index(pick)].get("user_id")

    pick_root = os.path.join(BASE_DIR, "user_data", pick_uid)
    pick_csv  = os.path.join(pick_root, "results.csv")
    pick_runs = os.path.join(pick_root, "results_runs")

    df_runs = rebuild_results_from_runs(pick_runs)
    if df_runs.empty:
        df_csv = load_results_csv(pick_csv)
        df_base = df_csv if not df_csv.empty else pd.DataFrame(columns=["time","score","total","mode","run_id"])
    else:
        df_runs["time"] = pd.to_datetime(df_runs["time"], errors="coerce")
        df_base = df_runs.copy()

    if df_base.empty:
        st.info("该用户暂无成绩记录")
        st.stop()

    dft = df_base.sort_values("time", ascending=True).copy()
    dft["时间"] = pd.to_datetime(dft["time"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    dft["得分题数"] = pd.to_numeric(dft["score"], errors="coerce").fillna(0).astype(int)
    dft["分数"] = dft["得分题数"] * 5
    dft["题量"] = pd.to_numeric(dft["total"], errors="coerce").fillna(0).astype(int)
    df_show = dft[["时间","得分题数","题量","分数"]].reset_index(drop=True)
    df_show.index = range(1, len(df_show)+1)
    st.table(df_show)

    options = [(f"测试 {row['时间']}", row["run_id"]) for _, row in dft.iterrows()]
    labels = [x[0] for x in options]; rids = [x[1] for x in options]
    pick_label = st.selectbox("选择一次测试", labels, index=len(labels)-1)
    rid = rids[labels.index(pick_label)]
    try:
        with open(os.path.join(pick_runs, f"run_{rid}.json"), "r", encoding="utf-8") as f:
            detail = json.load(f)
        st.markdown("#### 🧩 逐题精讲", unsafe_allow_html=True)
        for r in detail:
            idn = f"{(r['indicator_id']+' ') if r['indicator_id'] else ''}{r['indicator_name'] or '未标注指标'}"
            exp = r["explain"]; steps = "、".join(exp["how_to"])
            explain_map = r["explain"]["why_wrong"]
            wrong_brief = "；".join([f"{lab}：{txt}" for lab, txt in explain_map.items() if lab != r["correct"]])
            st.markdown(
                f"<div class='review-card'><span class='review-hd'>题 {r['index']}｜能力：</span>{idn}｜"
                f"<b>正确 {r['correct']}</b>｜理由：{exp['why_right']}｜怎么做：{steps}｜"
                f"{wrong_brief}｜边界：{exp['edge']}</div>", unsafe_allow_html=True
            )
    except FileNotFoundError:
        st.warning("该次明细缺失")
