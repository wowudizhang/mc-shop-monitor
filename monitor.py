#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MC 商店云端监控（邮件版 · 汇总发送）
- 每轮扫描结束后，将本轮所有命中结果汇总为一封邮件
"""

import os
import time
import json
import re
import smtplib
import requests
from email.mime.text import MIMEText
from email.header import Header

# ========== 配置 ==========
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
ALERT_MAIL = os.getenv("ALERT_MAIL")

API_BASE = "http://103.236.99.176:1201/api/shops"
SITE_ACCESS = os.getenv("SITE_ACCESS")

LOOP_COUNT = 5
SLEEP_SECONDS = 60
COOLDOWN = 300

session = requests.Session()
session.headers.update({
    "Cookie": f"site_access={SITE_ACCESS}",
    "User-Agent": "Mozilla/5.0"
})

alert_cache = {}

def clean_name(name: str) -> str:
    return re.sub(r"§.", "", name or "")

def send_mail(subject: str, body: str):
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
    now = time.time()
    hits = []  # ✅ 本轮命中结果收集

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
                continue

            alert_cache[key] = now
            hits.append({
                "name": name,
                "price": price,
                "amount": amount,
                "merchant": merchant,
                "world": world,
                "coord": f"{x},{y},{z}",
                "type": ttype
            })

    # ✅ 本轮结束后统一发一封邮件
    if hits:
        subject = f"🚨 MC商店提醒：共 {len(hits)} 条命中"
        body_lines = [f"扫描时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
        for h in hits:
            body_lines.append(
                f"【{h['name']}】\n"
                f"类型：{'售卖' if h['type'] == 'sell' else '收购'}\n"
                f"价格：{h['price']}  库存：{h['amount']}\n"
                f"商家：{h['merchant']}\n"
                f"世界：{h['world']}\n"
                f"坐标：{h['coord']}\n"
            )
        send_mail(subject, "\n".join(body_lines))
        print(f"✅ 本轮汇总发送 {len(hits)} 条")
    else:
        print("ℹ️ 本轮无命中")

def main():
    print("=" * 60)
    print("📧 MC 商店云端监控（汇总邮件版）")
    print("=" * 60)

    if not all([SITE_ACCESS, SMTP_SERVER, SMTP_USER, SMTP_PASS, ALERT_MAIL]):
        print("❌ 配置不完整")
        return

    tasks = json.loads(os.getenv("MONITOR_TASKS"))
    print(f"📋 共 {len(tasks)} 个监控任务")

    for i in range(1, LOOP_COUNT + 1):
        print(f"\n--- 第 {i}/{LOOP_COUNT} 轮 ---")
        check_all_tasks(tasks)
        if i < LOOP_COUNT:
            time.sleep(SLEEP_SECONDS)

    print("\n✅ 本轮监控结束")

if __name__ == "__main__":
    main()
