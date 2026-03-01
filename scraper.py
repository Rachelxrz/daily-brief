#!/usr/bin/env python3
"""
每日智识简报 - 新闻抓取引擎（中文版）
调用 Claude API 翻译标题 + 生成3-5句中文摘要
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


def clean_html(raw):
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(separator=" ")
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:600]


def fetch_feed(source, max_items=4):
    items = []
    try:
        log.info("  抓取: %s" % source['name'])
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
        log.warning("  抓取失败 %s: %s" % (source['name'], str(e)))
    return items


def call_claude(api_key, prompt):
    """直接调用 Claude API，返回文本内容"""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}]
    }

    log.info("  >>> 发送 API 请求到 Claude...")
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    log.info("  >>> HTTP 状态码: %d" % resp.status_code)

    if resp.status_code != 200:
        log.error("  >>> API 返回错误: %s" % resp.text[:300])
        return None

    data = resp.json()
    text = data["content"][0]["text"].strip()
    log.info("  >>> API 返回成功，内容前50字: %s" % text[:50])
    return text


def translate_and_summarize(items, category_cn):
    """批量翻译+生成中文摘要，每批5条"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    if not api_key:
        log.warning("  未设置 ANTHROPIC_API_KEY，保留英文原文")
        for item in items:
            item["title"]   = item["title_en"]
            item["summary"] = item["summary_en"][:200]
        return items

    log.info("  API Key 已读取，前12位: %s" % api_key[:12])

    BATCH = 5
    result_items = list(items)

    for batch_start in range(0, len(items), BATCH):
        batch = items[batch_start: batch_start + BATCH]
        log.info("  处理第 %d 批，共 %d 条..." % (batch_start // BATCH + 1, len(batch)))

        news_text = ""
        for i, item in enumerate(batch, 1):
            news_text += "\n新闻%d:\n标题: %s\n内容: %s\n来源: %s\n---" % (
                i, item['title_en'], item['summary_en'] or '(无)', item['source']
            )

        prompt = (
            "你是专业中文编辑，请处理以下%d条英文新闻（分类：%s）。\n\n"
            "对每条新闻：\n"
            "1. 写简洁有力的中文标题（不超过25字）\n"
            "2. 写3到5句流畅的中文摘要，包含事件核心、重要数据、影响意义\n"
            "3. 专有名词（公司名、人名）可保留英文，其余全部中文\n\n"
            "%s\n\n"
            "只输出JSON数组，不要其他任何文字：\n"
            '[{"title": "标题1", "summary": "第一句。第二句。第三句。"}, ...]'
        ) % (len(batch), category_cn, news_text)

        # 最多重试3次
        success = False
        for attempt in range(3):
            try:
                if attempt > 0:
                    wait_sec = attempt * 8
                    log.info("  第%d次重试，等待%d秒..." % (attempt + 1, wait_sec))
                    time.sleep(wait_sec)

                raw_text = call_claude(api_key, prompt)
                if not raw_text:
                    raise Exception("API返回空内容")

                match = re.search(r'\[.*\]', raw_text, re.DOTALL)
                if not match:
                    log.error("  返回内容中找不到JSON: %s" % raw_text[:200])
                    raise Exception("无法解析JSON")

                translations = json.loads(match.group(0))
                log.info("  解析到 %d 条翻译结果" % len(translations))

                for i, trans in enumerate(translations):
                    idx = batch_start + i
                    if idx < len(result_items):
                        result_items[idx]["title"]   = trans.get("title", result_items[idx]["title_en"])
                        result_items[idx]["summary"] = trans.get("summary", "")
                        log.info("  [%d] %s" % (idx + 1, result_items[idx]["title"]))

                success = True
                break  # 成功则退出重试循环

            except Exception as e:
                log.error("  翻译失败 第%d批 第%d次尝试: %s" % (batch_start // BATCH + 1, attempt + 1, str(e)))

        if not success:
            log.error("  第%d批全部重试失败，保留英文" % (batch_start // BATCH + 1))
            for i, item in enumerate(batch):
                idx = batch_start + i
                if idx < len(result_items):
                    result_items[idx]["title"]   = item["title_en"]
                    result_items[idx]["summary"] = item["summary_en"][:200]

        # 批次间等待，避免API限速（每批之间等5秒）
        log.info("  等待5秒后处理下一批...")
        time.sleep(5)

    return result_items


def scrape_all(items_per_category=10):
    result = {}
    for category, sources in FEEDS.items():
        cat_cn = CATEGORY_CN.get(category, category)
        log.info("\n%s\n分类: %s\n%s" % ("=" * 45, cat_cn, "=" * 45))

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
        log.info("  去重后 %d 条，取前 %d 条，开始翻译..." % (len(unique), len(top_items)))

        translated = translate_and_summarize(top_items, cat_cn)
        result[category] = translated
        log.info("  %s 完成" % cat_cn)

    return result


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    data = scrape_all()
    out_path = "logs/news_%s.json" % datetime.now().strftime('%Y%m%d')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("已保存: %s" % out_path)
