#!/usr/bin/env python3
"""
🏛 国会交易信号模块 - congress_tracker.py v1.0
Congressional Trading Signal Tracker

数据源:
  - 众议院: House Stock Watcher 社区镜像
    https://github.com/TattooedHead/house-stock-watcher-data
  - 参议院: 原 Senate Stock Watcher 数据源已失效，暂无可用免费替代
    （见 modules/congress/status.md「已知问题」）

用法:
  python congress_tracker.py              # 抓取 + 评分 + 推送 + 保存
  python congress_tracker.py --dry-run    # 仅抓取分析，打印结果，不推送不保存
"""

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from config import Config
from market_monitor import push_serverchan, push_wecom, push_wxpusher
from save_to_web import save_congress
from watchlist_manager import add_congress_ticker, remove_expired_tickers
from stock_screener import get_hist

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
# 数据源 & 常量
# ═══════════════════════════════════════════════
HOUSE_URL = "https://raw.githubusercontent.com/TattooedHead/house-stock-watcher-data/main/data/all_transactions.json"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL   = "claude-sonnet-4-20250514"

RECENT_DAYS          = 14      # 信号窗口：披露日期在最近N天内（国会批量披露，14天确保不漏）
MIN_TRADE_SIZE       = 10_000  # 层二过滤：交易规模下限（美元）
SEEN_FILE            = Path(__file__).parent / "docs" / "data" / "congress_seen.json"
SEEN_RETENTION_DAYS  = 14

# ═══════════════════════════════════════════════
# 高信号议员加分名单（不作为硬过滤条件，仅用于 score_trade 加分）
# 数据来源：对 house-stock-watcher 数据实际分析后更新
# ═══════════════════════════════════════════════
BONUS_MEMBERS = {
    # 长期高关注度
    "Nancy Pelosi":           {"party": "D", "committee": "N/A"},
    "Dwight Evans":           {"party": "D", "committee": "Ways and Means"},
    "Warren Davidson":        {"party": "R", "committee": "Financial Services"},
    # 当前活跃交易者（2025-2026 数据分析）
    "Josh Gottheimer":        {"party": "D", "committee": "Financial Services"},
    "Gilbert Cisneros":       {"party": "D", "committee": "Armed Services"},
    "April McClain Delaney":  {"party": "D", "committee": "N/A"},
    "Maria Elvira Salazar":   {"party": "R", "committee": "Foreign Affairs"},
    "Daniel Goldman":         {"party": "D", "committee": "Judiciary"},
    "Lisa McClain":           {"party": "R", "committee": "Armed Services"},
    "Virginia Foxx":          {"party": "R", "committee": "Education"},
    "Kevin Hern":             {"party": "R", "committee": "Budget"},
    "Mike Kelly":             {"party": "R", "committee": "Ways and Means"},
}

# 已知"声明由基金经理全权委托"的议员（信号失真，直接过滤）。当前暂无，按需补充。
DELEGATED_MANAGER_MEMBERS = set()

# ═══════════════════════════════════════════════
# 层四：持仓与 Watchlist
# ═══════════════════════════════════════════════
MY_HOLDINGS = {
    "GLD": {"weight": 0.30, "direction": "long"},
    "WTI": {"weight": 0.20, "direction": "long"},
    "QQQ": {"weight": 0.25, "direction": "long"},
    "TLT": {"weight": 0.20, "direction": "long"},
}

MY_WATCHLIST = [
    "ALB","ANET","AVGO","BDRY","CEG","CIEN","COHR","COPX",
    "ETHA","FRO","GEV","GS","HEWJ","LITE","MP","NEE",
    "NVDA","PLTR","PWR","VRT","VST","MPWR","ADI","GOOG","NBIS","MPC"
]

# 行业(yfinance sector) → 持仓提示（层四 C：行业关联）
SECTOR_HOLDING_HINTS = {
    "Energy":             ("WTI", "能源"),
    "Basic Materials":    ("GLD", "材料/贵金属"),
    "Technology":         ("QQQ", "科技"),
    "Financial Services": ("TLT", "利率敏感/金融"),
}

