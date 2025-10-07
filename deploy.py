# -*- coding: utf-8 -*-
# 一键部署脚本：自动 git 提交 + 推送 Streamlit 更新
import os, subprocess, sys
from datetime import datetime

# ========== 自动补全 Git 路径 ==========
# 如果系统找不到 git，这里强制加到 PATH 中（兼容 Windows）
os.environ["PATH"] += r";C:\Program Files\Git\cmd;C:\Program Files\Git\bin"

def run(cmd):
    print(f"\n🚀 执行：{cmd}")
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if result.stdout: print(result.stdout)
    if result.stderr: print(result.stderr)
    if result.returncode != 0: raise RuntimeError(f"❌ 命令失败：{cmd}")

def main():
    os.chdir(os.path.dirname(__file__))
    print("=== CRC 知识图谱测评平台 · 一键部署开始 ===")
    subprocess.call("git add .", shell=True)
    msg = f"update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    subprocess.call(f'git commit -m "{msg}"', shell=True)
    subprocess.call("git push", shell=True)
    print("\n✅ 所有更新已提交，Streamlit Cloud 正在自动刷新部署！")

if __name__ == "__main__":
    # 统一输出编码为 UTF-8，防止 emoji 报错
    sys.stdout.reconfigure(encoding="utf-8")
    main()