# -*- coding: utf-8 -*-
"""
CRC 知识图谱测评平台 · 一键部署脚本（Windows安全版）
修复：
1️⃣ 兼容 Windows GBK 终端（移除 emoji）
2️⃣ 检测 Git 命令是否可用
3️⃣ 智能检测 Streamlit 部署完成后再打开网站
"""

import os
import subprocess
import datetime
import webbrowser
import time
import requests
import shutil
import os
os.environ["PATH"] += r";C:\Program Files\Git\bin;C:\Program Files\Git\cmd"
import sys
sys.stdout.reconfigure(encoding='utf-8')

# === 配置 ===
REPO_URL = "https://github.com/bobnice134-max/crc-knowledge-system-v2.git"
STREAMLIT_URL = "https://crc-knowledge-system-v2-dggwmk6hrhqjbdg7qlet98.streamlit.app"
LOG_FILE = "deploy_log.txt"

def run(cmd):
    """执行命令并返回输出文本"""
    return subprocess.getoutput(cmd)

def log_write(text):
    """写入日志文件"""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")

def wait_for_streamlit_ready(url, timeout=300):
    """检测 Streamlit 是否已成功部署"""
    print(f"正在检测 Streamlit 部署状态（最多等待 {timeout//60} 分钟）...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                print("检测结果：网站已成功上线。")
                return True
        except requests.RequestException:
            pass
        time.sleep(10)
    print("警告：未在超时时间内检测到部署完成（可能仍在构建中）")
    return False

def main():
    print("\n=== CRC 知识图谱测评平台 · 一键部署开始 ===\n")

    # Step 0. 检查 git 是否可用
    if not shutil.which("git"):
        print("错误：未检测到 Git，请确保已安装并加入系统环境变量。")
        return

    # Step 1. 检查是否有改动
    status = run("git status --porcelain")
    if not status.strip():
        print("代码未改动，无需推送。")
        log_write(f"[{datetime.datetime.now()}] 无改动，跳过部署。")
        return

    # Step 2. 提交变更
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(run("git add ."))
    print(run(f'git commit -m "update at {now}"'))

    # Step 3. 推送到 GitHub
    print(run("git push -u origin main"))

    # Step 4. 检测部署
    print("\n所有更新已提交，Streamlit Cloud 正在自动刷新部署。")
    if wait_for_streamlit_ready(STREAMLIT_URL):
        print(f"自动打开网站：{STREAMLIT_URL}")
        webbrowser.open(STREAMLIT_URL)
    else:
        print(f"请稍后手动访问：{STREAMLIT_URL}")

    # Step 5. 写入日志
    log_write(f"[{now}] 已推送至 GitHub，触发 Streamlit 部署检测。")

    print("\n=== 部署流程结束 ===")

if __name__ == "__main__":
    main()
