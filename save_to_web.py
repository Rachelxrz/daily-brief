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


def _call_claude(prompt: str, max_tokens: int = 3000) -> str:
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
            resp = requests.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            text = "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text")
            if text.strip():
                return text.strip()
        except Exception as e:
            log.warning(f"   ⚠️ Claude 调用第{attempt}次失败: {e}")
        if attempt < 3:
            time.sleep(60)
    return ""


def _parse_json(text: str):
    """健壮的 JSON 解析，处理 markdown 代码块和多余文字。"""
    clean = text.strip()
    if "```" in clean:
        parts = clean.split("```")
        for p in parts:
            p2 = p.strip()
            if p2.startswith("json"):
                p2 = p2[4:].strip()
            if p2.startswith("{"):
                clean = p2
                break
    start = clean.find("{")
    end   = clean.rfind("}")
    if start != -1 and end != -1:
        clean = clean[start:end+1]
    return json.loads(clean)


def generate_news_with_insights(news_data: dict) -> tuple:
    """
    调用 Claude 生成：
    - 每条新闻：中文标题 + 英文标题 + 3句话描述（中英各自）
    - 全局洞察：投资3条 + 健康3条（中英各自）
    返回 (cn_report, en_report)
    """
    tz_cst  = timezone(timedelta(hours=8))
    date_cn = datetime.now(tz_cst).strftime("%Y年%m月%d日")
    date_en = datetime.now(tz_cst).strftime("%B %d, %Y")

    # 构建新闻列表
    news_lines = []
    for cat, items in news_data.items():
        news_lines.append(f"\n[{CATEGORY_EN.get(cat, cat)}]")
        for i, item in enumerate(items, 1):
            news_lines.append(f"{i}. [{item['source']}] {item['title']}")
    news_text = "\n".join(news_lines)

    prompt = f"""You are a professional investment advisor and health advisor. Below are today's curated news ({date_en}).

For EACH news item, provide:
1. title_cn: Chinese translation of the title
2. summary_cn: 3-sentence Chinese summary/description of the story
3. summary_en: 3-sentence English summary/description of the story

Then provide GLOBAL INSIGHTS (based on ALL news combined):
- investment_insights_cn: exactly 3 actionable investment insights in Chinese (each max 30 chars)
- investment_insights_en: exactly 3 actionable investment insights in English (each max 15 words)
- health_insights_cn: exactly 3 actionable health/wellness insights in Chinese (each max 30 chars)
- health_insights_en: exactly 3 actionable health/wellness insights in English (each max 15 words)

IMPORTANT: Output ONLY valid JSON. No markdown. No quotes inside string values (use alternate phrasing instead).

JSON format:
{{
  "articles": {{
    "finance": [
      {{"title_en": "...", "title_cn": "...", "summary_cn": "...", "summary_en": "..."}},
      {{"title_en": "...", "title_cn": "...", "summary_cn": "...", "summary_en": "..."}}
    ],
    "social": [...],
    "wellness": [...]
  }},
  "insights": {{
    "investment_cn": ["洞察1", "洞察2", "洞察3"],
    "investment_en": ["insight 1", "insight 2", "insight 3"],
    "health_cn": ["洞察1", "洞察2", "洞察3"],
    "health_en": ["insight 1", "insight 2", "insight 3"]
  }}
}}

News list:
{news_text}"""

    log.info("🤖 调用 Claude 生成新闻内容与洞察...")
    result = _call_claude(prompt, max_tokens=4000)

    if not result:
        log.warning("⚠️ 内容生成失败，使用纯标题版")
        return "", _format_plain_en(news_data, date_en)

    try:
        parsed = _parse_json(result)
    except Exception as e:
        log.warning(f"⚠️ JSON 解析失败: {e}")
        log.warning(f"   返回内容预览: {result[:300]}")
        return "", _format_plain_en(news_data, date_en)

    articles = parsed.get("articles", {})
    insights = parsed.get("insights", {})

    # ── 生成中文版 ──────────────────────────────────────
    cn = [f"# 📰 每日智识简报（中文）", f"### {date_cn}\n"]
    for cat_key in ["finance", "social", "wellness"]:
        items_parsed = articles.get(cat_key, [])
        orig_items   = news_data.get(cat_key, [])
        if not items_parsed:
            continue
        cn.append(f"\n## {CATEGORY_CN.get(cat_key, cat_key)}\n")
        for i, p in enumerate(items_parsed):
            title_cn  = p.get("title_cn", orig_items[i]["title"] if i < len(orig_items) else "")
            summary_cn = p.get("summary_cn", "")
            cn.append(f"**{title_cn}**")
            if summary_cn:
                cn.append(f"\n{summary_cn}\n")

    # 中文全局洞察
    inv_cn    = insights.get("investment_cn", [])
    health_cn = insights.get("health_cn", [])
    if inv_cn or health_cn:
        cn.append("\n---\n## 💡 今日洞察\n")
        if inv_cn:
            cn.append("**📈 投资建议**")
            for s in inv_cn[:3]:
                cn.append(f"- {s}")
            cn.append("")
        if health_cn:
            cn.append("**🧠 健康建议**")
            for s in health_cn[:3]:
                cn.append(f"- {s}")

    # ── 生成英文版 ──────────────────────────────────────
    en = [f"# 📰 Daily Intelligence Brief", f"### {date_en}\n"]
    for cat_key in ["finance", "social", "wellness"]:
        items_parsed = articles.get(cat_key, [])
        orig_items   = news_data.get(cat_key, [])
        if not items_parsed:
            continue
        en.append(f"\n## {CATEGORY_EN.get(cat_key, cat_key)}\n")
        for i, p in enumerate(items_parsed):
            title_en   = p.get("title_en", orig_items[i]["title"] if i < len(orig_items) else "")
            summary_en = p.get("summary_en", "")
            url = orig_items[i].get("url","") if i < len(orig_items) else ""
            if url:
                en.append(f"**[{title_en}]({url})**")
            else:
                en.append(f"**{title_en}**")
            if summary_en:
                en.append(f"\n{summary_en}\n")

    # 英文全局洞察
    inv_en    = insights.get("investment_en", [])
    health_en = insights.get("health_en", [])
    if inv_en or health_en:
        en.append("\n---\n## 💡 Today's Insights\n")
        if inv_en:
            en.append("**📈 Investment**")
            for s in inv_en[:3]:
                en.append(f"- {s}")
            en.append("")
        if health_en:
            en.append("**🧠 Health & Wellness**")
            for s in health_en[:3]:
                en.append(f"- {s}")

    return "\n".join(cn), "\n".join(en)


def _format_plain_en(news_data: dict, date_en: str) -> str:
    lines = [f"# 📰 Daily Intelligence Brief", f"### {date_en}\n"]
    for cat, items in news_data.items():
        lines.append(f"\n## {CATEGORY_EN.get(cat, cat)}\n")
        for item in items:
            lines.append(f"- [{item['source']}] {item['title']}")
    return "\n".join(lines)


def save_news(news_data: dict = None, news_cn: str = None, news_en: str = None):
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
    tz_cst = timezone(timedelta(hours=8))
    today  = datetime.now(tz_cst).strftime("%Y-%m-%d")
    data = load_data()
    if today not in data:
        data[today] = {}
    data[today]["updated"] = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M CST")
    data[today]["monitor"] = {"cn": monitor_cn, "en": monitor_en}
    save_data(data)
    log.info(f"📌 市场监控已保存: {today}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    save_monitor("# 测试中文", "# Test English")