# 委员会 → 相关行业(yfinance sector)（层三：委员会与行业匹配 +1分）
COMMITTEE_SECTOR_MAP = {
    "Financial Services": ["Financial Services"],
    "Armed Services":     ["Industrials"],
    "Ways and Means":     ["Financial Services", "Healthcare"],
    "Judiciary":          ["Technology", "Communication Services"],
    "Commerce":           ["Technology", "Communication Services", "Industrials"],
}

# ═══════════════════════════════════════════════
# 中文翻译表
# ═══════════════════════════════════════════════
COMMITTEE_CN = {
    "Financial Services": "金融服务委",
    "Armed Services":     "军事委",
    "Ways and Means":     "筹款委",
    "Judiciary":          "司法委",
    "Commerce":           "商务委",
    "Ethics":             "道德委",
    "Budget":             "预算委",
    "N/A":                "",
}

TRANSACTION_CN = {"Buy": "买入", "Sell": "卖出"}

ASSET_TYPE_CN = {
    "Stock":       "股票",
    "Call Option": "期权(Call)",
    "Put Option":  "期权(Put)",
    "Option":      "期权",
}

SECTOR_CN = {
    "Energy":                 "能源",
    "Industrials":            "工业",
    "Technology":             "科技",
    "Financial Services":     "金融",
    "Healthcare":             "医疗",
    "Consumer Cyclical":      "消费(可选)",
    "Consumer Defensive":     "消费(必需)",
    "Basic Materials":        "材料",
    "Utilities":              "公用事业",
    "Real Estate":            "房地产",
    "Communication Services": "通讯",
}

INDUSTRY_CN = {
    "Semiconductors":                      "半导体",
    "Semiconductor Equipment & Materials": "半导体设备",
    "Oil & Gas E&P":                       "油气开采",
    "Oil & Gas Equipment & Services":      "油气设备服务",
    "Oil & Gas Midstream":                 "油气中游",
    "Oil & Gas Integrated":                "综合油气",
    "Electrical Equipment & Parts":        "电力设备",
    "Utilities—Renewable":                 "新能源发电",
    "Utilities—Regulated Electric":        "电力公用事业",
    "Aerospace & Defense":                 "航空国防",
    "Software—Application":                "应用软件",
    "Software—Infrastructure":             "基础软件",
    "Internet Content & Information":      "互联网内容",
    "Gold":                                 "黄金",
    "Copper":                               "铜业",
    "Specialty Industrial Machinery":      "工业机械",
    "Communication Equipment":             "通讯设备",
    "Banks—Diversified":                   "银行",
    "Asset Management":                    "资产管理",
}


# ═══════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════

def get_bonus_member(name: str) -> dict | None:
    """返回 BONUS_MEMBERS 条目（若存在），否则返回 None。"""
    return BONUS_MEMBERS.get(name.strip())


def normalize_transaction(raw_type: str) -> str:
    raw = (raw_type or "").strip().lower()
    if raw.startswith("purchase"):
        return "Buy"
    if raw.startswith("sale"):
        return "Sell"
    return "Other"


def normalize_asset_type(asset_type: str, asset_description: str) -> str:
    text = f"{asset_type or ''} {asset_description or ''}".lower()
    if "put" in text and "option" in text:
        return "Put Option"
    if "call" in text and "option" in text:
        return "Call Option"
    if "option" in text:
        return "Option"
    return "Stock"


def parse_us_date(date_str: str) -> datetime:
    """解析 MM/DD/YYYY 格式日期。"""
    return datetime.strptime(date_str, "%m/%d/%Y")


def format_size_range(amount: str) -> str:
    """'$15,001 - $50,000' -> '$15K-50K'"""
    def _to_k(num_str):
        n = int(num_str.replace("$", "").replace(",", "").strip())
        return f"{n // 1000}K" if n >= 1000 else str(n)

    for sep in ("-", "–", "—"):
        if sep in (amount or ""):
            parts = [p.strip() for p in amount.split(sep)]
            if len(parts) == 2:
                try:
                    return f"${_to_k(parts[0])}-{_to_k(parts[1])}"
                except ValueError:
                    return amount
    return amount or "未知"


