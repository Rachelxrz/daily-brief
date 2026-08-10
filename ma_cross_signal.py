#!/usr/bin/env python3
"""
ma_cross_signal.py — 20/50 均线 × Supertrend(10,4) 买卖信号 v1.1

规则（用户 2026-07-21 指定；2026-07-30 按「策略1」加入 MA150 分级卖出）：
  BUY       = MA20 > MA50  且  Supertrend(10, 4) 方向为 UP        → 全仓买入
  SELL_HALF = MA20 < MA50  且  Supertrend(10, 4) 方向为 DOWN      → 减半（死叉）
  SELL_ALL  = 收盘价 < MA150                                       → 清仓（跌破150均线地板）
  其余 = NEUTRAL（无信号）
  优先级（风险优先）：SELL_ALL > SELL_HALF > BUY > NEUTRAL
  MA150 与 MA20/MA50 同一时间框架（ETF=150周、个股/杠杆ETF=150日）；历史不足150根则不触发 SELL_ALL。

时间框架（2026-07-25 指定）：
  个股 → 日线；ETF → 周线（MA20/MA50 = 20/50 周，Supertrend 用周线 K）；
  杠杆 ETF（DAILY_OVERRIDE：USD 2×、SOXL 3×）→ 仍按日线。
  ETF/个股用 yfinance quoteType 自动判定并缓存于 etf_flags.json。

信号事件在「状态翻转进入 BUY / SELL」的当根 K 收盘记录一次（周线记为周五、日线记为当日），
每只标的保留最近 **2** 条历史（类型 + 日期 + 当时价格/均线）。
状态保持不变则不重复记录；回到 NEUTRAL 也不记录（NEUTRAL 不是信号）。

标的：docs/watchlist.json 的 core_holdings + long_term（动态读取），排除 EXCLUDE
输出：docs/data.json 的 "ma_signal" key（供网页「🔀 均线信号」tab），含「近一周买卖」清单
持久化：ma_signal_history.json + etf_flags.json（跨 GitHub Actions checkout 必须一起提交）
推送微信摘要（2026-08 起：微信只推「每日简报」+「均线信号」两个板块，其它只上网页）。

复用 signal_advisor.py 的 get_ohlcv / calc_supertrend，避免重复实现指标。
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

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
ETF_CACHE_FILE = BASE_DIR / "etf_flags.json"

ST_PERIOD     = 10
ST_MULTIPLIER = 4.0
MA_FAST = 20
MA_SLOW = 50
MA_LONG = 150      # 150 均线地板
KEEP_SIGNALS = 2   # 每只标的保留最近 2 条信号历史
RECENT_DAYS  = 7   # 「近一周买卖」窗口

# 策略C(闸门融合,回测最优阈值≈3):跌破MA150 时,只有市场结构红灯≥3(确认崩盘体制)才清仓;
# 否则继续持有,等 MA50<MA150 再清。红灯数 = macro_gate 六因子(市场级,当日一个数)。
C_RED_THRESHOLD = 3
GATE_VOTES = None   # 当日市场结构红灯数(0-6),run() 里算一次;None=取不到,C 回退旧策略


def _compute_gate_votes():
    """调 macro_gate 算当日六因子红灯数;失败返回 None(C 退回旧策略)。"""
    try:
        import macro_credit_gate as macro_gate
        return int(macro_gate.compute().get("votes"))
    except Exception as e:
        log.warning(f"⚠️ 市场结构红灯数取用失败，策略C 回退旧策略：{e}")
        return None

# 从均线信号中排除（不影响 watchlist.json 里的真实持仓/其他模块）。
# WTI：yfinance 的 WTI 是 W&T Offshore（小盘油气股）而非原油，信号会误导，故剔除。
EXCLUDE = {"WTI"}

# 杠杆 ETF：虽是 ETF，但仍按日线计算（Rachel 2026-07-25）。
# USD = ProShares Ultra Semiconductors(2×)，SOXL = Direxion Daily Semiconductor Bull(3×)。
DAILY_OVERRIDE = {"USD", "SOXL"}


def _today_et() -> str:
    """交易日期用美东时间，与 save_to_web / signal_advisor 一致，避免盘后跨到 CST 次日。"""
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")


def _now_cst() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M CST")


def _load_wl() -> dict:
    try:
        return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"读取 watchlist.json 失败：{e}")
        return {}


def load_tickers() -> list:
    """活跃跟踪清单 = core_holdings + long_term + screener_signals，去重；
    已暂停(周线破200MA)的标的排除，不再计算买卖信号。"""
    wl = _load_wl()
    suspended = {s.get("ticker") for s in wl.get("suspended", []) if isinstance(s, dict)}
    tickers = []
    for h in wl.get("core_holdings", []):
        t = h.get("ticker") if isinstance(h, dict) else h
        if t:
            tickers.append(str(t).upper())
    for t in wl.get("long_term", []):
        if t:
            tickers.append(str(t).upper())
    for s in wl.get("screener_signals", []):   # 强势股筛选自动加入的标的
        t = s.get("ticker") if isinstance(s, dict) else s
        if t:
            tickers.append(str(t).upper())
    seen, out = set(), []
    for t in tickers:
        if t not in seen and t not in EXCLUDE and t not in suspended:
            seen.add(t)
            out.append(t)
    return out


def watchlist_meta() -> tuple:
    """返回 (source_map, suspended_list, class_map)。source_map: {ticker: 'screener'|'manual'}；
    suspended_list: [{ticker,source,reason,detail,since}]；class_map: {ticker: archetype}（个股分档）。"""
    wl = _load_wl()
    src = {}
    for h in wl.get("core_holdings", []):
        t = (h.get("ticker") if isinstance(h, dict) else h)
        if t:
            src[str(t).upper()] = "manual"
    for t in wl.get("long_term", []):
        if t:
            src[str(t).upper()] = "manual"
    for s in wl.get("screener_signals", []):
        t = s.get("ticker") if isinstance(s, dict) else s
        if t:
            src.setdefault(str(t).upper(), "screener")
    susp = [{"ticker": s.get("ticker"), "source": s.get("source"),
             "reason": s.get("reason"), "detail": s.get("detail"), "since": s.get("since")}
            for s in wl.get("suspended", []) if isinstance(s, dict)]
    cmap = {tk: (info or {}).get("archetype")
            for tk, info in ((wl.get("classification") or {}).get("tickers", {})).items()}
    return src, susp, cmap


# ── ETF/个股分类（yfinance quoteType，缓存到 etf_flags.json）────────────────
def load_etf_cache() -> dict:
    if ETF_CACHE_FILE.exists():
        try:
            return json.loads(ETF_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_etf_cache(cache: dict):
    ETF_CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def is_etf(ticker: str, cache: dict) -> bool:
    """是否 ETF；缓存未命中时查一次 yfinance quoteType 并写入缓存。"""
    if ticker in cache:
        return bool(cache[ticker])
    try:
        qt = (yf.Ticker(ticker).get_info() or {}).get("quoteType", "")
        cache[ticker] = (qt == "ETF")
        log.info(f"  分类 {ticker}: quoteType={qt} → {'ETF' if cache[ticker] else '个股'}")
    except Exception as e:
        log.warning(f"  {ticker} quoteType 查询失败，暂按个股：{e}")
        cache[ticker] = False
    return cache[ticker]


def timeframe_of(ticker: str, cache: dict) -> str:
    """'W' = 周线（ETF，非杠杆）；'D' = 日线（个股 + 杠杆 ETF）。"""
    if ticker in DAILY_OVERRIDE:
        return "D"
    return "W" if is_etf(ticker, cache) else "D"


def _to_weekly(df):
    """日线 OHLCV → 周线（以周五为界，当前未完成周也生成一根 forming bar）。"""
    agg = {
        "Open":  df["Open"].resample("W-FRI").first(),
        "High":  df["High"].resample("W-FRI").max(),
        "Low":   df["Low"].resample("W-FRI").min(),
        "Close": df["Close"].resample("W-FRI").last(),
    }
    if "Volume" in df:
        agg["Volume"] = df["Volume"].resample("W-FRI").sum()
    w = pd.DataFrame(agg).dropna(subset=["Open", "High", "Low", "Close"])
    return w


def load_bars(ticker: str, cache: dict):
    """
    取足够历史，按标的时间框架返回用于计算的 df。
    price / day_chg 始终取「最新日线」（真实最新价与当日涨跌），
    指标（MA/Supertrend）用 calc（周线 ETF 为周线 K，其余为日线 K）。
    """
    tf = timeframe_of(ticker, cache)
    period = "5y" if tf == "W" else "2y"
    dfd = get_ohlcv(ticker, period=period)
    if dfd.empty:
        return None
    close_d = dfd["Close"].values.astype(float)
    price   = round(float(close_d[-1]), 2)
    prev_d  = float(close_d[-2]) if len(close_d) >= 2 else price
    day_chg = round((price - prev_d) / prev_d * 100, 2) if prev_d else 0.0
    calc = _to_weekly(dfd) if tf == "W" else dfd
    if calc.empty:
        return None
    asof = calc.index[-1].strftime("%Y-%m-%d")
    return {"tf": tf, "calc": calc, "price": price, "day_chg": day_chg, "asof": asof}


def _tf_cn(tf: str) -> str:
    return "周线" if tf == "W" else "日线"


def _compute(ticker: str, bars: dict) -> dict:
    """由已取好的 bars 计算当前 MA/Supertrend 状态与信号（不再联网）。"""
    tf_cn = _tf_cn(bars["tf"])
    calc  = bars["calc"]
    close = calc["Close"].values.astype(float)
    if len(close) < MA_SLOW:
        return {"ticker": ticker, "tf": tf_cn, "signal": "NO_DATA"}

    ma20 = round(float(np.mean(close[-MA_FAST:])), 2)
    ma50 = round(float(np.mean(close[-MA_SLOW:])), 2)
    ma_gap_pct = round((ma20 / ma50 - 1) * 100, 2) if ma50 else 0.0
    # MA150 地板（历史不足 150 根则为 None，不触发清仓）
    ma150 = round(float(np.mean(close[-MA_LONG:])), 2) if len(close) >= MA_LONG else None
    ma200 = round(float(np.mean(close[-200:])), 2) if len(close) >= 200 else None
    last_close = float(close[-1])

    st = calc_supertrend(calc, period=ST_PERIOD, multiplier=ST_MULTIPLIER)
    if not st:
        return {"ticker": ticker, "tf": tf_cn, "signal": "NO_DATA"}

    st_dir   = st.get("direction", "")
    st_value = st.get("value")
    st_bars  = st.get("bars_since_flip")

    below150 = ma150 is not None and last_close < ma150
    ma_cross = ma150 is not None and ma50 < ma150      # MA50 < MA150

    # 旧策略(A)：SELL_ALL > SELL_HALF > BUY > NEUTRAL；跌破150即清仓
    if below150:
        signal = "SELL_ALL"                                   # 跌破150均线 → 清仓
    elif ma20 < ma50 and st_dir == "DOWN":
        signal = "SELL_HALF"                                  # 死叉 → 减半
    elif ma20 > ma50 and st_dir == "UP":
        signal = "BUY"                                        # 全仓买入
    else:
        signal = "NEUTRAL"

    # 策略C(闸门融合)：MA50<MA150 全清；或 跌破150 且 红灯≥3 全清；否则跌破150也继续持有
    votes = GATE_VOTES
    clear_c = ma_cross or (below150 and (votes is None or votes >= C_RED_THRESHOLD))
    if clear_c:
        signal_c = "SELL_ALL"
    elif ma20 < ma50 and st_dir == "DOWN":
        signal_c = "SELL_HALF"
    elif ma20 > ma50 and st_dir == "UP" and not below150:
        signal_c = "BUY"
    elif below150:
        signal_c = "HOLD"                                     # 跌破150但闸门未确认崩盘 → 持有（与旧策略分歧）
    else:
        signal_c = "NEUTRAL"

    return {
        "ticker":     ticker,
        "tf":         tf_cn,
        "price":      bars["price"],
        "day_chg":    bars["day_chg"],
        "asof":       bars["asof"],
        "ma20":       ma20,
        "ma50":       ma50,
        "ma150":      ma150,
        "ma200":      ma200,
        "below_ma150": below150,
        "ma50_below_ma150": ma_cross,
        "ma50_below_ma200": (ma200 is not None and ma50 < ma200),
        "ma_gap_pct": ma_gap_pct,
        "st_dir":     st_dir,
        "st_value":   st_value,
        "st_bars":    st_bars,
        "signal":     signal,
        "signal_c":   signal_c,
    }


def analyze(ticker: str, cache: dict) -> dict:
    """返回单只标的的 MA/Supertrend 状态与当前信号（按其时间框架）。"""
    bars = load_bars(ticker, cache)
    if bars is None:
        return {"ticker": ticker, "signal": "NO_DATA"}
    return _compute(ticker, bars)


def archetype_signal(r: dict, arch: str, votes) -> tuple:
    """按分档给出差异化买卖信号，返回 (signal, rule_label)。
       稳定核心 = 买入持有(不出卖出信号)；成长核心 = 策略C 但清仓用 MA50<MA200；
       趋势成长/题材投机/其它 = 策略C(清仓 MA50<MA150)。"""
    ma20, ma50, ma150, ma200 = r.get("ma20"), r.get("ma50"), r.get("ma150"), r.get("ma200")
    price = r.get("price")
    st_up = r.get("st_dir") == "UP"; st_dn = r.get("st_dir") == "DOWN"
    below150 = r.get("below_ma150")
    if ma150 is None or ma50 is None:
        return r.get("signal_c"), "策略C"                       # 历史不足 → 退回策略C

    if arch == "稳定核心":                                       # 买入持有：只出买/持有，不出卖
        if ma50 > ma150 and not below150:
            return ("BUY" if (price is not None and price <= ma50) else "HOLD"), "买入持有"
        return "NEUTRAL", "买入持有"

    if arch == "成长性核心":
        clear = (ma200 is not None and ma50 < ma200) or (below150 and (votes is None or votes >= C_RED_THRESHOLD))
        rule = "策略C·50×200"
    else:                                                        # 趋势成长 / 题材投机 / 其它
        clear = (ma50 < ma150) or (below150 and (votes is None or votes >= C_RED_THRESHOLD))
        rule = "策略C·50×150"
    if clear:
        return "SELL_ALL", rule
    if ma20 < ma50 and st_dn:
        return "SELL_HALF", rule
    if ma20 > ma50 and st_up and not below150:
        return "BUY", rule
    if below150:
        return "HOLD", rule
    return "NEUTRAL", rule


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
    ma150_s = cs.rolling(MA_LONG).mean().values
    trend, line = _supertrend_series(df)
    dates = [d.strftime("%Y-%m-%d") for d in df.index]

    events = []
    prev_state = None
    for i in range(n):
        if np.isnan(ma20_s[i]) or np.isnan(ma50_s[i]) or trend[i] == 0:
            continue
        # 与 _compute 同优先级：SELL_ALL > SELL_HALF > BUY > NEUTRAL
        if not np.isnan(ma150_s[i]) and close[i] < ma150_s[i]:
            state = "SELL_ALL"
        elif ma20_s[i] < ma50_s[i] and trend[i] == -1:
            state = "SELL_HALF"
        elif ma20_s[i] > ma50_s[i] and trend[i] == 1:
            state = "BUY"
        else:
            state = "NEUTRAL"

        if state in ("BUY", "SELL_HALF", "SELL_ALL") and state != prev_state:
            events.append({
                "type":  state,
                "date":  dates[i],
                "price": round(float(close[i]), 2),
                "ma20":  round(float(ma20_s[i]), 2),
                "ma50":  round(float(ma50_s[i]), 2),
                "ma150": None if np.isnan(ma150_s[i]) else round(float(ma150_s[i]), 2),
                "st_value": None if np.isnan(line[i]) else round(float(line[i]), 2),
            })
        prev_state = state

    return events[-keep:]


def backfill():
    """
    用历史数据重建 ma_signal_history.json：每只标的按其时间框架（周线 ETF / 日线）
    回查最近 2 次真实信号翻转日期，并把 last_state 设为最新一根的状态，供后续每日增量接续。
    同时刷新 etf_flags.json 分类缓存。
    """
    cache = load_etf_cache()
    tickers = load_tickers()
    log.info("=" * 60)
    log.info(f"🔁 回查历史信号 · 重建 {HIST_FILE.name}（{len(tickers)} 只）")
    log.info("=" * 60)
    hist = {}
    for t in tickers:
        bars = load_bars(t, cache)
        if bars is None or len(bars["calc"]) < MA_SLOW + 1:
            log.warning(f"  {t:<6} ⚠️ 历史不足，跳过")
            continue
        evs = signal_events(bars["calc"])    # 按时间正序，末尾最新
        res = _compute(t, bars)              # 当前状态（与在线一致，同一份 bars）
        last_state = res.get("signal")
        if last_state == "NO_DATA":
            last_state = None
        hist[t] = {"last_state": last_state, "signals": evs}
        shown = "；".join(f"{e['type']}@{e['date']}" for e in evs) or "无"
        log.info(f"  {t:<6} [{_tf_cn(bars['tf'])}] last={str(last_state):<7} 最近两次[{shown}]")
    save_etf_cache(cache)
    save_history(hist)
    log.info(f"✅ 已重建 {HIST_FILE.name}：{len(hist)} 只（分类缓存 {ETF_CACHE_FILE.name}）")


def load_history() -> dict:
    if HIST_FILE.exists():
        try:
            return json.loads(HIST_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"读取 {HIST_FILE.name} 失败，视为空：{e}")
    return {}


def save_history(hist: dict):
    HIST_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")


def update_history(hist: dict, res: dict) -> dict:
    """
    根据当根 K 状态更新某只标的的历史。
    只有当状态「翻转进入 BUY/SELL」（当前 BUY/SELL 且不同于上一次记录的状态）时，
    才追加一条信号事件（日期用当根 K 收盘 asof：周线=周五、日线=当日），
    并裁剪到最近 KEEP_SIGNALS 条。
    """
    ticker = res["ticker"]
    state  = res["signal"]
    asof   = res.get("asof")
    rec = hist.get(ticker) or {"last_state": None, "signals": []}
    prev_state = rec.get("last_state")

    if state in ("BUY", "SELL_HALF", "SELL_ALL") and state != prev_state and asof:
        rec.setdefault("signals", []).append({
            "type":  state,
            "date":  asof,
            "price": res.get("price"),
            "ma20":  res.get("ma20"),
            "ma50":  res.get("ma50"),
            "ma150": res.get("ma150"),
            "st_value": res.get("st_value"),
        })
        rec["signals"] = rec["signals"][-KEEP_SIGNALS:]

    # NO_DATA 不改变 last_state（数据缺失不应擦掉真实状态）
    if state != "NO_DATA":
        rec["last_state"] = state

    hist[ticker] = rec
    return rec


# 排序：BUY → SELL_ALL → SELL_HALF → NEUTRAL → NO_DATA；组内按均线差降序
_SIG_ORDER = {"BUY": 0, "SELL_ALL": 1, "SELL_HALF": 2, "NEUTRAL": 3, "NO_DATA": 4}


def _days_between(d_from: str, d_to: str):
    try:
        a = datetime.strptime(d_from, "%Y-%m-%d").date()
        b = datetime.strptime(d_to, "%Y-%m-%d").date()
        return (b - a).days
    except Exception:
        return None


def build_recent(rows: list, today: str, days: int = RECENT_DAYS) -> list:
    """近一周内发生过买入/卖出翻转的标的（取最近一次事件在窗口内的）。"""
    recent = []
    for r in rows:
        hist = r.get("history") or []
        if not hist:
            continue
        last = hist[0]                       # 最新在前
        prev = hist[1] if len(hist) > 1 else None   # 上一次信号
        gap = _days_between(last.get("date", ""), today)
        if gap is not None and 0 <= gap <= days:
            recent.append({
                "ticker":    r["ticker"],
                "type":      last["type"],
                "date":      last["date"],
                "tf":        r.get("tf", ""),
                "price":     r.get("price"),
                "signal":    r.get("signal"),   # 当前状态（旧策略A）
                "signal_c":  r.get("signal_c"), # 策略C 当前建议
                "signal_arch": r.get("signal_arch"),
                "archetype": r.get("archetype"),
                "below_ma150": r.get("below_ma150"),
                "prev_type": prev["type"] if prev else None,   # 上次信号类型
                "prev_date": prev["date"] if prev else None,   # 上次信号时间
            })
    recent.sort(key=lambda x: (x["type"] != "BUY", x["date"]), reverse=False)
    recent.sort(key=lambda x: x["date"], reverse=True)
    return recent


def _recent_wl_changes(n: int = 30) -> list:
    """读取 watchlist 变更审计日志的最近 n 条（newest first）。"""
    f = DOCS_DIR / "watchlist_changelog.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("events", [])[:n]
    except Exception:
        return []


def save_web(rows: list, today: str, recent: list, suspended: list = None):
    data = {}
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    counts = {"buy": 0, "sell_half": 0, "sell_all": 0, "hold": 0, "neutral": 0, "no_data": 0}
    _cmap = {"BUY": "buy", "SELL_HALF": "sell_half", "SELL_ALL": "sell_all",
             "HOLD": "hold", "NEUTRAL": "neutral", "NO_DATA": "no_data"}
    for r in rows:
        counts[_cmap.get(r.get("signal_arch", r.get("signal")), "no_data")] += 1

    payload = {
        "date":    today,
        "updated": _now_cst(),
        "rule":    "按分档差异化：稳定核心=买入持有(MA50>MA150且价格>150MA买/回调≤MA50加仓，不卖，交给周线闸门)；"
                   "成长核心=策略C但清仓用 MA50<MA200；趋势成长/题材=策略C 清仓 MA50<MA150(跌破150MA红灯≥3清，红灯<3扛)。",
        "counts":  counts,
        "recent":  recent,
        "recent_days": RECENT_DAYS,
        "gate_votes": GATE_VOTES,          # 当日市场结构红灯数(0-6),供策略C
        "c_threshold": C_RED_THRESHOLD,    # 红灯≥此值,跌破150MA才清仓
        "suspended": suspended or [],      # 周线破200MA暂停(不给信号)的标的
        "wl_changes": _recent_wl_changes(30),  # watchlist 变更日志(近30条)
        "tickers": rows,
    }

    if today not in data:
        data[today] = {}
    data[today]["updated"]   = _now_cst()
    data[today]["ma_signal"] = payload

    DOCS_DIR.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"💾 ma_signal 已写入 data.json：{today}  BUY={counts['buy']} 减半={counts['sell_half']} "
             f"清仓={counts['sell_all']} 无信号={counts['neutral']}  红灯={GATE_VOTES}")


def push_wechat(recent: list, today: str, counts: dict):
    """当日均线信号摘要推送微信（复用 market_monitor 的通用推送通道）。"""
    try:
        from config import Config
        from market_monitor import push_serverchan, push_wecom, push_wxpusher
    except Exception as e:
        log.warning(f"⚠️ 无法导入推送模块，跳过微信推送：{e}")
        return
    lab = {"BUY": "🟢买入", "SELL_HALF": "🟠减半", "SELL_ALL": "🔴清仓", "HOLD": "🟡持有", "NEUTRAL": "⚪无信号"}
    vtxt = f"{GATE_VOTES}/6" if GATE_VOTES is not None else "取用失败"
    lines = [f"# 🔀 均线信号 {today}",
             f"🚦 市场结构红灯 {vtxt}（策略C：跌破150MA 时红灯≥{C_RED_THRESHOLD} 才清仓，否则持有）",
             f"🟢买入 {counts.get('buy',0)} · 🟠减半 {counts.get('sell_half',0)} · "
             f"🔴清仓 {counts.get('sell_all',0)} · ⚪无信号 {counts.get('neutral',0)}", ""]
    if recent:
        lines.append(f"📢 近 {RECENT_DAYS} 天买卖翻转（{len(recent)}）：")
        for x in recent:
            line = f"- {x['ticker']} {lab.get(x['type'], x['type'])} @{x['date']} [{x.get('tf','')}]"
            if x.get('prev_type') and x.get('prev_date'):
                line += f"（上次 {lab.get(x['prev_type'], x['prev_type'])} @{x['prev_date']}）"
            # 策略C 建议与旧策略不同时,标出(尤其"旧清仓 vs C持有")
            sc = x.get('signal_c')
            if sc and sc != x.get('type'):
                line += f" → 策略C：{lab.get(sc, sc)}"
            lines.append(line)
    else:
        lines.append(f"📢 近 {RECENT_DAYS} 天无新的买卖翻转。")
    lines += ["", "规则：买入=MA20>MA50 且 ST(10,4)↑；减半=死叉；清仓=跌破 MA150。仅供参考，不构成投资建议。"]
    msg, title = "\n".join(lines), f"🔀 均线信号 {today}"
    sent = False
    if getattr(Config, "SERVERCHAN_SENDKEY", ""):
        push_serverchan(title, msg); sent = True
    if getattr(Config, "WECOM_WEBHOOK_URL", ""):
        push_wecom(msg); sent = True
    if getattr(Config, "WXPUSHER_APP_TOKEN", ""):
        push_wxpusher(title, msg); sent = True
    log.info("📲 均线信号已推送微信" if sent else "⏭️ 未配置微信渠道，跳过推送")


def run(dry_run: bool = False):
    global GATE_VOTES
    today = _today_et()
    cache = load_etf_cache()
    tickers = load_tickers()
    log.info("=" * 60)
    log.info(f"🔀 均线×Supertrend 信号  {today}  ({len(tickers)} 只)")
    log.info("=" * 60)

    GATE_VOTES = _compute_gate_votes()      # 当日市场结构红灯数(策略C用),算一次供所有标的
    log.info(f"🚦 市场结构红灯数 = {GATE_VOTES}/6（策略C：跌破150MA 时红灯≥{C_RED_THRESHOLD} 才清仓）")

    hist = load_history()
    rows = []
    for t in tickers:
        res = analyze(t, cache)
        rec = update_history(hist, res)
        res["history"] = list(reversed(rec.get("signals", [])))  # 最新在前
        rows.append(res)
        if res["signal"] == "NO_DATA":
            log.warning(f"  {t:<6} ⚠️ 数据不足")
        else:
            log.info(f"  {t:<6} [{res.get('tf','')}] {res['signal']:<8} ${res['price']}  "
                     f"MA20 {res['ma20']} / MA50 {res['ma50']}  ST{res['st_dir']}")

    # 来源标记（筛选/自选）+ 已暂停清单（周线破150MA）+ 个股分档 + 分档差异化信号
    src_map, suspended, class_map = watchlist_meta()
    for r in rows:
        r["source"] = src_map.get(r.get("ticker"), "manual")
        r["archetype"] = class_map.get(r.get("ticker"))
        if r.get("signal") == "NO_DATA":
            r["signal_arch"], r["rule"] = "NO_DATA", ""
        else:
            r["signal_arch"], r["rule"] = archetype_signal(r, r.get("archetype"), GATE_VOTES)

    rows.sort(key=lambda r: (_SIG_ORDER.get(r["signal"], 9), -(r.get("ma_gap_pct") or -999)))
    recent = build_recent(rows, today)

    if dry_run:
        log.info("🧪 dry-run：不写文件")
        log.info(f"📢 近一周买卖（{len(recent)}）：")
        for x in recent:
            log.info(f"    {x['ticker']:<6} {x['type']}@{x['date']}  [{x['tf']}]")
        return

    save_etf_cache(cache)
    save_history(hist)
    save_web(rows, today, recent, suspended)
    cnt = {"buy": 0, "sell_half": 0, "sell_all": 0, "neutral": 0, "no_data": 0}
    _m = {"BUY": "buy", "SELL_HALF": "sell_half", "SELL_ALL": "sell_all", "NEUTRAL": "neutral", "NO_DATA": "no_data"}
    for r in rows:
        cnt[_m.get(r["signal"], "no_data")] += 1
    push_wechat(recent, today, cnt)
    log.info(f"✅ 完成（近一周买卖 {len(recent)} 只）")


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
