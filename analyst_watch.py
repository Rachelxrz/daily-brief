#!/usr/bin/env python3
"""
Analyst Watch — 首席策略师观点追踪 + 可验证检查点
=================================================

- 用 Google News RSS 搜索每位分析师，抓取最近被媒体引用的观点标题。
- 基于其真实标题，让 Claude 合成 3-5 句中文核心观点，并给出**可验证的测试规格**：
    测试标的（一只 ETF）、测试内容（可证伪的判定条件）、测试时间（发言日 + 3 个月，
    或标题中明确的时间窗）。
- 历史留存 90 天（三个月）到 analyst_history.jsonl；只有当某位分析师的**来源标题变化**
  时才记录新的一条"观点/预测"，避免每天重复刷屏。
- 写入 docs/data.json 的 "analysts" 键，网页左右分栏显示：左=观点，右=测试规格。

依赖：Python 标准库 + feedparser（翻译/合成复用 save_to_web._call_claude）。

用法：
  python analyst_watch.py --dry-run   # 抓取+合成并打印，不写历史/网页
  python analyst_watch.py             # 更新历史 + 写入 docs/data.json
"""

import argparse
import json
import logging
import re
import sys
import urllib.parse
from datetime import datetime, date, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("analyst_watch")

# ─── 追踪名单：(显示名, 机构, Google News 查询)──────────────
ANALYSTS = [
    ("Michael Arone",       "State Street",    '"Michael Arone" State Street'),
    ("Mike Wilson",         "Morgan Stanley",  '"Mike Wilson" Morgan Stanley'),
    ("Jan Hatzius",         "Goldman Sachs",   '"Jan Hatzius" Goldman Sachs'),
    ("Savita Subramanian",  "Bank of America", '"Savita Subramanian" Bank of America'),
    ("John Stoltzfus",      "Oppenheimer",     '"John Stoltzfus" Oppenheimer'),
    ("Scott Chronert",      "Citi",            '"Scott Chronert" Citi'),
    ("Ryan Detrick",        "Carson Group",    '"Ryan Detrick" Carson'),
    ("Chris Harvey",        "CIBC",            '"Chris Harvey" CIBC'),
    ("Marko Papic",         "BCA Research",    '"Marko Papic" BCA'),
    ("Sam Stovall",         "CFRA",            '"Sam Stovall" CFRA'),
    ("Michael Kantrowitz",  "Piper Sandler",   '"Michael Kantrowitz" Piper Sandler'),
]

ITEMS_PER_ANALYST = 3      # 每条记录引用几个来源标题
WINDOW_DAYS       = 30     # Google News 搜索时间窗
CHECK_MONTHS      = 3      # 默认检查点 = 发言日 + 3 个月
HISTORY_DAYS      = 90     # 历史留存三个月

# 限定测试标的，保证可验证（与轮动观察页的标的体系一致）
TEST_TICKERS = ["SPY", "QQQ", "IWM", "IJR", "MDY", "RSP", "SMH", "IGV",
                "XLE", "XLF", "XBI", "XMMO", "UTES", "TLT", "DIA"]

BASE_DIR  = Path(__file__).parent
HIST_FILE = BASE_DIR / "analyst_history.jsonl"
_HEADERS  = {"User-Agent": "Mozilla/5.0 (compatible; DailyBriefBot/1.0)"}


# ─── 时间 ──────────────────────────────────────────────────
def _now_et() -> datetime:
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))


def _add_months(d: date, n: int) -> date:
    """d 之后 n 个月（月末安全）。"""
    y, m = d.year, d.month + n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    dim = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, dim))


def _parse_pub(s: str):
    """RSS published → date；失败返回 None。"""
    try:
        return parsedate_to_datetime(s).date()
    except Exception:
        return None


# ─── 抓取 ──────────────────────────────────────────────────
def _clean_title(title: str, source: str) -> str:
    t = (title or "").strip()
    if source and t.endswith(f" - {source}"):
        t = t[: -(len(source) + 3)].strip()
    else:
        t = re.sub(r"\s+-\s+[^-]+$", "", t).strip() or t
    return t


def _norm(t: str) -> str:
    return re.sub(r"[^0-9a-z]", "", (t or "").lower())[:80]


