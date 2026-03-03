#!/usr/bin/env python3
"""
网页数据写入器 - 把每日报告保存到 docs/data.json
Web Data Writer - Saves daily reports to docs/data.json for GitHub Pages

每次 GitHub Actions 运行后调用此脚本，将报告追加到 data.json。
网页读取 data.json 展示历史所有报告。
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

DOCS_DIR  = Path(__file__).parent / "docs"
DATA_FILE = DOCS_DIR / "data.json"
MAX_DAYS  = 30  # 最多保留最近30天


def load_data() -> dict:
    """加载现有数据，若不存在则返回空字典。"""
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_data(data: dict):
    """保存数据，同时修剪超过 MAX_DAYS 的旧数据。"""
    DOCS_DIR.mkdir(exist_ok=True)
    # 只保留最近 MAX_DAYS 天
    if len(data) > MAX_DAYS:
        keys = sorted(data.keys())
        for old_key in keys[:len(data) - MAX_DAYS]:
            del data[old_key]
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"✅ 已写入 {DATA_FILE}，共 {len(data)} 天数据")


def save_news(news_cn: str, news_en: str = None):
    """保存每日新闻简报数据。"""
    tz_cst = timezone(timedelta(hours=8))
    today  = datetime.now(tz_cst).strftime("%Y-%m-%d")

    data = load_data()
    if today not in data:
        data[today] = {}
    data[today]["updated"] = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M CST")
    data[today]["news"] = {
        "cn": news_cn,
        "en": news_en or "",
    }
    save_data(data)
    print(f"📰 新闻简报已保存: {today}")


def save_monitor(monitor_cn: str, monitor_en: str):
    """保存市场结构监控数据（中英双语）。"""
    tz_cst = timezone(timedelta(hours=8))
    today  = datetime.now(tz_cst).strftime("%Y-%m-%d")

    data = load_data()
    if today not in data:
        data[today] = {}
    data[today]["updated"] = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M CST")
    data[today]["monitor"] = {
        "cn": monitor_cn,
        "en": monitor_en,
    }
    save_data(data)
    print(f"📌 市场监控已保存: {today}")


if __name__ == "__main__":
    # 测试用：写入示例数据
    save_news(
        news_cn="# 📰 测试简报（中文）\n\n这是测试数据。",
        news_en="# 📰 Test Brief (English)\n\nThis is test data."
    )
    save_monitor(
        monitor_cn="# 📌 测试监控（中文）\n\n## VIX: 20.5",
        monitor_en="# 📌 Test Monitor (English)\n\n## VIX: 20.5"
    )