# ═══════════════════════════════════════════════
# 数据抓取
# ═══════════════════════════════════════════════

def fetch_house_trades() -> list:
    """从 House Stock Watcher 社区镜像抓取众议院交易数据。"""
    try:
        resp = requests.get(HOUSE_URL, timeout=60,
                             headers={"User-Agent": "daily-brief-congress-tracker"})
        resp.raise_for_status()
        data = resp.json()
        log.info(f"   ✅ House 数据获取成功，共 {len(data)} 条记录")
        return data
    except Exception as e:
        log.error(f"   ❌ House 数据获取失败: {e}")
        return []


def fetch_senate_trades() -> list:
    """参议院数据源（Senate Stock Watcher）已失效，暂返回空列表。
    见 modules/congress/status.md「已知问题」。"""
    log.warning("   ⚠️ 参议院数据源暂不可用，本次跳过（详见 status.md）")
    return []


# ═══════════════════════════════════════════════
# 行业 & 技术面 富化
# ═══════════════════════════════════════════════

_SECTOR_CACHE = {}


def get_sector(ticker: str) -> dict:
    """返回 {'sector':..., 'industry':..., 'label_cn':...}，带缓存。"""
    if ticker in _SECTOR_CACHE:
        return _SECTOR_CACHE[ticker]

    result = {"sector": None, "industry": None, "label_cn": "未知"}
    try:
        import yfinance as yf
        info     = yf.Ticker(ticker).info
        sector   = info.get("sector")
        industry = info.get("industry")
        result["sector"]   = sector
        result["industry"] = industry
        if industry and industry in INDUSTRY_CN:
            result["label_cn"] = INDUSTRY_CN[industry]
        elif sector and sector in SECTOR_CN:
            result["label_cn"] = SECTOR_CN[sector]
        elif industry:
            result["label_cn"] = industry
        elif sector:
            result["label_cn"] = sector
    except Exception as e:
        log.warning(f"   ⚠️ {ticker} 行业信息获取失败: {e}")

    _SECTOR_CACHE[ticker] = result
    return result


def get_ma_signal(ticker: str):
    """复用 stock_screener.get_hist 计算 MA20/MA50 状态。"""
    try:
        _, hist = get_hist(ticker, period="3mo")
        if hist is None or len(hist) < 20:
            return None
        closes = hist["Close"].dropna().tolist()
        n = len(closes)
        price = round(closes[-1], 2)
        ma20  = round(sum(closes[-20:]) / 20, 2)
        ma50  = round(sum(closes[-50:]) / 50, 2) if n >= 50 else None
        return {
            "price": price,
            "ma20": ma20,
            "ma50": ma50,
            "above_ma20": price > ma20,
            "above_ma50": (price > ma50) if ma50 is not None else None,
        }
    except Exception as e:
        log.warning(f"   ⚠️ {ticker} MA信号获取失败: {e}")
        return None


# ═══════════════════════════════════════════════
# 层一 + 层二：抓取、匹配、解析、过滤
# ═══════════════════════════════════════════════

