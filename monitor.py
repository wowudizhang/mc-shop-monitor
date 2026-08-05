#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MC 商店监控 - 自诊断版
用途：专门查 GitHub Secrets 为什么没加载
"""

import os
import sys

REQUIRED = [
    "SITE_ACCESS",
    "SMTP_SERVER",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASS",
    "ALERT_MAIL",
    "MONITOR_TASKS",
]

def main():
    print("=" * 60)
    print("🐞 MC 商店监控 - Secrets 自检")
    print("=" * 60)

    missing = []
    for name in REQUIRED:
        v = os.getenv(name)
        if v is None:
            print(f"❌ {name} = None（根本不存在）")
            missing.append(name)
        elif v.strip() == "":
            print(f"❌ {name} = 空字符串（有名字但没内容）")
            missing.append(name)
        else:
            print(f"✅ {name} = 已加载（长度={len(v)}）")

    print("-" * 60)
    if missing:
        print("❌ 以下 Secrets 有问题：")
        for m in missing:
            print(f"   • {m}")
        print("\n👉 请去 GitHub → Settings → Secrets and variables → Actions")
        print("👉 确认这些名字一字不差，且都已填写")
        sys.exit(1)
    else:
        print("✅ 所有 Secrets 均已加载，问题不在这")

    print("=" * 60)

if __name__ == "__main__":
    main()
