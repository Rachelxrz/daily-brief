#!/usr/bin/env python3
"""
ma_cross_signal.py — 20/50 均线 × Supertrend(10,4) 买卖信号 v1.0

规则（用户 2026-07-21 指定）：
  BUY  = MA20 > MA50  且  Supertrend(10, 4) 方向为 UP
  SELL = MA20 < MA50  且  Supertrend(10, 4) 方向为 DOWN
  其余 = NEUTRAL（无信号）

信号事件在「状态翻转进入 BUY / SELL」的当天记录一次，
每只标的保留最近 **2** 条历史（类型 + 日期 + 当时价格/均线）。
状态保持不变则不重复记录；回到 NEUTRAL 也不记录（NEUTRAL 不是信号）。

标的：docs/watchlist.json 的 core_holdings + long_term（动态读取），排除 EXCLUDE（当前 29 只）
输出：docs/data.json 的 "ma_signal" key（供网页「🔀 均线信号」tab）
持久化：ma_signal_history.json（跨 GitHub Actions checkout 必须一起提交，否则历史会丢）
不推送微信（遵循「微信只推新闻」规则）。

复用 signal_advisor.py 的 get_ohlcv / calc_supertrend，避免重复实现指标。
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np

from signal_advisor import get_ohlcv, calc_supertrend

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_DIR  = Path(__file__).parent
DOCS_DIR  = BASE_DIR / "docs"
DATA_FILE = DOCS_DIR / "data.json"
WATCHLIST_FILE = DOCS_DIR / "watchlist.json"
HIST_FILE = BASE_DIR / "ma_signal_history.json"

ST_PERIOD     = 10
ST_MULTIPLIER = 4.0
MA_FAST = 20
MA_SLOW = 50
KEEP_SIGNALS = 2   # 每只标的保留最近 2 条信号历史

# 从均线信号中排除（不影响 watchlist.json 里的真实持仓/其他模块）。
# WTI：yfinance 的 WTI 是 W&T Offshore（小盘油气股）而非原油，信号会误导，故剔除。
EXCLUDE = {"WTI"}


def _today_et() -> str:
    """交易日期用美东时间，与 save_to_web / signal_advisor 一致，避免盘后跨到 CST 次日。"""
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")


def _now_cst() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M CST")


def load_tickers() -> list:
    """core_holdings + long_term，按出现顺序去重。"""
    try:
        wl = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"读取 watchlist.json 失败，回退空列表：{e}")
        return []
    tickers = []
    for h in wl.get("core_holdings", []):
        t = h.get("ticker") if isinstance(h, dict) else h
        if t:
            tickers.append(str(t).upper())
    for t in wl.get("long_term", []):
        if t:
            tickers.append(str(t).upper())
    # 去重保序 + 排除
    seen, out = set(), []
    for t in tickers:
        if t not in seen and t not in EXCLUDE:
            seen.add(t)
            out.append(t)
    return out


def analyze(ticker: str) -> dict:
    """返回单只标的的 MA/Supertrend 状态与当前信号。"""
    df = get_ohlcv(ticker, period="8mo")
    if df.empty or len(df) < MA_SLOW:
        return {"ticker": ticker, "signal": "NO_DATA"}

    close = df["Close"].values.astype(float)
    price   = round(float(close[-1]), 2)
    prev_c  = float(close[-2]) if len(close) >= 2 else price
    day_chg = round((price - prev_c) / prev_c * 100, 2) if prev_c else 0.0

    ma20 = round(float(np.mean(close[-MA_FAST:])), 2)
    ma50 = round(float(np.mean(close[-MA_SLOW:])), 2)
    ma_gap_pct = round((ma20 / ma50 - 1) * 100, 2) if ma50 else 0.0

    st = calc_supertrend(df, period=ST_PERIOD, multiplier=ST_MULTIPLIER)
    if not st:
        return {"ticker": ticker, "signal": "NO_DATA"}

    st_dir   = st.get("direction", "")
    st_value = st.get("value")
    st_bars  = st.get("bars_since_flip")

    if ma20 > ma50 and st_dir == "UP":
        signal = "BUY"
    elif ma20 < ma50 and st_dir == "DOWN":
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    return {
        "ticker":     ticker,
        "price":      price,
        "day_chg":    day_chg,
        "ma20":       ma20,
        "ma50":       ma50,
        "ma_gap_pct": ma_gap_pct,
        "st_dir":     st_dir,
        "st_value":   st_value,
        "st_bars":    st_bars,
        "signal":     signal,
    }


def _supertrend_series(df, period: int = ST_PERIOD, multiplier: float = ST_MULTIPLIER):
    """
    逐日 Supertrend：返回 (trend, line) 两个数组，与 signal_advisor.calc_supertrend
    完全同算法（同样的 Wilder ATR、final band 递推、翻转规则），保证最后一根与在线信号一致。
    trend[i] ∈ {0=warmup, 1=多头, -1=空头}；line[i] 为当根 Supertrend 线值（NaN=未定）。
    """
    high  = df["High"].values.astype(float)
    low   = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    n = len(close)
    trend = np.zeros(n, dtype=int)
    line  = np.full(n, np.nan)
    if n < period * 2 + 5:
        return trend, line

    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))

    atr = np.full(n, np.nan)
    atr[period] = tr[1:period + 1].mean()
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    hl2     = (high + low) / 2.0
    up_band = hl2 + multiplier * atr
    dn_band = hl2 - multiplier * atr

    final_up = np.full(n, np.nan)
    final_dn = np.full(n, np.nan)
    for i in range(1, n):
        if np.isnan(up_band[i]):
            continue
        fu_prev = final_up[i - 1]
        fd_prev = final_dn[i - 1]
        final_up[i] = (up_band[i] if (np.isnan(fu_prev) or up_band[i] < fu_prev or close[i - 1] > fu_prev) else fu_prev)
        final_dn[i] = (dn_band[i] if (np.isnan(fd_prev) or dn_band[i] > fd_prev or close[i - 1] < fd_prev) else fd_prev)

        prev = trend[i - 1]
        if prev == 0:
            trend[i] = 1 if close[i] > final_dn[i] else -1
        elif prev == 1:
            trend[i] = -1 if close[i] < final_dn[i] else 1
        else:
            trend[i] = 1 if close[i] > final_up[i] else -1

        line[i] = final_dn[i] if trend[i] == 1 else final_up[i]

    return trend, line


def signal_events(df, keep: int = KEEP_SIGNALS) -> list:
    """
    回溯历史 K 线，逐日判定 BUY/SELL/NEUTRAL，找出真正「翻转进入 BUY/SELL」的日期。
    翻转 = 当日为 BUY/SELL 且不同于前一日状态。返回最近 keep 条事件（最新在前）。
    """
    close = df["Close"].values.astype(float)
    n = len(close)
    if n < MA_SLOW + 1:
        return []

    cs = df["Close"]
    ma20_s = cs.rolling(MA_FAST).mean().values
    ma50_s = cs.rolling(MA_SLOW).mean().values
    trend, line = _supertrend_series(df)
    dates = [d.strftime("%Y-%m-%d") for d in df.index]

    events = []
    prev_state = None
    for i in range(n):
        if np.isnan(ma20_s[i]) or np.isnan(ma50_s[i]) or trend[i] == 0:
            continue
        if ma20_s[i] > ma50_s[i] and trend[i] == 1:
            state = "BUY"
        elif ma20_s[i] < ma50_s[i] and trend[i] == -1:
            state = "SELL"
        else:
            state = "NEUTRAL"

        if state in ("BUY", "SELL") and state != prev_state:
            events.append({
                "type":  state,
                "date":  dates[i],
                "price": round(float(close[i]), 2),
                "ma20":  round(float(ma20_s[i]), 2),
                "ma50":  round(float(ma50_s[i]), 2),
                "st_value": None if np.isnan(line[i]) else round(float(line[i]), 2),
            })
        prev_state = state

    return events[-keep:]


def backfill():
    """
    用历史数据重建 ma_signal_history.json：每只标的回查最近 2 次真实信号翻转日期，
    并把 last_state 设为最新一根的状态，供后续每日增量接续。
    """
    tickers = load_tickers()
    log.info("=" * 60)
    log.info(f"🔁 回查历史信号 · 重建 {HIST_FILE.name}（{len(tickers)} 只，约 2 年历史）")
    log.info("=" * 60)
    hist = {}
    for t in tickers:
        df = get_ohlcv(t, period="2y")
        if df.empty or len(df) < MA_SLOW + 1:
            log.warning(f"  {t:<6} ⚠️ 历史不足，跳过")
            continue
        evs = signal_events(df)              # 最近 2 条，最新在前？——按时间正序，末尾最新
        res = analyze(t)                     # 当前状态（与在线一致）
        last_state = res.get("signal")
        if last_state == "NO_DATA":
            last_state = None
        hist[t] = {"last_state": last_state, "signals": evs}
        shown = "；".join(f"{e['type']}@{e['date']}" for e in evs) or "无"
        log.info(f"  {t:<6} last={last_state:<7} 最近两次[{shown}]")
    save_history(hist)
    log.info(f"✅ 已重建 {HIST_FILE.name}：{len(hist)} 只")


def load_history() -> dict:
    if HIST_FILE.exists():
        try:
            return json.loads(HIST_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"读取 {HIST_FILE.name} 失败，视为空：{e}")
    return {}


def save_history(hist: dict):
    HIST_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")


def update_history(hist: dict, res: dict, today: str) -> dict:
    """
    根据今日状态更新某只标的的历史。
    只有当状态「翻转进入 BUY/SELL」（今日 BUY/SELL 且不同于上一次记录的状态）时，
    才追加一条信号事件，并裁剪到最近 KEEP_SIGNALS 条。
    """
    ticker = res["ticker"]
    state  = res["signal"]
    rec = hist.get(ticker) or {"last_state": None, "signals": []}
    prev_state = rec.get("last_state")

    if state in ("BUY", "SELL") and state != prev_state:
        rec.setdefault("signals", []).append({
            "type":  state,
            "date":  today,
            "price": res.get("price"),
            "ma20":  res.get("ma20"),
            "ma50":  res.get("ma50"),
            "st_value": res.get("st_value"),
        })
        rec["signals"] = rec["signals"][-KEEP_SIGNALS:]

    # NO_DATA 不改变 last_state（数据缺失不应擦掉真实状态）
    if state != "NO_DATA":
        rec["last_state"] = state

    hist[ticker] = rec
    return rec


# 排序：BUY → SELL → NEUTRAL → NO_DATA；组内按均线差降序
_SIG_ORDER = {"BUY": 0, "SELL": 1, "NEUTRAL": 2, "NO_DATA": 3}


def save_web(rows: list, today: str):
    data = {}
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    counts = {"buy": 0, "sell": 0, "neutral": 0, "no_data": 0}
    for r in rows:
        counts[{"BUY": "buy", "SELL": "sell", "NEUTRAL": "neutral", "NO_DATA": "no_data"}[r["signal"]]] += 1

    payload = {
        "date":    today,
        "updated": _now_cst(),
        "rule":    "BUY = MA20>MA50 且 Supertrend(10,4)↑ ；SELL = MA20<MA50 且 Supertrend(10,4)↓",
        "counts":  counts,
        "tickers": rows,
    }

    if today not in data:
        data[today] = {}
    data[today]["updated"]   = _now_cst()
    data[today]["ma_signal"] = payload

    DOCS_DIR.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"💾 ma_signal 已写入 data.json：{today}  BUY={counts['buy']} SELL={counts['sell']} "
             f"NEUTRAL={counts['neutral']} NO_DATA={counts['no_data']}")


def run(dry_run: bool = False):
    today = _today_et()
    tickers = load_tickers()
    log.info("=" * 60)
    log.info(f"🔀 均线×Supertrend 信号  {today}  ({len(tickers)} 只)")
    log.info("=" * 60)

    hist = load_history()
    rows = []
    for t in tickers:
        res = analyze(t)
        rec = update_history(hist, res, today)
        res["history"] = list(reversed(rec.get("signals", [])))  # 最新在前
        rows.append(res)
        if res["signal"] == "NO_DATA":
            log.warning(f"  {t:<6} ⚠️ 数据不足")
        else:
            log.info(f"  {t:<6} {res['signal']:<8} ${res['price']}  MA20 {res['ma20']} / MA50 {res['ma50']}  ST{res['st_dir']}")

    rows.sort(key=lambda r: (_SIG_ORDER.get(r["signal"], 9), -(r.get("ma_gap_pct") or -999)))

    if dry_run:
        log.info("🧪 dry-run：不写 data.json / 不落历史")
        for r in rows:
            if r["signal"] in ("BUY", "SELL"):
                h = "；".join(f"{s['type']}@{s['date']}" for s in r.get("history", []))
                log.info(f"    {r['ticker']:<6} {r['signal']}  历史[{h}]")
        return

    save_history(hist)
    save_web(rows, today)
    log.info("✅ 完成")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="20/50 均线 × Supertrend(10,4) 买卖信号")
    p.add_argument("--dry-run",  action="store_true", help="不写文件，仅打印")
    p.add_argument("--backfill", action="store_true", help="回查历史，重建 ma_signal_history.json 的最近两次信号日期")
    args = p.parse_args()
    if args.backfill:
        backfill()
    else:
        run(args.dry_run)