def fetch_analyst_items(query: str) -> list:
    """抓取一位分析师近 WINDOW_DAYS 天被引用的文章（去重后取前 N，按时间新→旧）。"""
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
        link = getattr(e, "link", "")
        if not title or not link:
            continue
        key = _norm(title)
        if key in seen:
            continue
        seen.add(key)
        pub = _parse_pub(getattr(e, "published", "") or "")
        out.append({
            "title":  title,
            "url":    link,
            "source": source,
            "time":   (getattr(e, "published", "") or "")[:16],
            "date":   pub.isoformat() if pub else "",
        })
        if len(out) >= ITEMS_PER_ANALYST:
            break
    return out


def _signature(items: list) -> str:
    """来源标题集合的指纹：标题不变=同一次观点，不重复记录。"""
    return "|".join(sorted(_norm(it["title"]) for it in items))


def _stated_at(items: list) -> str:
    """发言日 = 这批来源里最新一篇的日期。"""
    ds = [it["date"] for it in items if it.get("date")]
    return max(ds) if ds else _now_et().date().isoformat()


# ─── 历史留存（90 天）────────────────────────────────────
def load_history() -> list:
    recs = []
    if HIST_FILE.exists():
        for line in HIST_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
    return recs


def save_history(recs: list) -> None:
    cutoff = (_now_et().date() - timedelta(days=HISTORY_DAYS)).isoformat()
    kept = [r for r in recs if r.get("date", "") >= cutoff]
    kept.sort(key=lambda r: (r.get("analyst", ""), r.get("date", "")))
    HIST_FILE.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in kept) + "\n",
        encoding="utf-8")
    log.info(f"💾 历史已写入 {HIST_FILE.name}（{len(kept)} 条，保留近 {HISTORY_DAYS} 天）")


def _latest_for(recs: list, analyst: str):
    mine = [r for r in recs if r.get("analyst") == analyst]
    return max(mine, key=lambda r: r.get("date", "")) if mine else None


# ─── Claude：合成观点 + 测试规格 ──────────────────────────
def _generate(pending: list) -> None:
    """pending: [{name, firm, items, stated_at}]，就地写入 view_cn / ticker / check。"""
    if not pending:
        return
    try:
        from save_to_web import _call_claude
    except Exception as e:
        log.warning(f"⚠️ 无法导入 Claude，跳过合成: {e}")
        return
    blocks = []
    for i, p in enumerate(pending, 1):
        heads = "\n".join(f"- {it['title']}" for it in p["items"])
        blocks.append(f"Analyst {i}: {p['name']} ({p['firm']}), spoke on {p['stated_at']}\n"
                      f"Recent headlines:\n{heads}")
    body = "\n\n".join(blocks)
    prompt = (
        f"For each of the {len(pending)} analysts below, based ONLY on their recent headlines, "
        "produce a testable read of their CURRENT market view.\n\n"
        "For each analyst output EXACTLY these 4 lines (in this order):\n"
        f"TICKER: <one ticker from this list that best tests the view: {' '.join(TEST_TICKERS)}>\n"
        "CHECK: <one short falsifiable Chinese criterion measured against that ticker's close on the "
        "analyst's speaking date, e.g. \"SPY 高于发言日收盘\" or \"IGV 跑赢 SPY\">\n"
        "HORIZON: <YYYY-MM-DD if the headlines state a specific deadline (e.g. year-end, H2), else exactly: default>\n"
        "VIEW: <3-5 full Chinese sentences: their stance, the reasoning it implies, and what it means "
        "for investors>\n\n"
        "Rules: Do NOT invent specific numbers, price targets, or quotes not present in the headlines. "
        "The CHECK must be objectively verifiable from price data alone. Be conservative if headlines are sparse.\n"
        f"Output EXACTLY {len(pending)} sections separated by a line containing only ---, in the same order. "
        "No names, no numbering, no extra text.\n\n"
        f"{body}"
    )
    raw = _call_claude(prompt, max_tokens=4000)
    if not raw:
        return
    parts = [p.strip() for p in raw.split("---") if p.strip()]
    for i, p in enumerate(pending):
        if i >= len(parts):
            break
        sec = parts[i]
        m_t = re.search(r"TICKER:\s*([A-Z]{1,5})", sec)
        m_c = re.search(r"CHECK:\s*(.+)", sec)
        m_h = re.search(r"HORIZON:\s*(\S+)", sec)
        m_v = re.search(r"VIEW:\s*(.+)", sec, re.S)
        ticker = (m_t.group(1) if m_t else "SPY").upper()
        p["ticker"] = ticker if ticker in TEST_TICKERS else "SPY"
        p["check"]  = m_c.group(1).strip() if m_c else "较发言日收盘上涨"
        p["view_cn"] = re.sub(r"\s*\n\s*", " ", m_v.group(1).strip()) if m_v else ""
        # 检查点：优先用标题里明确的时间窗，否则发言日 + 3 个月
        cd = None
        if m_h:
            h = m_h.group(1).strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", h):
                cd = h
        if not cd:
            sd = datetime.strptime(p["stated_at"], "%Y-%m-%d").date()
            cd = _add_months(sd, CHECK_MONTHS).isoformat()
        p["check_date"] = cd


