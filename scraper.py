#!/usr/bin/env python3
"""
每日智识简报 - 新闻抓取引擎（中文版）
- 抓取英文 RSS 新闻
- 调用 Claude API 翻译标题 + 生成3-5句中文摘要
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import json, re, time, logging, os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/scraper.log', encoding='utf-8')
    ]
)
log = logging.getLogger(__name__)

# ─── RSS 来源配置 ──────────────────────────────────────────
FEEDS = {
    "finance": [
        {"name": "Reuters",         "url": "https://feeds.reuters.com/reuters/businessNews"},
        {"name": "CNBC",            "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html"},
        {"name": "Yahoo Finance",   "url": "https://finance.yahoo.com/news/rssindex"},
        {"name": "FT",              "url": "https://www.ft.com/rss/home/uk"},
        {"name": "Bloomberg",       "url": "https://feeds.bloomberg.com/markets/news.rss"},
        {"name": "WSJ",             "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"},
        {"name": "Investing.com",   "url": "https://www.investing.com/rss/news_25.rss"},
        {"name": "Seeking Alpha",   "url": "https://seekingalpha.com/market_currents.xml"},
    ],
    "social": [
        {"name": "Hacker News",     "url": "https://hnrss.org/frontpage"},
        {"name": "TechCrunch",      "url": "https://techcrunch.com/feed/"},
        {"name": "The Verge",       "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "Wired",           "url": "https://www.wired.com/feed/rss"},
        {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/"},
        {"name": "Ars Technica",    "url": "https://feeds.arstechnica.com/arstechnica/index"},
        {"name": "36kr",            "url": "https://36kr.com/feed"},
        {"name": "InfoQ",           "url": "https://www.infoq.com/feed/"},
    ],
    "wellness": [
        {"name": "ScienceDaily",    "url": "https://www.sciencedaily.com/rss/mind_brain.xml"},
        {"name": "PsyPost",         "url": "https://www.psypost.org/feed"},
        {"name": "Psychology Today","url": "https://www.psychologytoday.com/us/front/feed"},
        {"name": "Aeon",            "url": "https://aeon.co/feed.rss"},
        {"name": "Greater Good",    "url": "https://greatergood.berkeley.edu/feeds/news"},
        {"name": "Harvard Health",  "url": "https://www.health.harvard.edu/blog/feed"},
        {"name": "Big Think",       "url": "https://bigthink.com/feed/"},
        {"name": "Psych Central",   "url": "https://psychcentral.com/feed/"},
    ]
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DailyBriefBot/1.0)"}

CATEGORY_CN = {
    "finance":  "金融财经",
    "social":   "科技自媒体",
    "wellness": "健康·心理·美学",
}


def clean_html(raw: str) -> str:
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(separator=" ")
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:600]


def fetch_feed(source: dict, max_items: int = 4) -> list:
    items = []
    try:
        log.info(f"  抓取: {source['name']}")
        feed = feedparser.parse(source['url'], request_headers=HEADERS)
        for entry in feed.entries[:max_items * 3]:
            title   = clean_html(getattr(entry, 'title', ''))
            summary = clean_html(getattr(entry, 'summary', '') or getattr(entry, 'description', '') or '')
            if not title:
                continue
            items.append({
                "title_en":   title,
                "summary_en": summary,
                "url":        getattr(entry, 'link', ''),
                "source":     source['name'],
            })
            if len(items) >= max_items:
                break
    except Exception as e:
        log.warning(f"  抓取失败 {source['name']}: {e}")
    return items


def translate_and_summarize(items: list, category_cn: str) -> list:
    """调用 Claude API 批量翻译标题 + 生成3-5句中文摘要"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.warning("未设置 ANTHROPIC_API_KEY，保留英文原文")
    else:
        log.info("API Key 已读取，前10位: %s" % api_key[:10])
        for item in items:
            item["title"]   = item["title_en"]
            item["summary"] = item["summary_en"][:200]
        return items

    BATCH = 5
    result_items = list(items)

    for batch_start in range(0, len(items), BATCH):
        batch = items[batch_start: batch_start + BATCH]

        news_text = ""
        for i, item in enumerate(batch, 1):
            news_text += f"\n新闻{i}:\n标题: {item['title_en']}\n内容: {item['summary_en'] or '(无)'}\n来源: {item['source']}\n---"

        prompt = f"""你是专业的中文财经/科技/健康编辑，请处理以下{len(batch)}条英文新闻（分类：{category_cn}）。

对每条新闻：
1. 写一个简洁有力的中文标题（不超过25字）
2. 写3到5句流畅的中文摘要，包含：事件核心、重要数据、影响或意义
3. 语气专业易读，像财经日报简讯
4. 专有名词（公司名、人名）可保留英文，其余全部中文

{news_text}

只输出JSON，格式如下，不要有任何其他文字：
[
  {{"title": "标题1", "summary": "第一句。第二句。第三句。第四句。"}},
  {{"title": "标题2", "summary": "..."}},
  ...
]"""

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=40
            )
            resp.raise_for_status()
            raw_text = resp.json()["content"][0]["text"].strip()

            match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            if match:
                raw_text = match.group(0)

            translations = json.loads(raw_text)
            for i, trans in enumerate(translations):
                idx = batch_start + i
                if idx < len(result_items):
                    result_items[idx]["title"]   = trans.get("title", result_items[idx]["title_en"])
                    result_items[idx]["summary"] = trans.get("summary", "")
            log.info(f"  ✅ 翻译完成 第{batch_start//BATCH + 1}批 ({len(batch)}条)")

        except Exception as e:
            log.warning(f"  翻译失败 第{batch_start//BATCH + 1}批: {e}")
            for i, item in enumerate(batch):
                idx = batch_start + i
                if idx < len(result_items):
                    result_items[idx]["title"]   = item["title_en"]
                    result_items[idx]["summary"] = item["summary_en"][:200]

        time.sleep(1)

    return result_items


def scrape_all(items_per_category: int = 10) -> dict:
    result = {}
    for category, sources in FEEDS.items():
        cat_cn = CATEGORY_CN.get(category, category)
        log.info(f"\n{'='*45}\n📡 分类: {cat_cn}\n{'='*45}")

        all_items = []
        for source in sources:
            all_items.extend(fetch_feed(source, max_items=4))
            time.sleep(0.4)

        seen, unique = set(), []
        for item in all_items:
            key = item['title_en'][:50].lower()
            if key not in seen:
                seen.add(key)
                unique.append(item)

        top_items = unique[:items_per_category]
        log.info(f"  去重后 {len(unique)} 条，取前 {len(top_items)} 条，开始翻译...")

        translated = translate_and_summarize(top_items, cat_cn)
        result[category] = translated
        log.info(f"  ✅ {cat_cn} 完成")

    return result


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    data = scrape_all()
    out_path = f"logs/news_{datetime.now().strftime('%Y%m%d')}.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"\n✅ 已保存: {out_path}")