def fetch_recent_trades(now: datetime) -> list:
    raw = fetch_house_trades() + fetch_senate_trades()
    cutoff = now.replace(tzinfo=None) - timedelta(days=RECENT_DAYS)

    trades = []
    for r in raw:
        member_name = (r.get("representative") or "").strip()
        if not member_name or member_name in DELEGATED_MANAGER_MEMBERS:
            continue

        ticker = (r.get("ticker") or "").strip().upper()
        if not ticker or ticker in ("--", "N/A"):
            continue

        transaction = normalize_transaction(r.get("type", ""))
        if transaction == "Other":
            continue

        try:
            trade_date      = parse_us_date(r["transaction_date"])
            disclosure_date = parse_us_date(r["disclosure_date"])
        except (KeyError, ValueError, TypeError):
            continue

        if disclosure_date < cutoff:
            continue

        amount_mid = r.get("amount_mid")
        if not isinstance(amount_mid, (int, float)) or amount_mid < MIN_TRADE_SIZE:
            continue

        bonus = get_bonus_member(member_name)
        trades.append({
            "member":          member_name,
            "party":           bonus["party"] if bonus else "",
            "chamber":         "House",
            "committee":       bonus["committee"] if bonus else "N/A",
            "ticker":          ticker,
            "asset_type":      normalize_asset_type(r.get("asset_type", ""), r.get("asset_description", "")),
            "transaction":     transaction,
            "trade_date":      trade_date.strftime("%Y-%m-%d"),
            "disclosure_date": disclosure_date.strftime("%Y-%m-%d"),
            "delay_days":      (disclosure_date - trade_date).days,
            "amount_mid":      amount_mid,
            "size_range":      format_size_range(r.get("amount", "")),
            "filing_id":       r.get("filing_id", ""),
        })

    log.info(f"   📋 筛选后符合条件交易: {len(trades)} 条（窗口 {RECENT_DAYS} 天）")
    return trades


def enrich_trades(trades: list) -> list:
    for t in trades:
        t["sector_info"] = get_sector(t["ticker"])
    return trades


def find_multi_member_buys(trades: list) -> set:
    """找出同一标的、同向买入且涉及 ≥2 名议员的组合（层三加分项）。"""
    groups = defaultdict(set)
    for t in trades:
        if t["transaction"] == "Buy":
            groups[t["ticker"]].add(t["member"])
    return {ticker for ticker, members in groups.items() if len(members) > 1}


# ═══════════════════════════════════════════════
# 层三：信号强度评级
# ═══════════════════════════════════════════════

def score_trade(trade: dict, multi_member_buy_tickers: set) -> int:
    asset_type  = trade["asset_type"]
    transaction = trade["transaction"]

    if "Option" in asset_type and transaction == "Buy":
        score = 3
    elif transaction == "Buy" and asset_type == "Stock":
        score = 2
    elif transaction == "Sell" and asset_type == "Stock":
        score = 1
    else:
        score = 0

    # 高信号议员加分
    if trade["member"] in BONUS_MEMBERS:
        score += 2

    # Watchlist 标的加分（仅买入）
    if transaction == "Buy" and trade["ticker"] in MY_WATCHLIST:
        score += 2

    # 委员会与行业匹配（bonus 议员才有有效 committee）
    sector = trade["sector_info"].get("sector")
    if sector and sector in COMMITTEE_SECTOR_MAP.get(trade["committee"], []):
        score += 1

    if transaction == "Buy" and trade["ticker"] in multi_member_buy_tickers:
        score += 1

    if trade["amount_mid"] > 50_000:
        score += 1

    if trade["delay_days"] > 60:
        score -= 2
    elif trade["delay_days"] > 45:
        score -= 1

    return max(score, 0)


def score_to_tier(score: int, delay_days: int) -> str:
    if delay_days > 60:
        return "weak"  # 层二：delay_days > 60 强制降级为弱信号
    if score >= 5:
        return "strong"
    if score >= 3:
        return "medium"
    if score >= 1:
        return "weak"
    return "excluded"


# ═══════════════════════════════════════════════
# 层四：与持仓 / Watchlist 对比
# ═══════════════════════════════════════════════