# ─── 主流程 ────────────────────────────────────────────────
def build(dry_run: bool = False) -> list:
    """返回本次的全部历史记录（含新增），并按需写入历史文件。"""
    history = load_history()
    today = _now_et().date().isoformat()
    pending = []

    for name, firm, query in ANALYSTS:
        log.info(f"🔎 {name}（{firm}）...")
        items = fetch_analyst_items(query)
        if not items:
            log.info("   → 0 条，跳过")
            continue
        sig = _signature(items)
        last = _latest_for(history, name)
        if last and last.get("sig") == sig:
            log.info(f"   → {len(items)} 条（与上次相同，不新增记录）")
            continue
        log.info(f"   → {len(items)} 条（新观点，待生成）")
        pending.append({"name": name, "firm": firm, "items": items,
                        "stated_at": _stated_at(items), "sig": sig})

    if pending:
        log.info(f"🤖 合成 {len(pending)} 位分析师的观点 + 测试规格...")
        _generate(pending)
        for p in pending:
            if not p.get("view_cn"):
                log.warning(f"   ⚠️ {p['name']} 未拿到观点，跳过入库")
                continue
            history.append({
                "date": today, "analyst": p["name"], "firm": p["firm"],
                "stated_at": p["stated_at"], "view_cn": p["view_cn"],
                "ticker": p.get("ticker", "SPY"), "check": p.get("check", ""),
                "check_date": p.get("check_date", ""), "sig": p["sig"],
                "sources": p["items"],
            })
    else:
        log.info("ℹ️ 所有分析师均无新观点，历史不变")

    if not dry_run:
        save_history(history)
    return history


def to_groups(history: list) -> list:
    """按分析师分组，每位按日期新→旧列出其近三个月的观点记录。"""
    order = {name: i for i, (name, _, _) in enumerate(ANALYSTS)}
    by = {}
    for r in history:
        by.setdefault(r["analyst"], []).append(r)
    groups = []
    for name, firm, _ in ANALYSTS:
        recs = sorted(by.get(name, []), key=lambda r: r.get("date", ""), reverse=True)
        if recs:
            groups.append({"name": name, "firm": firm, "records": recs})
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
    history = build(dry_run=dry_run)
    if not history:
        log.error("❌ 无任何分析师记录，终止，不覆盖网页。")
        return 1
    groups = to_groups(history)
    total = sum(len(g["records"]) for g in groups)
    log.info(f"✅ {len(groups)} 位分析师，共 {total} 条观点记录（近 {HISTORY_DAYS} 天）")

    if dry_run:
        for g in groups:
            print(f"\n【{g['name']} · {g['firm']}】")
            for r in g["records"][:2]:
                print(f"  发言日 {r['stated_at']} | 观点: {r['view_cn'][:70]}...")
                print(f"    ⏱ 测试时间 {r['check_date']} | 🎯 标的 {r['ticker']} | ✔ 内容 {r['check']}")
    else:
        save_to_web(groups)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyst Watch — 观点追踪 + 检查点")
    parser.add_argument("--dry-run", action="store_true", help="抓取+合成并打印，不写历史/网页")
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run))
