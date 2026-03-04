#!/usr/bin/env python3
"""
网页数据写入器 - 把每日报告保存到 docs/data.json
包含 AI 洞察生成
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
    "finance":  "📈 金融财经",
    "social":   "📱 自媒体精选",
    "wellness": "🧠 健康·心理·美学",
}
CATEGORY_EN = {
    "finance":  "📈 Finance & Markets",
    "social":   "📱 Tech & Media",
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


def _call_claude(prompt: str, max_tokens: int = 2000) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    for attempt in range(1, 4):
        try:
            resp = requests.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            text = "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text")
            if text.strip():
                return text.strip()
        except Exception as e:
            log.warning(f"   ⚠️ Claude 调用第{attempt}次失败: {e}")
        if attempt < 3:
            time.sleep(30)
    return ""


def generate_news_with_insights(news_data: dict) -> tuple[str, str]:
    """
    调用 Claude 一次性生成：
    - 每条新闻的中文翻译 + 一句话 AI 洞察
    返回 (cn_report, en_report)
    """
    tz_cst   = timezone(timedelta(hours=8))
    date_cn  = datetime.now(tz_cst).strftime("%Y年%m月%d日")
    date_en  = datetime.now(tz_cst).strftime("%B %d, %Y")

    # 构建新闻列表
    news_lines = []
    for cat, items in news_data.items():
        cat_en = CATEGORY_EN.get(cat, cat)
        news_lines.append(f"\n[{cat_en}]")
        for i, item in enumerate(items, 1):
            news_lines.append(f"{i}. [{item['source']}] {item['title']}")

    news_text = "\n".join(news_lines)

    prompt = f"""你是一位专业的投资顾问和健康顾问。以下是今日精选新闻（{date_en}）。

请为每一条新闻：
1. 翻译标题为中文
2. 写一句话洞察（从投资价值、个人健康、或趋势判断角度，20字以内，直接、有洞见）

严格按以下 JSON 格式输出，不要任何其他内容：
{{
  "date": "{date_cn}",
  "categories": {{
    "finance": [
      {{"title_en": "原英文标题", "title_cn": "中文翻译", "insight": "一句话洞察"}},
      ...
    ],
    "social": [...],
    "wellness": [...]
  }}
}}

新闻列表：
{news_text}"""

    log.info("🤖 调用 Claude 生成新闻洞察...")
    result = _call_claude(prompt, max_tokens=3000)

    if not result:
        log.warning("⚠️ 洞察生成失败，使用纯英文版")
        return "", _format_plain_en(news_data, date_en)

    # 解析 JSON
    try:
        # 清理可能的 markdown 代码块
        clean = result.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:])
        if clean.endswith("```"):
            clean = "\n".join(clean.split("\n")[:-1])
        parsed = json.loads(clean.strip())
    except Exception as e:
        log.warning(f"⚠️ JSON 解析失败: {e}，使用纯英文版")
        return "", _format_plain_en(news_data, date_en)

    # 生成中文版 Markdown
    cn_lines = [f"# 📰 每日智识简报（中文）", f"### {date_cn}\n"]
    en_lines = [f"# 📰 Daily Intelligence Brief", f"### {date_en}\n"]

    cats = parsed.get("categories", {})
    for cat_key in ["finance", "social", "wellness"]:
        items_parsed = cats.get(cat_key, [])
        orig_items   = news_data.get(cat_key, [])
        if not items_parsed:
            continue

        cn_lines.append(f"\n## {CATEGORY_CN.get(cat_key, cat_key)}\n")
        en_lines.append(f"\n## {CATEGORY_EN.get(cat_key, cat_key)}\n")

        for i, p in enumerate(items_parsed):
            title_cn = p.get("title_cn", "")
            title_en = p.get("title_en", "")
            insight  = p.get("insight", "")
            # 获取原始 url
            url = orig_items[i]["url"] if i < len(orig_items) else ""
            source = orig_items[i]["source"] if i < len(orig_items) else ""

            if title_cn:
                cn_lines.append(f"- **{title_cn}**")
                if insight:
                    cn_lines.append(f"  > 💡 {insight}")
            if title_en:
                en_line = f"- **[{title_en}]({url})**" if url else f"- **{title_en}**"
                en_lines.append(en_line)
                if insight:
                    en_lines.append(f"  > 💡 {insight}")

    cn_report = "\n".join(cn_lines)
    en_report = "\n".join(en_lines)
    return cn_report, en_report


def _format_plain_en(news_data: dict, date_en: str) -> str:
    """无 AI 洞察时的纯英文备用版本。"""
    lines = [f"# 📰 Daily Intelligence Brief", f"### {date_en}\n"]
    for cat, items in news_data.items():
        lines.append(f"\n## {CATEGORY_EN.get(cat, cat)}\n")
        for item in items:
            lines.append(f"- [{item['source']}] {item['title']}")
    return "\n".join(lines)


def save_news(news_data: dict = None, news_cn: str = None, news_en: str = None):
    """保存每日新闻简报。"""
    tz_cst = timezone(timedelta(hours=8))
    today  = datetime.now(tz_cst).strftime("%Y-%m-%d")

    if news_data is not None:
        news_cn, news_en = generate_news_with_insights(news_data)

    data = load_data()
    if today not in data:
        data[today] = {}
    data[today]["updated"] = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M CST")
    existing = data[today].get("news", {})
    data[today]["news"] = {
        "cn": news_cn if news_cn else existing.get("cn", ""),
        "en": news_en if news_en else existing.get("en", ""),
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
    save_monitor("# 测试中文", "# Test English")