def compare_with_holdings(trade: dict) -> dict:
    ticker = trade["ticker"]

    # A. 直接持仓重叠
    if ticker in MY_HOLDINGS:
        direction  = MY_HOLDINGS[ticker]["direction"]
        is_aligned = (
            (direction == "long" and trade["transaction"] == "Buy") or
            (direction == "short" and trade["transaction"] == "Sell")
        )
        if is_aligned:
            return {"type": "holding", "alignment": "confirm",
                    "detail": f"✅ 与您持仓 {ticker} 方向一致（确认信号）", "ma": None}
        return {"type": "holding", "alignment": "warn",
                "detail": f"⚠️ 与您持仓 {ticker} 方向相反，建议关注是否减仓", "ma": None}

    # B. Watchlist 重叠
    if ticker in MY_WATCHLIST:
        ma = get_ma_signal(ticker)
        if ma and ma["above_ma50"] is not None:
            ma_str = "MA50向上 ✅" if ma["above_ma50"] else "MA50向下 ⚠️"
            detail = f"⚡ 与您 Watchlist 重叠 | {ma_str}"
        else:
            detail = "📌 Watchlist 标的 | 建议关注突破信号"
        return {"type": "watchlist", "alignment": None, "detail": detail, "ma": ma}

    # C. 行业关联
    sector = trade["sector_info"].get("sector")
    if sector in SECTOR_HOLDING_HINTS:
        hold_ticker, sector_cn = SECTOR_HOLDING_HINTS[sector]
        return {"type": "sector", "alignment": None,
                "detail": f"🔗 行业相关：与您 {hold_ticker} 持仓相关（{sector_cn}板块）", "ma": None}

    # D. 全新标的
    return {"type": "new", "alignment": None,
            "detail": "🆕 候选观察 · 建议结合技术指标二次确认", "ma": None}


# ═══════════════════════════════════════════════
# 层五：行业分布 & 推送格式
# ═══════════════════════════════════════════════

def build_sector_breakdown(trades: list) -> dict:
    """统计窗口内 Buy 交易的行业分布（百分比）。"""
    buys = [t for t in trades if t["transaction"] == "Buy"]
    if not buys:
        return {}
    counts = {}
    for t in buys:
        label = t["sector_info"].get("label_cn") or "其他"
        counts[label] = counts.get(label, 0) + 1
    total = sum(counts.values())
    return dict(sorted(
        ((label, round(c / total * 100, 1)) for label, c in counts.items()),
        key=lambda kv: kv[1], reverse=True
    ))


def render_sector_bars(breakdown: dict, top_n: int = 3) -> list:
    lines = []
    for label, pct in list(breakdown.items())[:top_n]:
        bar = "█" * max(1, round(pct / 5))
        lines.append(f"  {label} {bar} {pct:.0f}%")
    return lines


def format_trade_block(trade: dict, score: int, comparison: dict, show_score: bool) -> list:
    committee_cn = COMMITTEE_CN.get(trade["committee"], trade["committee"])
    header = (f"{trade['member']} ({trade['party']}-{committee_cn})" if committee_cn
              else f"{trade['member']} ({trade['party']})")

    trans_cn = TRANSACTION_CN.get(trade["transaction"], trade["transaction"])
    asset_cn = ASSET_TYPE_CN.get(trade["asset_type"], trade["asset_type"])
    action   = f"{trans_cn} {trade['ticker']} {asset_cn} · {trade['size_range']} · 交易延迟{trade['delay_days']}天"
    sector_line = f"行业：{trade['sector_info'].get('label_cn') or '未知'}"

    lines = [header, action, sector_line, comparison["detail"]]
    if show_score:
        lines.append(f"信号强度：{score} 分")
    return lines


def build_push_message(today_str: str, strong: list, medium: list, weak: list,
                        sector_breakdown: dict, anti_signals: list,
                        ai_insight: str = "") -> str:
    lines = [f"🏛 国会交易信号 {today_str}", ""]

    if strong:
        lines.append("🔴 强信号")
        for item in strong:
            for l in format_trade_block(item["trade"], item["score"], item["comparison"], show_score=True):
                lines.append(f"  {l}")
            lines.append("")

    if medium:
        lines.append("🟡 中等信号")
        for item in medium:
            for l in format_trade_block(item["trade"], item["score"], item["comparison"], show_score=False):
                lines.append(f"  {l}")
            lines.append("")

    if weak:
        lines.append("🟢 弱信号/观察")
        for item in weak[:5]:
            t = item["trade"]
            trans_cn = TRANSACTION_CN.get(t["transaction"], t["transaction"])
            lines.append(f"  {t['member']} · {trans_cn} {t['ticker']} · {t['sector_info'].get('label_cn') or '未知'}")
        if len(weak) > 5:
            lines.append(f"  ...等共 {len(weak)} 条")
        lines.append("")

    if sector_breakdown:
        lines.append("📊 本周国会买入最多行业")
        lines.extend(render_sector_bars(sector_breakdown))
        lines.append("")

    lines.append("⚠️ 与您持仓方向相反的交易")
    if anti_signals:
        for item in anti_signals:
            t = item["trade"]
            trans_cn = TRANSACTION_CN.get(t["transaction"], t["transaction"])
            lines.append(f"  {t['member']} {trans_cn} {t['ticker']}：{item['comparison']['detail']}")
    else:
        lines.append("  无")

    lines.append("")
    if ai_insight:
        lines.append("🤖 AI 解读")
        lines.append(f"  {ai_insight}")
        lines.append("")
    lines.append("⚠️ 仅供参考，不构成投资建议 | 数据：House Stock Watcher 社区镜像（参议院数据暂缺）")

    return "\n".join(lines)


