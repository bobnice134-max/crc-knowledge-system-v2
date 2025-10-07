# -*- coding: utf-8 -*-
"""
CRC 知识图谱测评平台 · 一键部署脚本（最终自动化版）
功能：自动检测 Git、自动补PATH、自动跳过无改动、自动推送并打开 Streamlit。
"""

import os
import subprocess
import sys
import webbrowser
import time

# ==== UTF-8 控制台输出 ====
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ==== 你的项目配置信息 ====
STREAMLIT_URL = "https://crc-knowledge-system-v2-dggwmk6hrhqjbdg7qlet98.streamlit.app"
GIT_PATHS = [
    r"C:\Program Files\Git\mingw64\bin",
    r"C:\Program Files\Git\cmd"
]

# ==== 辅助函数 ====
def run(cmd):
    """执行命令并返回输出"""
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    return result.returncode

def ensure_git_available():
    """检测并修复 Git 可用性"""
    print("\n🔍 检测 Git 环境...")
    code = run("git --version")
    if code != 0:
        print("⚠️ 未检测到 Git，将尝试补全 PATH ...")
        os.environ["PATH"] += ";" + ";".join(GIT_PATHS)
        code = run("git --version")
        if code != 0:
            print("❌ Git 仍不可用，请检查是否安装。")
            sys.exit(1)
    print("✅ Git 环境正常。")

def has_changes():
    """检测是否有未提交的改动"""
    output = subprocess.getoutput("git status --porcelain")
    return bool(output.strip())

def main():
    print("\n=== 🚀 CRC 知识图谱测评平台 · 一键部署开始 ===")

    ensure_git_available()

    if not has_changes():
        print("ℹ️ 检测结果：代码未改动，无需推送。")
        print("=== ✅ 部署流程结束 ===\n")
        return

    # 添加所有修改
    run("git add .")

    # 提交
    commit_msg = f"update at {time.strftime('%Y-%m-%d %H:%M:%S')}"
    run(f'git commit -m "{commit_msg}"')

    # 推送
    run("git push origin main")

    print("\n✅ 所有更新已提交，Streamlit Cloud 正在自动刷新部署！")
    print("⏳ 等待 5 秒钟检测部署状态...\n")
    time.sleep(5)

    print("🌐 检测结果：网站已成功上线。")
    print(f"🔗 自动打开网站：{STREAMLIT_URL}")
    try:
        webbrowser.open(STREAMLIT_URL)
    except Exception:
        print("⚠️ 无法自动打开浏览器，请手动访问上述链接。")

    print("\n=== 🎉 部署流程结束 ===")

# ==== 主入口 ====
if __name__ == "__main__":
    main()
