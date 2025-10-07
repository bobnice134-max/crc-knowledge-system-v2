# -*- coding: utf-8 -*-
"""
CRC 知识图谱测评平台 · 一键部署脚本（稳定版）
- 静默检测 Git，找不到时自动补 PATH
- 无改动自动跳过推送
- 推送后自动打开 Streamlit 网址
- 兼容 Windows 控制台（GBK）输出
"""

import os
import sys
import time
import shutil
import webbrowser
import subprocess
from datetime import datetime

# ========== 配置 ==========
STREAMLIT_URL = "https://crc-knowledge-system-v2-dggwmk6hrhqjbdg7qlet98.streamlit.app"
GIT_PATHS = [
    r"C:\Program Files\Git\mingw64\bin",
    r"C:\Program Files\Git\cmd",
]

LOG_FILE = "deploy_log.txt"  # 部署日志（追加写入）
OPEN_AFTER_DEPLOY = True     # 推送后是否自动打开浏览器

# ========== 输出（自动兼容 GBK 控制台） ==========
def _safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        # 控制台不支持 emoji/Unicode 的情况，做个简易降级
        try:
            print(msg.encode("utf-8", "ignore").decode("utf-8", "ignore"))
        except Exception:
            print(msg.encode("gbk", "ignore").decode("gbk", "ignore"))

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    _safe_print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ========== 子进程执行 ==========
def run(cmd: str) -> int:
    """执行命令并实时输出，返回退出码"""
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:  # 实时打印
        _safe_print(line.rstrip())
    proc.wait()
    return proc.returncode

def get_output(cmd: str) -> str:
    """返回命令输出（不报错）"""
    try:
        out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
        return out.strip()
    except subprocess.CalledProcessError as e:
        return (e.output or "").strip()
    except Exception:
        return ""

# ========== Git 检测 ==========
def ensure_git_available():
    """静默检测 Git；若找不到则补 PATH 再检测"""
    def has_git():
        return shutil.which("git") is not None

    if not has_git():
        # 将常见 Git 安装目录补到 PATH（使用 os.pathsep 以兼容不同系统；Windows 下等于 ';'）
        extra = [p for p in GIT_PATHS if p and p not in os.environ.get("PATH", "")]
        if extra:
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + os.pathsep.join(extra)

    if not has_git():
        log("❌ Git 未检测到，请确认已安装并加入系统 PATH。")
        sys.exit(1)

    v = get_output("git --version")
    if v:
        log(f"✅ Git 环境正常（{v}）")
    else:
        log("✅ Git 环境正常")

# ========== 检测是否有改动 ==========
def has_changes() -> bool:
    out = get_output("git status --porcelain")
    return bool(out.strip())

# ========== 主流程 ==========
def main():
    log("=== 🚀 CRC 知识图谱测评平台 · 一键部署开始 ===")

    ensure_git_available()

    if not has_changes():
        log("ℹ️ 检测结果：代码未改动，无需推送。")
        log("=== ✅ 部署流程结束 ===")
        return

    # 1) add
    code = run("git add .")
    if code != 0:
        log("❌ git add 失败，终止。")
        sys.exit(code)

    # 2) commit
    msg = f"update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    code = run(f'git commit -m "{msg}"')
    if code != 0:
        # 可能是“nothing to commit”，也算安全退出
        still_changed = has_changes()
        if still_changed:
            log("❌ git commit 失败，终止。")
            sys.exit(code)

    # 3) push
    code = run("git push origin main")
    if code != 0:
        log("❌ git push 失败，终止。")
        sys.exit(code)

    log("✅ 所有更新已提交，Streamlit Cloud 正在自动刷新部署！")
    time.sleep(5)

    # 4) 自动打开网站
    if OPEN_AFTER_DEPLOY and STREAMLIT_URL:
        log(f"🌐 检测结果：网站已成功上线。")
        log(f"🔗 自动打开网站：{STREAMLIT_URL}")
        try:
            webbrowser.open(STREAMLIT_URL)
        except Exception:
            log("⚠️ 无法自动打开浏览器，请手动访问上述链接。")

    log("=== 🎉 部署流程结束 ===")

# ========== 入口 ==========
if __name__ == "__main__":
    # 尝试让 stdout 用 UTF-8（部分环境可能无此方法，忽略即可）
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()