def generate_ai_insight(strong: list, medium: list, sector_breakdown: dict) -> str:
    """调用 Claude API 生成 2-3 句中文投资洞察。无信号或 API 未配置时返回空字符串。"""
    if not strong and not medium:
        return ""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    def _fmt(items):
        parts = []
        for s in items[:3]:
            t = s["trade"]
            trans = "买入" if t["transaction"] == "Buy" else "卖出"
            parts.append(f"{t['member']}({t['party']}) {trans} {t['ticker']} [{t['sector_info'].get('label_cn','未知')}] 评分{s['score']}分")
        return "；".join(parts) if parts else "无"

    sector_str = "、".join(f"{k}{v:.0f}%" for k, v in list(sector_breakdown.items())[:4]) or "无"

    prompt = (
        "你是一位专业投资顾问。根据以下美国国会议员本周的交易信号，"
        "用2-3句简洁的中文生成一段投资洞察，重点说明对以下持仓和关注股的启示。"
        "直接输出洞察文字，不要任何标题或格式前缀，不超过150字。\n\n"
        f"持仓：GLD(黄金30%) · QQQ(科技25%) · WTI(原油20%) · TLT(国债20%)\n"
        f"强信号：{_fmt(strong)}\n"
        f"中等信号：{_fmt(medium)}\n"
        f"本周买入行业分布：{sector_str}"
    )

    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            json={"model": ANTHROPIC_MODEL, "max_tokens": 300,
                  "messages": [{"role": "user", "content": prompt}]},
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            timeout=45,
        )
        resp.raise_for_status()
        blocks = resp.json().get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        if text:
            log.info("   🤖 AI 解读生成成功")
            return text
    except Exception as e:
        log.warning(f"   ⚠️ AI 解读生成失败（跳过）: {e}")
    return ""


def _serialize(item: dict) -> dict:
    t = item["trade"]
    return {
        "member":          t["member"],
        "party":           t["party"],
        "chamber":         t["chamber"],
        "committee":       t["committee"],
        "ticker":          t["ticker"],
        "asset_type":      t["asset_type"],
        "transaction":     t["transaction"],
        "trade_date":      t["trade_date"],
        "disclosure_date": t["disclosure_date"],
        "delay_days":      t["delay_days"],
        "amount_mid":      t["amount_mid"],
        "size_range":      t["size_range"],
        "sector":          t["sector_info"].get("label_cn"),
        "score":           item["score"],
        "comparison":      item["comparison"]["detail"],
    }


# ═══════════════════════════════════════════════
# 去重（避免同一披露重复推送）
# ═══════════════════════════════════════════════

def load_seen() -> dict:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_seen(seen: dict, now: datetime):
    cutoff = (now.replace(tzinfo=None) - timedelta(days=SEEN_RETENTION_DAYS)).strftime("%Y-%m-%d")
    pruned = {k: v for k, v in seen.items() if v >= cutoff}
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(pruned, ensure_ascii=False, indent=2), encoding="utf-8")


def trade_key(trade: dict) -> str:
    return f"{trade['filing_id']}_{trade['ticker']}_{trade['transaction']}_{trade['trade_date']}"


# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════

