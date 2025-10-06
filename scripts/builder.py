# -*- coding: utf-8 -*-
"""
Neo4j 知识图谱导入（先清空再生成｜按你最新关系表｜Neo4j 4.3 兼容版）
关系（方向固定）：
- 案例 —来源→ 试验项目
- 案例 —对应→ 能力指标
- 案例 —处于→ 试验阶段
- 案例 —涉及→ 岗位职责
- 案例 —出现→ 问题
- 问题 —采用→ 解决方法
- 解决方法 —产生→ 整改结果
- 案例 —形成→ 反思

注意点：
- 提交事务统一使用 g.commit(tx)（你的 py2neo 推荐用法，避免 DeprecationWarning）。
- 指标分层“属于”关系用 py2neo 的 Relationship。
- 所有 tx.run 内的中文关系名已用反引号包裹，避免解析问题。
- 增加表头“兜底映射”，轻微改列名也能正常导入。
"""

import re
import hashlib
import pandas as pd
from py2neo import Graph, Node, Relationship

# ===== 0) 基本配置 =====
NEO4J_URI  = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "dsm123456")

INDICATOR_XLSX = r"C:\Users\刘航博\Desktop\评价指标的分布.xlsx"
CASE_XLSX      = r"C:\Users\刘航博\Desktop\临床试验协调过程案例库（知识图谱版）.xlsx"

BATCH_SZ = 500

# 清空与重建开关
CLEAR_ALL_DATA     = True   # True=导入前清空所有节点与关系
RESET_CONSTRAINTS  = False  # True=连同约束一起重置（一般不需要）

# ===== 1) 工具函数 =====
def sval(x):
    if pd.isna(x):
        return ""
    s = str(x).strip().replace("\u3000", " ")
    return re.sub(r"\s+", " ", s)

RE_LV1_FULL = re.compile(r"^\s*(\d+)\s*(.*)$")
RE_LV2_FULL = re.compile(r"^\s*(\d+\.\d+)\s*(.*)$")
RE_LV3_FULL = re.compile(r"^\s*(\d+\.\d+\.\d+)\s*(.*)$")
RE_CODE_ANY = re.compile(r"^\s*(\d+(?:\.\d+)*)")

def unk_code(text):
    base = text if text else "EMPTY"
    return "UNK::" + hashlib.md5(base.encode("utf-8")).hexdigest()[:10]

def case_uid(case_name):
    # 当前以“案例名称”派生 UID；若未来转增量导入，建议改用“案例编号”列作为主键来源
    return hashlib.md5(case_name.encode("utf-8")).hexdigest()[:12]

def drop_constraints(db: Graph):
    # 兼容 Neo4j 4.3 的旧语法
    cqls = [
        "DROP CONSTRAINT ON (i:Indicator) ASSERT i.code IS UNIQUE",
        "DROP CONSTRAINT ON (c:Case)      ASSERT c.name IS UNIQUE",
        "DROP CONSTRAINT ON (p:Problem)   ASSERT p.uid  IS UNIQUE",
        "DROP CONSTRAINT ON (a:Action)    ASSERT a.uid  IS UNIQUE",
        "DROP CONSTRAINT ON (r:Result)    ASSERT r.uid  IS UNIQUE",
        "DROP CONSTRAINT ON (f:Reflection)ASSERT f.uid  IS UNIQUE",
        "DROP CONSTRAINT ON (s:Stage)     ASSERT s.name IS UNIQUE",
        "DROP CONSTRAINT ON (ro:Role)     ASSERT ro.name IS UNIQUE",
        "DROP CONSTRAINT ON (prj:Project) ASSERT prj.name IS UNIQUE",
        "DROP CONSTRAINT ON (ctr:Center)  ASSERT ctr.name IS UNIQUE",
    ]
    for c in cqls:
        try:
            db.run(c)
        except Exception as e:
            msg = str(e).lower()
            if ("exist" in msg) or ("no such" in msg) or ("not found" in msg):
                pass
            else:
                raise

