# -*- coding: utf-8 -*-
# 一键部署脚本：自动 git 提交 + 推送 Streamlit 更新
# 作者：刘航博（自动生成版）

import os
import subprocess
from datetime import datetime

def run(cmd):
    """运行系统命令"""
    print(f"\n🚀 正在执行：{cmd}")
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"❌ 命令执行失败：{cmd}")
    print("✅ 执行成功")

def main():
    print("=== CRC 知识图谱测评平台 · 一键部署开始 ===")
    os.chdir(os.path.dirname(__file__))  # 切换到当前项目目录

    # 1. git add .
    run("git add .")

    # 2. git commit -m "update + 时间"
    commit_msg = f"update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    run(f'git commit -m "{commit_msg}"')

    # 3. git push
    run("git push")

    print("\n🎉 所有更新已提交，Streamlit Cloud 将自动重新部署！")
    print("🌐 部署地址：https://crc-knowledge-system-v2-dggwmk6hrhqjbdg7qlet98.streamlit.app/")
    print("⏱️ 通常需要 1–2 分钟自动刷新。")

if __name__ == "__main__":
    main()
