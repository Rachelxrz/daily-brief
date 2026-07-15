#!/usr/bin/env python3
"""
Analyst Watch — 首席策略师观点追踪
=================================================

用 Google News RSS 搜索每位分析师的名字，抓取最近 ~30 天被媒体引用的观点，
翻译成中文，按分析师分组写入 docs/data.json 的 "analysts" 键，供网页
"🎯 分析师观点" 标签页显示。

依赖：Python 标准库 + feedparser + requests（翻译复用 save_to_web._call_claude）。

用法：
  python analyst_watch.py --dry-run   # 抓取+翻译并打印，不写网页
  python analyst_watch.py             # 写入 docs/data.json
"""

import argparse
import logging
import re
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta

import feedparser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("analyst_watch")

# ─── 追踪名单：(显示名, 机构, Google News 查询)──────────────
# 查询用 "全名" + 机构关键词消歧；名单可自由增删。
ANALYSTS = [
    ("Michael Arone",       "State Street",   '"Michael Arone" State Street'),
    ("Mike Wilson",         "Morgan Stanley", '"Mike Wilson" Morgan Stanley'),
    ("Jan Hatzius",         "Goldman Sachs",  '"Jan Hatzius" Goldman Sachs'),
    ("Savita Subramanian",  "Bank of America",'"Savita Subramanian" Bank of America'),
    ("John Stoltzfus",      "Oppenheimer",    '"John Stoltzfus" Oppenheimer'),
    ("Scott Chronert",      "Citi",           '"Scott Chronert" Citi'),
    ("Ryan Detrick",        "Carson Group",   '"Ryan Detrick" Carson'),
    ("Chris Harvey",        "CIBC",           '"Chris Harvey" CIBC'),
    ("Marko Papic",         "BCA Research",   '"Marko Papic" BCA'),
    ("Sam Stovall",         "CFRA",           '"Sam Stovall" CFRA'),
    ("Michael Kantrowitz",  "Piper Sandler",  '"Michael Kantrowitz" Piper Sandler'),
]

ITEMS_PER_ANALYST = 3          # 每位最多显示几条
WINDOW_DAYS       = 30         # 搜索时间窗
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DailyBriefBot/1.0)"}


def _now_et() -> datetime:
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))


def _clean_title(title: str, source: str) -> str:
    """去掉 Google News 标题结尾的 ' - 来源' 后缀。"""
    t = (title or "").strip()
    if source and t.endswith(f" - {source}"):
        t = t[: -(len(source) + 3)].strip()
    else:
        t = re.sub(r"\s+-\s+[^-]+$", "", t).strip() or t
    return t


def _norm(t: str) -> str:
    return re.sub(r"[^0-9a-z]", "", (t or "").lower())[:80]


def fetch_analyst_items(query: str) -> list:
    """抓取一位分析师最近 WINDOW_DAYS 天被引用的文章（去重后取前 N）。"""
    q = urllib.parse.quote(f"{query} when:{WINDOW_DAYS}d")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(url, request_headers=_HEADERS)
    except Exception as e:
        log.warning(f"   ⚠️ 抓取失败 [{query}]: {e}")
        return []
    out, seen = [], set()
    for e in feed.entries:
        source = ""
        if getattr(e, "source", None):
            source = getattr(e.source, "title", "") or ""
        title = _clean_title(getattr(e, "title", ""), source)
        url_ = getattr(e, "link", "")
        if not title or not url_:
            continue
        key = _norm(title)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "title":  title,
            "url":    url_,
            "source": source,
            "time":   (getattr(e, "published", "") or "")[:16],
        })
        if len(out) >= ITEMS_PER_ANALYST:
            break
    return out


def _synthesize_views(groups: list) -> None:
    """为每位有观点的分析师，基于其近期真实标题合成 3-5 句中文核心观点，写入 g['view_cn']。
    多条真实标题作约束，避免凭空杜撰；下方仍保留来源标题链接供核对。"""
    active = [g for g in groups if g["items"]]
    if not active:
        return
    try:
        from save_to_web import _call_claude
    except Exception as e:
        log.warning(f"⚠️ 无法导入 Claude，跳过观点合成: {e}")
        return
    blocks = []
    for i, g in enumerate(active, 1):
        heads = "\n".join(f"- {it['title']}" for it in g["items"])
        blocks.append(f"Analyst {i}: {g['name']} ({g['firm']})\nRecent headlines:\n{heads}")
    body = "\n\n".join(blocks)
    prompt = (
        f"For each of the {len(active)} analysts below, based ONLY on their recent news headlines, "
        "write a 3-5 sentence Chinese summary of their CURRENT core market view: their stance, the "
        "reasoning it implies, and what it means for investors.\n"
        "Rules: Do NOT invent specific numbers, price targets, dates, or quotes not present in the "
        "headlines. If the headlines are sparse or conflicting, summarize conservatively. Natural "
        "Chinese, 3-5 full sentences per analyst (not one line).\n"
        f"Output EXACTLY {len(active)} sections separated by a line containing only ---, in the same "
        "order, each section containing ONLY the Chinese summary (no name, no numbering, no heading).\n\n"
        f"{body}"
    )
    raw = _call_claude(prompt, max_tokens=4000)
    if not raw:
        return
    parts = [p.strip() for p in raw.split("---") if p.strip()]
    for i, g in enumerate(active):
        if i < len(parts):
            txt = re.sub(r"^Analyst\s*\d+[^\n]*\n?", "", parts[i]).strip()
            g["view_cn"] = txt or parts[i]


def build_groups() -> list:
    """抓取所有分析师，合成各自 3-5 句核心观点，返回分组结构。"""
    groups = []
    for name, firm, query in ANALYSTS:
        log.info(f"🔎 {name}（{firm}）...")
        items = fetch_analyst_items(query)
        groups.append({"name": name, "firm": firm, "items": items, "view_cn": ""})
        log.info(f"   → {len(items)} 条")

    log.info("🤖 合成各分析师 3-5 句核心观点...")
    _synthesize_views(groups)
    return groups


def save_to_web(groups: list) -> None:
    try:
        from save_to_web import load_data, save_data, _today_et
    except Exception as e:
        log.warning(f"⚠️ 无法导入 save_to_web，跳过写入: {e}")
        return
    today = _today_et()
    data = load_data()
    data.setdefault(today, {})
    data[today]["updated"] = _now_et().strftime("%Y-%m-%d %H:%M ET")
    data[today]["analysts"] = {
        "updated": _now_et().strftime("%Y-%m-%d %H:%M ET"),
        "groups":  groups,
    }
    save_data(data)
    log.info(f"🌐 分析师观点已写入网页: {today}")


def run(dry_run: bool = False) -> int:
    groups = build_groups()
    total = sum(len(g["items"]) for g in groups)
    if total == 0:
        log.error("❌ 未抓到任何分析师观点（网络问题？），终止，不覆盖网页。")
        return 1
    log.info(f"✅ 共 {total} 条观点，{sum(1 for g in groups if g['items'])}/{len(groups)} 位分析师有更新")
    if dry_run:
        for g in groups:
            if not g["items"]:
                continue
            print(f"\n【{g['name']} · {g['firm']}】")
            print(f"  观点: {g.get('view_cn', '（无）')}")
            for it in g["items"]:
                print(f"    来源: {it['title'][:70]}  [{it['source']} · {it['time']}]")
    else:
        save_to_web(groups)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyst Watch — 首席策略师观点追踪")
    parser.add_argument("--dry-run", action="store_true", help="抓取+翻译并打印，不写网页")
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run))