def run_congress_tracker(dry_run: bool = False) -> dict:
    tz_cst = timezone(timedelta(hours=8))
    now    = datetime.now(tz_cst)
    today_str = now.strftime("%Y-%m-%d")

    log.info("=" * 60)
    log.info("🏛 国会交易信号任务启动")
    log.info(f"   时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log.info("=" * 60)

    trades = enrich_trades(fetch_recent_trades(now))
    multi_member_buy_tickers = find_multi_member_buys(trades)

    scored = []
    for t in trades:
        score = score_trade(t, multi_member_buy_tickers)
        tier  = score_to_tier(score, t["delay_days"])
        if tier == "excluded":
            continue
        scored.append({"trade": t, "score": score, "tier": tier,
                        "comparison": compare_with_holdings(t)})

    strong = sorted((s for s in scored if s["tier"] == "strong"), key=lambda s: s["score"], reverse=True)
    medium = sorted((s for s in scored if s["tier"] == "medium"), key=lambda s: s["score"], reverse=True)
    weak   = sorted((s for s in scored if s["tier"] == "weak"),   key=lambda s: s["score"], reverse=True)

    sector_breakdown = build_sector_breakdown(trades)
    anti_signals     = [s for s in scored if s["comparison"]["alignment"] == "warn"]

    seen      = load_seen()
    new_items = [s for s in scored if trade_key(s["trade"]) not in seen]

    log.info(f"   📊 强:{len(strong)} 中:{len(medium)} 弱:{len(weak)}  新增:{len(new_items)}")

    # ── watchlist 集成 ────────────────────────────────────────────
    try:
        remove_expired_tickers()
        for s in [*strong, *medium]:
            t = s["trade"]
            if t.get("transaction") == "Buy" and t.get("ticker"):
                add_congress_ticker(
                    ticker=t["ticker"],
                    reason=f"{t['member']} {t['asset_type']}买入（评分{s['score']}）",
                    members=[t["member"]],
                    signal_score=s["score"],
                    sector=(t["sector_info"].get("label_cn")
                            or t["sector_info"].get("sector")
                            or "未知"),
                )
    except Exception as e:
        log.warning(f"   ⚠️ watchlist 更新失败（跳过）: {e}")

    ai_insight = generate_ai_insight(strong, medium, sector_breakdown)

    congress_data = {
        "date":             today_str,
        "strong":           [_serialize(s) for s in strong],
        "medium":           [_serialize(s) for s in medium],
        "watch":            [_serialize(s) for s in weak],
        "sector_breakdown": sector_breakdown,
        "ai_insight":       ai_insight,
    }

    message = build_push_message(today_str, strong, medium, weak, sector_breakdown, anti_signals,
                                 ai_insight=ai_insight)

    if dry_run:
        log.info("\n🔍 [Dry Run] 推送内容预览：\n" + message)
        log.info("\n🔍 [Dry Run] JSON 数据预览：\n" + json.dumps(congress_data, ensure_ascii=False, indent=2))
        return {"message": message, "data": congress_data, "new_count": len(new_items)}

    if new_items:
        log.info("\n📲 推送国会交易信号...")
        if Config.SERVERCHAN_SENDKEY:
            push_serverchan(f"🏛 国会交易信号 {today_str}", message)
        if Config.WECOM_WEBHOOK_URL:
            push_wecom(message)
        if Config.WXPUSHER_APP_TOKEN:
            push_wxpusher(f"🏛 国会交易信号 {today_str}", message)
    else:
        log.info("   ⏭️ 无新增信号，跳过推送")

    try:
        save_congress(congress_data)
        log.info("🌐 国会信号数据已保存到网页")
    except Exception as e:
        log.warning(f"⚠️ 网页数据保存失败: {e}")

    for s in scored:
        seen[trade_key(s["trade"])] = s["trade"]["disclosure_date"]
    save_seen(seen, now)

    log.info("\n" + "=" * 60)
    log.info("✅ 国会交易信号任务完成")
    log.info("=" * 60)

    return {"message": message, "data": congress_data, "new_count": len(new_items)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    run_congress_tracker(dry_run="--dry-run" in sys.argv)