def create_constraints(db: Graph):
    # 兼容 Neo4j 4.3 旧语法
    cqls = [
        "CREATE CONSTRAINT ON (i:Indicator) ASSERT i.code IS UNIQUE",
        "CREATE CONSTRAINT ON (c:Case)      ASSERT c.name IS UNIQUE",
        "CREATE CONSTRAINT ON (p:Problem)   ASSERT p.uid  IS UNIQUE",
        "CREATE CONSTRAINT ON (a:Action)    ASSERT a.uid  IS UNIQUE",
        "CREATE CONSTRAINT ON (r:Result)    ASSERT r.uid  IS UNIQUE",
        "CREATE CONSTRAINT ON (f:Reflection)ASSERT f.uid  IS UNIQUE",
        "CREATE CONSTRAINT ON (s:Stage)     ASSERT s.name IS UNIQUE",
        "CREATE CONSTRAINT ON (ro:Role)     ASSERT ro.name IS UNIQUE",
        "CREATE CONSTRAINT ON (prj:Project) ASSERT prj.name IS UNIQUE",
        "CREATE CONSTRAINT ON (ctr:Center)  ASSERT ctr.name IS UNIQUE",
    ]
    for c in cqls:
        try:
            db.run(c)
        except Exception as e:
            msg = str(e).lower()
            if ("already" in msg) or ("equivalent schema" in msg):
                pass
            else:
                raise

def eval_one(db: Graph, q: str, title: str):
    try:
        val = db.run(q).evaluate()
        print("{}: {}".format(title, val))
    except Exception as e:
        print("{} 查询出错: {}".format(title, e))

# 阶段归一（可选）
STAGE_MAP = {
    "准备阶段": "准备阶段",
    "进行阶段": "进行阶段",
    "结题阶段": "结题阶段",
    "随访阶段": "进行阶段",
    "结束阶段": "结题阶段",
    "收尾阶段": "结题阶段"
}

# ===== 表头“兜底映射” =====
IND_COLS = {
    "一级指标": ["一级指标", "一级", "Level1", "L1"],
    "二级指标": ["二级指标", "二级", "Level2", "L2"],
    "三级指标": ["三级指标", "三级", "Level3", "L3"],
}
CASE_COLS = {
    "案例":     ["案例", "案例名称", "Case", "案例名"],
    "试验项目": ["试验项目", "项目", "研究项目", "Project"],
    "能力指标": ["能力指标", "指标", "Indicator"],
    "试验阶段": ["试验阶段", "阶段", "Stage"],
    "岗位职责": ["岗位职责", "职责", "Role"],
    "问题":     ["问题", "问题描述", "Problem"],
    "解决方法": ["解决方法", "整改措施", "Action"],
    "整改结果": ["整改结果", "结果", "Result"],
    "反思":     ["反思", "案例反思", "Reflection"],
}

def pick_col(df: pd.DataFrame, canon_name: str, mapping: dict):
    for cand in mapping.get(canon_name, []):
        if cand in df.columns:
            return cand
    return None

# ===== 2) 连接 =====
g = Graph(NEO4J_URI, auth=NEO4J_AUTH)

# ===== 3) 清空（可选）=====
if CLEAR_ALL_DATA:
    print("⚠️ 正在清空现有图数据（节点与关系）...")
    g.run("MATCH (n) DETACH DELETE n")
    print("✅ 清空完成。")
    if RESET_CONSTRAINTS:
        print("⚠️ 正在重置唯一性约束...")
        drop_constraints(g)
        create_constraints(g)
        print("✅ 约束已重置。")
    else:
        create_constraints(g)
else:
    create_constraints(g)

# ===== 4) 指标体系（Center/属于 层级）=====
df_ind = pd.read_excel(INDICATOR_XLSX)
print("指标表头:", df_ind.columns.tolist())

col_l1 = pick_col(df_ind, "一级指标", IND_COLS)
col_l2 = pick_col(df_ind, "二级指标", IND_COLS)
col_l3 = pick_col(df_ind, "三级指标", IND_COLS)

tx = g.begin()
center = Node("Center", name="CRC实践核心能力评价指标")
tx.merge(center, "Center", "name")

