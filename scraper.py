#!/usr/bin/env python3
"""
每日智识简报 - 新闻抓取引擎
Daily Intelligence Brief - News Scraper Engine

抓取来源:
  金融财经: Bloomberg, Reuters, FT, CNBC, WSJ, Yahoo Finance
  自媒体精选: Hacker News, Product Hunt, TechCrunch, The Verge, 36kr
  健康心理美学: ScienceDaily, PsyPost, Psychology Today, Nature, Aeon
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import json
import re
import time
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/scraper.log', encoding='utf-8')
    ]
)
log = logging.getLogger(__name__)

# ─── RSS Feed 配置 ─────────────────────────────────────────
FEEDS = {
    "finance": [
        # ── 通讯社 / 综合财经 ──────────────────────────────
        {"name": "Reuters Business",    "url": "https://feeds.reuters.com/reuters/businessNews"},
        {"name": "Reuters Markets",     "url": "https://feeds.reuters.com/reuters/financialNews"},
        {"name": "CNBC Finance",        "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html"},
        {"name": "CNBC World Economy",  "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html"},
        {"name": "Yahoo Finance",       "url": "https://finance.yahoo.com/news/rssindex"},
        # ── 高端财经媒体 ──────────────────────────────────
        {"name": "FT Markets",          "url": "https://www.ft.com/rss/home/uk"},
        {"name": "Bloomberg Markets",   "url": "https://feeds.bloomberg.com/markets/news.rss"},
        {"name": "WSJ MarketWatch",     "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"},
        {"name": "WSJ Top Stories",     "url": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml"},
        {"name": "Barron's",            "url": "https://www.barrons.com/xml/rss/3_7510.xml"},
        {"name": "The Economist",       "url": "https://www.economist.com/finance-and-economics/rss.xml"},
        # ── 投资分析 ──────────────────────────────────────
        {"name": "Investing.com",       "url": "https://www.investing.com/rss/news_25.rss"},
        {"name": "Seeking Alpha",       "url": "https://seekingalpha.com/market_currents.xml"},
        {"name": "Motley Fool",         "url": "https://www.fool.com/feeds/index.aspx?id=fool-headlines"},
    ],
    "social": [
        {"name": "Hacker News",         "url": "https://hnrss.org/frontpage"},
        {"name": "TechCrunch",          "url": "https://techcrunch.com/feed/"},
        {"name": "The Verge",           "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "Wired",               "url": "https://www.wired.com/feed/rss"},
        {"name": "MIT Tech Review",     "url": "https://www.technologyreview.com/feed/"},
        {"name": "Ars Technica",        "url": "https://feeds.arstechnica.com/arstechnica/index"},
        {"name": "36kr",                "url": "https://36kr.com/feed"},
        {"name": "InfoQ",               "url": "https://www.infoq.com/feed/"},
    ],
    "wellness": [
        {"name": "ScienceDaily Mind",   "url": "https://www.sciencedaily.com/rss/mind_brain.xml"},
        {"name": "PsyPost",             "url": "https://www.psypost.org/feed"},
        {"name": "Psychology Today",    "url": "https://www.psychologytoday.com/us/front/feed"},
        {"name": "Aeon Magazine",       "url": "https://aeon.co/feed.rss"},
        {"name": "Greater Good",        "url": "https://greatergood.berkeley.edu/feeds/news"},
        {"name": "Harvard Health",      "url": "https://www.health.harvard.edu/blog/feed"},
        {"name": "Psych Central",       "url": "https://psychcentral.com/feed/"},
        {"name": "Big Think",           "url": "https://bigthink.com/feed/"},
    ]
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DailyBriefBot/1.0; +https://github.com/yourusername/daily-brief)"
}

def clean_html(raw: str) -> str:
    """Strip HTML tags and clean whitespace."""
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(separator=" ")
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:280] + "…" if len(text) > 280 else text

def is_today(entry) -> bool:
    """Check if feed entry was published today (Asia/Shanghai timezone)."""
    tz_cst = timezone(timedelta(hours=8))
    today = datetime.now(tz_cst).date()
    
    for attr in ('published_parsed', 'updated_parsed'):
        t = getattr(entry, attr, None)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc).astimezone(tz_cst)
                return dt.date() == today
            except Exception:
                pass
    return True  # fallback: include if no date

def fetch_feed(source: dict, max_items: int = 5) -> list:
    """Fetch and parse a single RSS feed."""
    items = []
    try:
        log.info(f"Fetching: {source['name']}")
        feed = feedparser.parse(source['url'], request_headers=HEADERS)
        
        for entry in feed.entries[:max_items * 3]:  # fetch extra, filter below
            summary = clean_html(
                getattr(entry, 'summary', '') or
                getattr(entry, 'description', '') or ''
            )
            title = clean_html(getattr(entry, 'title', ''))
            if not title:
                continue

            items.append({
                "title":   title,
                "summary": summary,
                "url":     getattr(entry, 'link', ''),
                "source":  source['name'],
                "time":    getattr(entry, 'published', ''),
            })
            if len(items) >= max_items:
                break
                
    except Exception as e:
        log.warning(f"Failed to fetch {source['name']}: {e}")
    
    return items

def scrape_all(items_per_category: int = 10) -> dict:
    """Scrape all categories and return top N per category."""
    result = {}
    
    for category, sources in FEEDS.items():
        log.info(f"\n{'='*40}")
        log.info(f"Category: {category.upper()}")
        log.info(f"{'='*40}")
        
        all_items = []
        for source in sources:
            items = fetch_feed(source, max_items=4)
            all_items.extend(items)
            time.sleep(0.5)  # polite crawling
        
        # deduplicate by title similarity
        seen_titles = set()
        unique_items = []
        for item in all_items:
            key = item['title'][:50].lower()
            if key not in seen_titles:
                seen_titles.add(key)
                unique_items.append(item)
        
        result[category] = unique_items[:items_per_category]
        log.info(f"  ✓ {len(result[category])} items collected for [{category}]")
    
    return result

if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    data = scrape_all()
    
    out_path = f"logs/news_{datetime.now().strftime('%Y%m%d')}.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    log.info(f"\n✅ Scraped data saved to {out_path}")
    print(json.dumps(data, ensure_ascii=False, indent=2))
