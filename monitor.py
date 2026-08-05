#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MC 商店云端监控脚本（GitHub Actions 版）
========================================
- 每次 Action 触发后，循环抓取 N 轮（模拟每分钟一次）
- 发现符合条件的商品 → 通过喵提醒推送到微信
- 所有配置从环境变量读取（GitHub Secrets 注入）
"""

import os
import time
import json
import urllib.parse
import urllib.request
import ssl

# ========== 从环境变量读取配置（GitHub Secrets 注入） ==========
SITE_ACCESS   = os.environ.get("SITE_ACCESS", "").strip()
MIAO_ID       = os.environ.get("MIAO_ID", "").strip()
API_BASE      = "http://103.236.99.176:1201/api/shops"

# 监控任务列表（JSON 字符串，GitHub Secret: MONITOR_TASKS）
# 格式：[{"keyword":"遗落","type":"sell","max_price":18,"stock_only":true}, ...]
TASKS_JSON    = os.environ.get("MONITOR_TASKS", "[]")

# 单次 Action 运行参数
LOOP_COUNT    = int(os.environ.get("LOOP_COUNT", "5"))   # 循环轮数（每轮≈1分钟）
SLEEP_SECONDS = int(os.environ.get("SLEEP_SECONDS", "60")) # 每轮间隔

# ========== 工具函数 ==========
def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def clean_name(name):
    """去掉 Minecraft §颜色代码"""
    import re
    return re.sub(r"§.", "", name or "")

def build_url(keyword, type_, stock=1, limit=100):
    sort = "priceAsc" if type_ == "sell" else "priceDesc"
    q = urllib.parse.quote(keyword)
    return f"{API_BASE}?q={q}&type={type_}&merchant=all&stock={stock}&sort={sort}&limit={limit}"

def fetch_json(url):
    """带 Cookie 请求 API"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url)
    req.add_header("Cookie", f"site_access={SITE_ACCESS}")
    req.add_header("User-Agent", "MC-Monitor/1.0")
    req.add_header("Accept", "application/json")

    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def send_miao(text):
    """发送喵提醒到微信"""
    if not MIAO_ID:
        log("⚠️ 未配置 MIAO_ID，跳过推送")
        return
    url = f"https://miaotixing.com/trigger?id={MIAO_ID}"
    data = urllib.parse.urlencode({"text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            log(f"✅ 喵提醒推送成功: {resp.read().decode()[:50]}")
    except Exception as e:
        log(f"❌ 喵提醒推送失败: {e}")

def check_task(task):
    """检查单个监控任务"""
    keyword   = task["keyword"]
    type_     = task["type"]          # sell / buy
    max_price = float(task.get("max_price", 999))
    min_price = float(task.get("min_price", 0))
    stock_only = task.get("stock_only", True)

    log(f"🔍 查询: {keyword} | 类型: {type_}")

    url = build_url(keyword, type_, stock=1 if stock_only else 0)
    data = fetch_json(url)
    entries = data.get("entries", [])

    hits = []
    for e in entries:
        price  = float(e.get("price", 0))
        amount = int(e.get("amount", 0))
        if stock_only and amount <= 0:
            continue
        if type_ == "sell":
            if price <= max_price:
                hits.append(e)
        else:  # buy
            if price >= max_price:
                hits.append(e)

    if hits:
        for h in hits[:5]:  # 最多推5条
            name = clean_name(h.get("plainName", ""))
            text = (
                f"🎯 MC商店提醒\n"
                f"商品: {name}\n"
                f"类型: {'售卖' if type_=='sell' else '收购'}\n"
                f"价格: {h['price']} (阈值: {max_price})\n"
                f"数量: {h.get('amount','?')}\n"
                f"商家: {h.get('merchantName','')}\n"
                f"世界: {h.get('worldDisplay', h.get('world',''))}\n"
                f"坐标: ({h.get('x','?')},{h.get('y','?')},{h.get('z','?')})"
            )
            send_miao(text)
            time.sleep(1)  # 防止推送过快
        log(f"✅ 命中 {len(hits)} 条")
    else:
        log(f"ℹ️ 无符合条件商品 (共 {len(entries)} 条)")

def main():
    log("=" * 50)
    log("MC 商店云端监控启动")
    log(f"Cookie: {'已配置' if SITE_ACCESS else '❌ 未配置'}")
    log(f"喵提醒: {'已配置' if MIAO_ID else '❌ 未配置'}")

    try:
        tasks = json.loads(TASKS_JSON)
    except json.JSONDecodeError:
        log("❌ MONITOR_TASKS JSON 解析失败")
        return

    if not tasks:
        log("⚠️ 没有配置监控任务，请在 Secrets 中设置 MONITOR_TASKS")
        return

    log(f"📋 共 {len(tasks)} 个监控任务")
    for t in tasks:
        log(f"   - {t.get('keyword','?')} [{t.get('type','?')}] 阈值={t.get('max_price','?')}")

    # 先跑一次
    for task in tasks:
        try:
            check_task(task)
        except Exception as e:
            log(f"❌ 任务异常: {e}")
        time.sleep(2)

    # 循环多轮（模拟每分钟一次）
    for i in range(1, LOOP_COUNT):
        log(f"\n--- 第 {i+1}/{LOOP_COUNT} 轮 ---")
        time.sleep(SLEEP_SECONDS)
        for task in tasks:
            try:
                check_task(task)
            except Exception as e:
                log(f"❌ 任务异常: {e}")
            time.sleep(2)

    log("=" * 50)
    log("本轮监控结束")

if __name__ == "__main__":
    main()
