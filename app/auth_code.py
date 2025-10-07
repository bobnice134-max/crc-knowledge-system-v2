# auth_code.py —— 账号+密码；本地 users.json 管理
import json, os, hashlib
import streamlit as st

SESSION_USER = "auth_user"   # {"user_id": "...", "name": "...", "role": "..."}
SESSION_STEP = "code_step"

@st.cache_data(show_spinner=False)
def load_users(json_path: str):
    if not os.path.exists(json_path):
        return {}
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    idx = {}
    for u in data:
        uid = str(u.get("user_id", "")).strip()
        if uid:
            idx[uid] = {
                "user_id": uid,
                "name": u.get("name", ""),
                "code_hash": str(u.get("code_hash", "")),  # 期望是 "sha256:..." 格式
                "role": u.get("role", "student"),
                "active": bool(u.get("active", True)),
            }
    return idx

def _sha256(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()

def _verify_code(plain: str, stored: str) -> bool:
    """兼容两种存储：sha256:xxxx 或 明文（仅用于本地临时测试）"""
    if not stored:
        return False
    if stored.startswith("sha256:"):
        return _sha256(plain) == stored
    # 兼容明文（不推荐，仅为防止历史数据）
    return plain == stored

def is_logged_in() -> bool:
    return st.session_state.get(SESSION_USER) is not None

def logout():
    st.session_state.pop(SESSION_USER, None)
    st.session_state.pop(SESSION_STEP, None)
    st.rerun()

def require_login(users_json_path: str = "users.json"):
    if is_logged_in():
        return

    users = load_users(users_json_path)
    st.subheader("🔐 账号登录")
    c1, c2 = st.columns(2)
    with c1:
        user_id = st.text_input("账号", key="code_user_id")
    with c2:
        code = st.text_input("密码", type="password", key="code_plain")

    if st.button("登录", type="primary", use_container_width=True):
        uid = (user_id or "").strip()
        cp  = (code or "").strip()
        if not uid or not cp:
            st.error("请输入账号和密码。")
            st.stop()

        u = users.get(uid)
        if not u or not u.get("active", True):
            st.error("该账号不存在或未启用。")
            st.stop()

        if not _verify_code(cp, u.get("code_hash", "")):
            st.error("密码不正确。")
            st.stop()

        st.session_state[SESSION_USER] = {
            "user_id": u["user_id"],
            "name": u["name"],
            "role": u.get("role", "student"),
        }
        st.success(f"欢迎，{u['name']}")
        st.rerun()

    st.stop()

def login_status_bar():
    if is_logged_in():
        u = st.session_state[SESSION_USER]
        with st.sidebar:
            st.markdown(f"**当前用户：** {u['name']}（{u['user_id']}）")
            if st.button("退出登录", use_container_width=True):
                logout()