ops = 0
for _, row in df_ind.iterrows():
    # 一级
    lvl1 = sval(row.get(col_l1)) if col_l1 else ""
    if lvl1:
        m1 = RE_LV1_FULL.match(lvl1)
        if m1:
            code1, name1 = m1.group(1), m1.group(2)
            n1 = Node("Indicator", code=code1, name=("{} {}".format(code1, name1)).strip(), level="一级")
            tx.merge(n1, "Indicator", "code")
            tx.merge(Relationship(n1, "属于", center))
    # 二级
    lvl2 = sval(row.get(col_l2)) if col_l2 else ""
    if lvl2:
        m2 = RE_LV2_FULL.match(lvl2)
        if m2:
            code2, name2 = m2.group(1), m2.group(2)
            n2 = Node("Indicator", code=code2, name=("{} {}".format(code2, name2)).strip(), level="二级")
            tx.merge(n2, "Indicator", "code")
            p1 = Node("Indicator", code=code2.split(".")[0])
            tx.merge(p1, "Indicator", "code")
            tx.merge(Relationship(n2, "属于", p1))
    # 三级
    lvl3 = sval(row.get(col_l3)) if col_l3 else ""
    if lvl3:
        m3 = RE_LV3_FULL.match(lvl3)
        if m3:
            code3, name3 = m3.group(1), m3.group(2)
            n3 = Node("Indicator", code=code3, name=("{} {}".format(code3, name3)).strip(), level="三级")
            tx.merge(n3, "Indicator", "code")
            p2_code = ".".join(code3.split(".")[:-1])
            p2 = Node("Indicator", code=p2_code)
            tx.merge(p2, "Indicator", "code")
            tx.merge(Relationship(n3, "属于", p2))

    ops += 1
    if ops % BATCH_SZ == 0:
        g.commit(tx)
        tx = g.begin()

g.commit(tx)
print("✅ 指标体系导入完成！")

# 仅承认正式“三级”
valid_lv3 = {}
lvl3_series = df_ind[col_l3] if col_l3 else []
for lvl3_text in lvl3_series:
    lvl3_text = sval(lvl3_text)
    m = RE_LV3_FULL.match(lvl3_text or "")
    if m:
        valid_lv3[m.group(1)] = lvl3_text

# ===== 5) 案例库（按最新八条关系）=====
df_cases = pd.read_excel(CASE_XLSX)
print("案例表头:", df_cases.columns.tolist())

c_case   = pick_col(df_cases, "案例", CASE_COLS)
c_proj   = pick_col(df_cases, "试验项目", CASE_COLS)
c_ind    = pick_col(df_cases, "能力指标", CASE_COLS)
c_stage  = pick_col(df_cases, "试验阶段", CASE_COLS)
c_role   = pick_col(df_cases, "岗位职责", CASE_COLS)
c_prob   = pick_col(df_cases, "问题", CASE_COLS)
c_act    = pick_col(df_cases, "解决方法", CASE_COLS)
c_res    = pick_col(df_cases, "整改结果", CASE_COLS)
c_ref    = pick_col(df_cases, "反思", CASE_COLS)

