"""
watchlist_manager.py — 动态 Watchlist 管理 (v1.1)

三层结构:
  core_holdings    → 手动维护，永不自动移除（GLD/WTI/QQQ/TLT）
  long_term        → 手动维护，人工判断进出（现有 26 只）
  congress_signals → 自动进出，由 congress_tracker.py 驱动，90 天无新信号自动移除

用法:
  python watchlist_manager.py          # 清理过期 + 打印当前列表
  python watchlist_manager.py --init   # 强制重建 watchlist.json（保留现有 congress/wheel 数据）
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

WATCHLIST_FILE       = Path(__file__).parent / "docs" / "watchlist.json"
CST                  = timezone(timedelta(hours=8))
CONGRESS_EXPIRY_DAYS = 90
SCREENER_EXPIRY_DAYS = 30  # 强势股筛选信号：连续 30 天未再入选自动移除
MIN_SCORE_ENTRY      = 3  # 中等信号（3分）以上才加入 congress_signals

CORE_HOLDINGS = [
    {"ticker": "GLD", "direction": "long", "weight": 0.30},
    {"ticker": "WTI", "direction": "long", "weight": 0.20},
    {"ticker": "QQQ", "direction": "long", "weight": 0.25},
    {"ticker": "TLT", "direction": "long", "weight": 0.20},
]

LONG_TERM_DEFAULT = [
    "ALB", "ANET", "AVGO", "BDRY", "CEG", "CIEN", "COHR", "COPX",
    "ETHA", "FRO", "GEV",  "GS",   "HEWJ", "LITE", "MP",   "NEE",
    "NVDA", "PLTR", "PWR",  "VRT",  "VST",  "MPWR", "ADI",  "GOOG", "NBIS", "MPC",
]


# ── helpers ──────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


def _expiry(from_date: str) -> str:
    d = datetime.strptime(from_date, "%Y-%m-%d") + timedelta(days=CONGRESS_EXPIRY_DAYS)
    return d.strftime("%Y-%m-%d")


def _expiry_days(from_date: str, days: int) -> str:
    d = datetime.strptime(from_date, "%Y-%m-%d") + timedelta(days=days)
    return d.strftime("%Y-%m-%d")


# ── I/O ──────────────────────────────────────────────────────────────────

def load_watchlist() -> dict:
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"⚠️ watchlist.json 读取失败，使用默认值: {e}")
    return {
        "last_updated":    _today(),
        "core_holdings":   CORE_HOLDINGS,
        "long_term":       list(LONG_TERM_DEFAULT),
        "congress_signals": [],
        "screener_signals": [],
        "suspended":        [],   # 跌破周线200MA被暂停跟踪的标的（记住以便恢复）
        "wheel_positions": [],
    }


def save_watchlist(data: dict) -> None:
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = _today()
    WATCHLIST_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    n_congress = len(data.get("congress_signals", []))
    n_wheel    = len(data.get("wheel_positions", []))
    log.info(f"💾 watchlist.json 已保存 (congress={n_congress}, wheel={n_wheel})")


# ── 读取接口 ──────────────────────────────────────────────────────────────

def get_full_watchlist() -> list:
    """返回各层合并的完整 ticker 列表（去重排序）。"""
    data    = load_watchlist()
    tickers = set()
    tickers.update(h["ticker"] for h in data.get("core_holdings", []))
    tickers.update(data.get("long_term", []))
    tickers.update(s["ticker"] for s in data.get("congress_signals", []))
    tickers.update(s["ticker"] for s in data.get("screener_signals", []))
    return sorted(tickers)


def get_core_holdings() -> list:
    """返回 core_holdings 列表（含 direction/weight）。"""
    return load_watchlist().get("core_holdings", [])


# ── congress_signals 管理 ─────────────────────────────────────────────────

def add_congress_ticker(ticker: str, reason: str, members: list,
                        signal_score: int, sector: str) -> bool:
    """
    将国会信号标的加入 congress_signals 层。
    已存在则刷新过期时间和评分；新标的则追加。
    返回 True 表示实际写入（新增或更新）。
    """
    if signal_score < MIN_SCORE_ENTRY:
        return False
    if not ticker or ticker.upper() in ("", "N/A", "NONE"):
        return False

    today  = _today()
    data   = load_watchlist()
    sigs   = data.setdefault("congress_signals", [])
    exists = next((s for s in sigs if s["ticker"] == ticker), None)

    if exists:
        exists["expires"]      = _expiry(today)
        exists["signal_score"] = max(exists.get("signal_score", 0), signal_score)
        new_m = [m for m in members if m not in exists.get("members", [])]
        exists.setdefault("members", []).extend(new_m)
        exists["reason"] = reason
        log.info(f"   🔄 congress_signals 更新: {ticker} score={exists['signal_score']} expires={exists['expires']}")
    else:
        sigs.append({
            "ticker":       ticker,
            "added_date":   today,
            "expires":      _expiry(today),
            "reason":       reason,
            "members":      list(members),
            "signal_score": signal_score,
            "sector":       sector,
        })
        log.info(f"   ➕ congress_signals 新增: {ticker} ({reason})")

    save_watchlist(data)
    return True


def remove_expired_tickers() -> list:
    """移除 congress_signals 中过期（expires < today）的标的。返回被移除的 ticker 列表。"""
    today  = _today()
    data   = load_watchlist()
    before = data.get("congress_signals", [])
    after  = [s for s in before if s.get("expires", "") >= today]
    removed = [s["ticker"] for s in before if s.get("expires", "") < today]
    if removed:
        data["congress_signals"] = after
        save_watchlist(data)
        log.info(f"   🗑️ congress_signals 过期移除: {removed}")
    return removed


# ── screener_signals 管理（强势股筛选自动进出）────────────────────────────

def sync_screener_signals(entries: list) -> dict:
    """批量刷新 screener_signals 层。入选即加入并常驻（不再按30天过期）；
    移除只由「周线跌破200MA」触发（见 watchlist_gate.py）。已暂停(suspended)的标的不重复加入。
    entries: [{"ticker","sector","bucket"(current/potential)}]。返回 {"added","refreshed"}。"""
    today   = _today()
    data    = load_watchlist()
    sigs    = data.setdefault("screener_signals", [])
    susp_tk = {s["ticker"] for s in data.get("suspended", [])}
    by_tk   = {s["ticker"]: s for s in sigs}
    added, refreshed = [], []
    for e in entries or []:
        tk = str(e.get("ticker") or "").upper()
        if not tk or tk in ("", "N/A", "NONE") or tk in susp_tk:
            continue
        if tk in by_tk:
            s = by_tk[tk]
            s["last_seen"] = today
            s["bucket"]    = e.get("bucket")
            s["sector"]    = e.get("sector")
            s.pop("expires", None)      # 清掉旧的过期字段
            refreshed.append(tk)
        else:
            sigs.append({"ticker": tk, "added_date": today, "last_seen": today,
                         "bucket": e.get("bucket"), "sector": e.get("sector")})
            by_tk[tk] = sigs[-1]
            added.append(tk)
    save_watchlist(data)
    if added:
        log_watchlist_changes([{"ticker": tk, "action": "add", "source": "screener",
                                 "reason": "强势股筛选入选"} for tk in added])
    log.info(f"   📝 screener_signals: 新增{len(added)} 刷新{len(refreshed)}（常驻，仅周线破200MA才移除）")
    return {"added": added, "refreshed": refreshed}


# ── suspended 管理（周线跌破200MA暂停；来源标记；审计日志）─────────────────

CHANGELOG_FILE = Path(__file__).parent / "docs" / "watchlist_changelog.json"


def ticker_source(data: dict, ticker: str) -> str:
    """判断标的来源：manual（core_holdings/long_term，我自己加的）或 screener（强势股筛选）。"""
    tk = ticker.upper()
    if any((h.get("ticker") if isinstance(h, dict) else h) == tk for h in data.get("core_holdings", [])):
        return "manual"
    if tk in [str(x).upper() for x in data.get("long_term", [])]:
        return "manual"
    if any(s["ticker"] == tk for s in data.get("screener_signals", [])):
        return "screener"
    return "manual"


def get_suspended_tickers() -> set:
    return {s["ticker"] for s in load_watchlist().get("suspended", [])}


def get_active_watchlist() -> list:
    """活跃跟踪清单 = 完整清单 − 已暂停。均线信号页只对这些打买卖信号。"""
    susp = get_suspended_tickers()
    return [t for t in get_full_watchlist() if t not in susp]


def log_watchlist_changes(events: list) -> None:
    """把 watchlist 变动（add/remove/suspend/resume）写入审计日志（newest first，封顶2000条）。"""
    if not events:
        return
    today = _today()
    try:
        doc = json.loads(CHANGELOG_FILE.read_text(encoding="utf-8")) if CHANGELOG_FILE.exists() else {}
    except Exception:
        doc = {}
    log_list = doc.get("events", [])
    for e in events:
        log_list.insert(0, {"date": today, **e})
    doc["events"] = log_list[:2000]
    doc["updated"] = today
    CHANGELOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHANGELOG_FILE.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_suspension(suspend: list, resume: list) -> dict:
    """应用暂停/恢复结果（watchlist_gate.py 计算后调用）。
    suspend: [{ticker,source,reason,detail}]  resume: [{ticker,source,reason,detail}]
    暂停：从 screener_signals 物理移出（若属于该层）+ 记入 suspended（记住来源以便恢复）。
    恢复：移出 suspended；若来源是 screener，重新放回 screener_signals。"""
    today = _today()
    data  = load_watchlist()
    susp_layer = data.setdefault("suspended", [])
    susp_map   = {s["ticker"]: s for s in susp_layer}
    sigs       = data.setdefault("screener_signals", [])
    events     = []

    for e in suspend:
        tk = e["ticker"].upper()
        if tk in susp_map:
            continue
        src = e.get("source") or ticker_source(data, tk)
        # 从 screener_signals 物理移出（若在）
        data["screener_signals"] = [s for s in data["screener_signals"] if s["ticker"] != tk]
        entry = {"ticker": tk, "source": src, "since": today,
                 "reason": e.get("reason", "周线跌破200MA"), "detail": e.get("detail", "")}
        susp_layer.append(entry); susp_map[tk] = entry
        events.append({"ticker": tk, "action": "suspend", "source": src,
                       "reason": entry["reason"], "detail": entry["detail"]})

    for e in resume:
        tk = e["ticker"].upper()
        if tk not in susp_map:
            continue
        src = susp_map[tk].get("source", "manual")
        data["suspended"] = [s for s in data["suspended"] if s["ticker"] != tk]
        susp_layer = data["suspended"]
        if src == "screener" and not any(s["ticker"] == tk for s in data["screener_signals"]):
            data["screener_signals"].append({"ticker": tk, "added_date": today,
                                              "last_seen": today, "bucket": "resumed", "sector": ""})
        events.append({"ticker": tk, "action": "resume", "source": src,
                       "reason": e.get("reason", "回到周线150/20MA上方且连续2季盈利上升"),
                       "detail": e.get("detail", "")})

    save_watchlist(data)
    log_watchlist_changes(events)
    log.info(f"   ⏸️ 暂停{len(suspend)} ▶️ 恢复{len(resume)}")
    return {"suspended": [e['ticker'] for e in suspend], "resumed": [e['ticker'] for e in resume]}


# ── wheel_positions 管理 ──────────────────────────────────────────────────

def add_wheel_position(ticker: str, position_type: str, strike: float,
                       expiry: str, premium: float, contracts: int) -> None:
    """记录新的 Wheel 期权仓位。"""
    data = load_watchlist()
    data.setdefault("wheel_positions", []).append({
        "ticker":           ticker,
        "type":             position_type,
        "strike":           strike,
        "expiry":           expiry,
        "premium_received": premium,
        "opened_date":      _today(),
        "contracts":        contracts,
        "status":           "open",
    })
    save_watchlist(data)
    log.info(f"   ➕ wheel_positions 新增: {ticker} {position_type} ${strike} exp {expiry}")


def update_wheel_position(ticker: str, strike: float, expiry: str, status: str) -> bool:
    """更新 Wheel 仓位状态（open / closed / assigned）。"""
    data = load_watchlist()
    for pos in data.get("wheel_positions", []):
        if (pos["ticker"] == ticker
                and abs(pos.get("strike", 0) - strike) < 0.01
                and pos.get("expiry") == expiry):
            pos["status"] = status
            save_watchlist(data)
            log.info(f"   ✏️ wheel_positions 更新: {ticker} ${strike} {expiry} → {status}")
            return True
    log.warning(f"   ⚠️ update_wheel_position: 未找到 {ticker} ${strike} {expiry}")
    return False


def get_active_wheel_positions() -> list:
    """返回所有状态为 open 的 Wheel 仓位。"""
    return [p for p in load_watchlist().get("wheel_positions", []) if p.get("status") == "open"]


# ── CLI ──────────────────────────────────────────────────────────────────

def _init_file() -> None:
    """强制重建 watchlist.json，保留现有 congress_signals 和 wheel_positions。"""
    existing = load_watchlist()
    data = {
        "last_updated":    _today(),
        "core_holdings":   CORE_HOLDINGS,
        "long_term":       list(LONG_TERM_DEFAULT),
        "congress_signals": existing.get("congress_signals", []),
        "screener_signals": existing.get("screener_signals", []),
        "suspended":        existing.get("suspended", []),
        "wheel_positions":  existing.get("wheel_positions", []),
    }
    save_watchlist(data)
    print(f"✅ watchlist.json 已初始化 ({WATCHLIST_FILE})")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if "--init" in sys.argv:
        _init_file()
    else:
        removed = remove_expired_tickers()
        if removed:
            print(f"🗑️ 已移除过期标的: {removed}")
        tickers = get_full_watchlist()
        data    = load_watchlist()
        print(f"\n📋 当前完整 Watchlist ({len(tickers)} 只):")
        print(f"  Core:     {[h['ticker'] for h in data.get('core_holdings', [])]}")
        print(f"  LongTerm: {data.get('long_term', [])}")
        cs = data.get("congress_signals", [])
        print(f"  Congress: {[s['ticker'] for s in cs]} ({len(cs)} 条)")
        wp = get_active_wheel_positions()
        print(f"  Wheel:    {[p['ticker'] for p in wp]} ({len(wp)} 活跃仓位)")
