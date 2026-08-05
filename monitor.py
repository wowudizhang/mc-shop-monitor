#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MC 商店云端监控（邮件版 · 1分钟粒度）
- GitHub Actions 每5分钟唤醒一次
- 脚本内部循环5轮，每轮 sleep 60s → 等效 1分钟查一次
- 同商品同商家同价格：5分钟内只发1封邮件（防刷屏）
"""

import os
import time
import json
import re
import smtplib
import requests
from email.mime.text import MIMEText
from email.header import Header

# ========== 配置（从 Secrets 读取） ==========
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
ALERT_MAIL = os.getenv("ALERT_MAIL")

API_BASE = "http://103.236.99.176:1201/api/shops"
SITE_ACCESS = os.getenv("SITE_ACCESS")

# ========== 运行参数 ==========
LOOP_COUNT = 5          # 5 轮
SLEEP_SECONDS = 60      # 每轮间隔 60 秒
COOLDOWN = 300          # 同商品 5 分钟内只提醒一次

# ========== 初始化 ==========
session = requests.Session()
session.headers.update({
    "Cookie": f"site_access={SITE_ACCESS}",
    "User-Agent": "Mozilla/5.0"
})

alert_cache = {}  # key -> last_alert_time


def clean_name(name: str) -> str:
    return re.sub(r"§.", "", name or "")


def send_mail(subject: str, body: str):
    """发送邮件（SSL / STARTTLS 自适应）"""
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_MAIL
        msg["Subject"] = Header(subject, "utf-8")

        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=15)
        else:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15)
            server.starttls()

        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [ALERT_MAIL], msg.as_string())
        server.quit()
        print("✅ 邮件发送成功")
    except Exception as e:
        print("❌ 邮件发送失败:", e)


def check_all_tasks(tasks):
    """对全部任务各查一次，命中即发邮件（受冷却限制）"""
    now = time.time()

    for task in tasks:
        keyword = task["keyword"]
        ttype = task["type"]
        max_price = float(task["max_price"])
        stock_only = task.get("stock_only", True)
        sort = "priceAsc" if ttype == "sell" else "priceDesc"

        url = f"{API_BASE}?q={keyword}&type={ttype}&stock=1&sort={sort}&limit=50"

        try:
            r = session.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"❌ 请求失败 [{keyword}]: {e}")
            continue

        for item in data.get("entries", []):
            if stock_only and item.get("amount", 0) <= 0:
                continue

            price = float(item.get("price", 0))
            match = (
                (ttype == "sell" and price <= max_price) or
                (ttype == "buy" and price >= max_price)
            )
            if not match:
                continue

            name = clean_name(item.get("plainName", ""))
            merchant = item.get("merchantName", "")
            world = item.get("worldDisplay", "")
            x, y, z = item.get("x"), item.get("y"), item.get("z")
            amount = item.get("amount")

            key = f"{name}|{merchant}|{price}"
            if key in alert_cache and now - alert_cache[key] < COOLDOWN:
                continue  # 冷却中，跳过

            alert_cache[key] = now

            subject = f"🚨 MC商店提醒：{name} {price}"
            body = (
                f"商品：{name}\n"
                f"类型：{'售卖' if ttype == 'sell' else '收购'}\n"
                f"价格：{price}\n"
                f"库存：{amount}\n"
                f"商家：{merchant}\n"
                f"世界：{world}\n"
                f"坐标：{x},{y},{z}\n"
                f"\n时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            print(f"✅ 命中 [{keyword}]，发送邮件")
            send_mail(subject, body)
            return  # 本轮只发一封，防刷屏


def main():
    print("=" * 50)
    print("📧 MC 商店云端监控（邮件版 · 1分钟粒度）")
    print("=" * 50)

    if not SITE_ACCESS:
        print("❌ 未配置 SITE_ACCESS"); return
    if not all([SMTP_SERVER, SMTP_USER, SMTP_PASS, ALERT_MAIL]):
        print("❌ SMTP 配置不完整"); return

    try:
        tasks = json.loads(os.getenv("MONITOR_TASKS"))
    except Exception as e:
        print("❌ MONITOR_TASKS JSON 解析失败:", e); return

    print(f"📋 共 {len(tasks)} 个监控任务")
    for t in tasks:
        print(f"   - {t['keyword']} {t['type']} 阈值={t['max_price']}")
    print(f"⏱ 每 {SLEEP_SECONDS}s 检查一次，共 {LOOP_COUNT} 轮")
    print("-" * 50)

    for i in range(1, LOOP_COUNT + 1):
        print(f"\n--- 第 {i}/{LOOP_COUNT} 轮 ---")
        check_all_tasks(tasks)
        if i < LOOP_COUNT:
            time.sleep(SLEEP_SECONDS)

    print("\n✅ 本轮监控结束")


if __name__ == "__main__":
    main()