tx = g.begin()
ops = 0
for _, row in df_cases.iterrows():
    case_name = sval(row.get(c_case)) if c_case else ""
    if not case_name:
        print("⚠️ 跳过空案例名称")
        continue

    # 案例节点
    tx.merge(Node("Case", name=case_name), "Case", "name")

    # 试验项目：案例-来源->项目
    project = sval(row.get(c_proj)) if c_proj else ""
    if project:
        tx.run("""
            MERGE (c:Case {name:$c})
            MERGE (p:Project {name:$p})
            MERGE (c)-[:`来源`]->(p)
        """, c=case_name, p=project)

    # 能力指标：案例-对应->指标（仅三级为“正式”）
    raw_ind = sval(row.get(c_ind)) if c_ind else ""
    m = RE_CODE_ANY.match(raw_ind)
    if m and (m.group(1) in valid_lv3):
        code = m.group(1)
        formal = valid_lv3[code]
        tx.run("""
            MERGE (c:Case {name:$c})
            MERGE (i:Indicator {code:$code})
              ON CREATE SET i.name=$name, i.level='三级'
            MERGE (c)-[:`对应`]->(i)
        """, c=case_name, code=code, name=formal)
    else:
        tx.run("""
            MERGE (c:Case {name:$c})
            MERGE (i:Indicator {code:$code})
              ON CREATE SET i.name=$name, i.level='待校验', i.display=$disp
            MERGE (c)-[:`对应`]->(i)
        """, c=case_name, code=unk_code(raw_ind), name=raw_ind, disp=raw_ind)

    # 试验阶段：案例-处于->阶段（归一）
    stage_raw = sval(row.get(c_stage)) if c_stage else ""
    stage = STAGE_MAP.get(stage_raw, stage_raw)
    if stage:
        tx.run("""
            MERGE (c:Case {name:$c})
            MERGE (s:Stage {name:$s})
            MERGE (c)-[:`处于`]->(s)
        """, c=case_name, s=stage)

    # 岗位职责：案例-涉及->岗位
    role = sval(row.get(c_role)) if c_role else ""
    if role:
        tx.run("""
            MERGE (c:Case {name:$c})
            MERGE (ro:Role {name:$r})
            MERGE (c)-[:`涉及`]->(ro)
        """, c=case_name, r=role)

    # 四段链条：出现→采用→产生；以及形成→反思
    prob = sval(row.get(c_prob)) if c_prob else ""
    act  = sval(row.get(c_act))  if c_act  else ""
    res  = sval(row.get(c_res))  if c_res  else ""
    ref  = sval(row.get(c_ref))  if c_ref  else ""

    cid = case_uid(case_name)
    puid = "{}::P".format(cid)
    auid = "{}::A".format(cid)
    ruid = "{}::R".format(cid)
    fuid = "{}::F".format(cid)

    if prob:
        tx.run("""
            MERGE (p:Problem {uid:$uid})
              ON CREATE SET p.desc=$d
            MERGE (c:Case {name:$c})
            MERGE (c)-[:`出现`]->(p)
        """, uid=puid, d=prob, c=case_name)

    if prob and act:
        tx.run("""
            MERGE (p:Problem {uid:$p})
            MERGE (a:Action  {uid:$a})
              ON CREATE SET a.desc=$ad
            MERGE (p)-[:`采用`]->(a)
        """, p=puid, a=auid, ad=act)

    if act and res:
        tx.run("""
            MERGE (a:Action {uid:$a})
            MERGE (r:Result {uid:$r})
              ON CREATE SET r.desc=$rd
            MERGE (a)-[:`产生`]->(r)
        """, a=auid, r=ruid, rd=res)

    if ref:
        tx.run("""
            MERGE (f:Reflection {uid:$f})
              ON CREATE SET f.desc=$fd
            MERGE (c:Case {name:$c})
            MERGE (c)-[:`形成`]->(f)
        """, f=fuid, fd=ref, c=case_name)

    ops += 1
    if ops % BATCH_SZ == 0:
        g.commit(tx)
        tx = g.begin()

g.commit(tx)
print("✅ 案例库导入完成！")

# ===== 6) 体检（DISTINCT 口径）=====
print("\n📊 体检汇总（DISTINCT）")
eval_one(g, "MATCH (n) RETURN count(n)", "节点总数")
eval_one(g, "MATCH ()-[r]->() RETURN count(r)", "关系总数")
eval_one(g, "MATCH (c:Case)-[:`对应`]->(:Indicator) RETURN count(DISTINCT c)", "已挂指标的案例数")
eval_one(g, "MATCH (i:Indicator {level:'待校验'}) RETURN count(i)", "待校验指标数量")
eval_one(g, "MATCH (c:Case) WHERE NOT (c)-[:`对应`]->(:Indicator) RETURN count(c)", "未挂指标案例")
eval_one(g, "MATCH (c:Case) WHERE NOT (c)-[:`处于`]->(:Stage) RETURN count(c)", "未挂阶段案例")

print("\n✅ 完成。可在 Neo4j Browser 检查：")
print("  MATCH (c:Case)-[:`对应`]->(i:Indicator) RETURN c,i LIMIT 20;")
print("  MATCH (c:Case)-[:`出现`]->(p:Problem)-[:`采用`]->(a:Action)-[:`产生`]->(r:Result) RETURN c,p,a,r LIMIT 10;")
print("  MATCH (c:Case)-[:`形成`]->(f:Reflection) RETURN c,f LIMIT 10;")

# 可选：一眼查空挂关键关系（若要求案例必须有 指标/阶段/项目）
print("\n🔎 关键关系挂载自检（前 50 条）：")
q_check = """
MATCH (c:Case)
RETURN
  c.name AS case_name,
  EXISTS((c)-[:`对应`]->(:Indicator)) AS hasIndicator,
  EXISTS((c)-[:`处于`]->(:Stage))     AS hasStage,
  EXISTS((c)-[:`来源`]->(:Project))   AS hasProject
ORDER BY hasIndicator, hasStage, hasProject
LIMIT 50
"""
try:
    data = g.run(q_check).data()
    for row in data:
        print(row)
except Exception as e:
    print("自检查询失败：{}".format(e))
