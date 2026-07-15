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


def _translate_titles(titles: list) -> list:
    """把英文标题批量翻译成中文；失败或缺失则回退英文原文。"""
    if not titles:
        return []
    try:
        from save_to_web import _call_claude
    except Exception as e:
        log.warning(f"⚠️ 无法导入翻译模块，用英文原文: {e}")
        return list(titles)
    body = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    prompt = (
        f"Translate each of the following {len(titles)} news headlines into concise Chinese.\n"
        f"Output EXACTLY {len(titles)} lines, one Chinese translation per line, in order.\n"
        "No numbering, no quotes, no extra text.\n\n"
        f"Headlines:\n{body}"
    )
    raw = _call_claude(prompt, max_tokens=4000)
    if not raw:
        return list(titles)
    lines = [re.sub(r"^\d+[\.\)]\s*", "", l.strip()) for l in raw.splitlines() if l.strip()]
    # 对齐长度：不足用英文补
    out = []
    for i, en in enumerate(titles):
        out.append(lines[i] if i < len(lines) and lines[i] else en)
    return out


def build_groups() -> list:
    """抓取所有分析师并翻译，返回分组结构。"""
    groups = []
    flat_titles, index = [], []   # index: (group_idx, item_idx)
    for name, firm, query in ANALYSTS:
        log.info(f"🔎 {name}（{firm}）...")
        items = fetch_analyst_items(query)
        g = {"name": name, "firm": firm, "items": items}
        for j, it in enumerate(items):
            index.append((len(groups), j))
            flat_titles.append(it["title"])
        groups.append(g)
        log.info(f"   → {len(items)} 条")

    log.info(f"🤖 翻译 {len(flat_titles)} 条标题...")
    cn = _translate_titles(flat_titles)
    for k, (gi, ji) in enumerate(index):
        groups[gi]["items"][ji]["title_cn"] = cn[k] if k < len(cn) else groups[gi]["items"][ji]["title"]
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
            print(f"\n【{g['name']} · {g['firm']}】")
            for it in g["items"]:
                print(f"  - {it.get('title_cn', it['title'])}  [{it['source']} · {it['time']}]")
    else:
        save_to_web(groups)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyst Watch — 首席策略师观点追踪")
    parser.add_argument("--dry-run", action="store_true", help="抓取+翻译并打印，不写网页")
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run))
