#!/usr/bin/env python3
"""
网页数据写入器 - 把每日报告保存到 docs/data.json
Web Data Writer - Saves daily reports to docs/data.json for GitHub Pages
"""

import json
import os
import requests
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

DOCS_DIR  = Path(__file__).parent / "docs"
DATA_FILE = DOCS_DIR / "data.json"
MAX_DAYS  = 30

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL   = "claude-sonnet-4-20250514"

CATEGORY_CN = {
    "finance": "📈 金融财经",
    "social":  "📱 自媒体精选",
    "wellness": "🧠 健康·心理·美学",
}

CATEGORY_EN = {
    "finance": "📈 Finance & Markets",
    "social":  "📱 Tech & Media",
    "wellness": "🧠 Health & Wellness",
}


def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_data(data: dict):
    DOCS_DIR.mkdir(exist_ok=True)
    if len(data) > MAX_DAYS:
        keys = sorted(data.keys())
        for old_key in keys[:len(data) - MAX_DAYS]:
            del data[old_key]
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log.info(f"✅ 已写入 {DATA_FILE}，共 {len(data)} 天数据")


def translate_news_to_cn(news_data: dict) -> str:
    """
    调用 Claude API 将新闻标题批量翻译成中文，生成中文版简报。
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.warning("未设置 ANTHROPIC_API_KEY，跳过翻译")
        return ""

    # 构建要翻译的新闻列表
    tz_cst = timezone(timedelta(hours=8))
    date_str = datetime.now(tz_cst).strftime("%Y年%m月%d日")

    lines_to_translate = []
    for cat, items in news_data.items():
        cat_label = CATEGORY_CN.get(cat, cat)
        lines_to_translate.append(f"\n## {cat_label}\n")
        for item in items:
            lines_to_translate.append(f"- [{item['source']}] {item['title']}")

    news_en_text = "\n".join(lines_to_translate)

    prompt = f"""请将以下英文新闻标题翻译成中文，保持原有的格式和结构不变。
只翻译标题文字，保留来源标签（方括号内的内容）不翻译，保留 ## 和 - 格式符号。

今天日期：{date_str}

需要翻译的内容：
{news_en_text}

直接输出翻译结果，不需要任何解释或前言。格式示例：
## 📈 金融财经
- [Reuters Business] 美联储暗示今年可能降息两次"""

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}]
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    for attempt in range(1, 4):
        try:
            log.info(f"   🔤 翻译新闻标题 第{attempt}次...")
            resp = requests.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            text = "".join(
                b.get("text", "") for b in data.get("content", [])
                if b.get("type") == "text"
            )
            if text.strip():
                log.info("   ✅ 翻译完成")
                # Add header
                return f"# 📰 每日智识简报（中文）\n### {date_str}\n\n" + text.strip()
        except Exception as e:
            log.warning(f"   ⚠️ 翻译第{attempt}次失败: {e}")
        if attempt < 3:
            time.sleep(30)

    return ""


def format_news_en(news_data: dict) -> str:
    """格式化英文版新闻简报。"""
    tz_cst = timezone(timedelta(hours=8))
    date_str = datetime.now(tz_cst).strftime("%B %d, %Y")

    lines = [f"# 📰 Daily Intelligence Brief", f"### {date_str}\n"]
    for cat, items in news_data.items():
        cat_label = CATEGORY_EN.get(cat, cat)
        lines.append(f"\n## {cat_label}\n")
        for item in items:
            lines.append(f"- [{item['source']}] {item['title']}")
    return "\n".join(lines)


def save_news(news_data: dict = None, news_cn: str = None, news_en: str = None):
    """
    保存每日新闻简报。
    支持两种调用方式：
      1. save_news(news_data=dict)  → 自动生成英文版并调用API翻译中文版
      2. save_news(news_cn=str, news_en=str)  → 直接传入文本
    """
    tz_cst = timezone(timedelta(hours=8))
    today  = datetime.now(tz_cst).strftime("%Y-%m-%d")

    if news_data is not None:
        # 生成英文版
        news_en = format_news_en(news_data)
        # 调用 Claude 翻译中文版
        news_cn = translate_news_to_cn(news_data)

    data = load_data()
    if today not in data:
        data[today] = {}
    data[today]["updated"] = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M CST")
    data[today]["news"] = {
        "cn": news_cn or "",
        "en": news_en or "",
    }
    save_data(data)
    log.info(f"📰 新闻简报已保存: {today}")


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
    log.info(f"📌 市场监控已保存: {today}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 测试
    save_monitor("# 测试中文", "# Test English")
