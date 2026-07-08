#!/usr/bin/env python3
"""
signal_advisor.py — 技术信号与期权建议模块 v1.1
盘前（UTC 12:00）+ 盘后（UTC 21:30）自动运行，工作日

覆盖：普通账户持仓 + IRA账户 + Watchlist 26只
输出：信号状态 + 操作建议 + 期权建议 + 企业微信推送 + data.json
"""

import sys
import os
import json
import argparse
import logging
import requests
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ── 日志 ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── 环境变量（兼容两种命名约定）────────────────────────────────────────────
WXPUSHER_TOKEN = (
    os.environ.get("WXPUSHER_APP_TOKEN") or os.environ.get("WXPUSHER_TOKEN", "")
)
WXPUSHER_UIDS = [
    u.strip() for u in os.environ.get("WXPUSHER_UIDS", "").split(",") if u.strip()
]
SERVERCHAN_KEY = (
    os.environ.get("SERVERCHAN_SENDKEY") or os.environ.get("SERVERCHAN_KEY", "")
)

# ── 路径 ────────────────────────────────────────────────────────────────────
DOCS_DIR  = Path(__file__).parent / "docs"
DATA_FILE = DOCS_DIR / "data.json"

# ═══════════════════════════════════════════════════════════════════════════
# 持仓数据（手动维护，成本为总成本非单价）
# ═══════════════════════════════════════════════════════════════════════════

REGULAR_HOLDINGS = {
    "ADI":  {"qty": 51,  "cost_basis": 18899.57},
    "ALB":  {"qty": 101, "cost_basis": 20012.65},
    "ASML": {"qty": 13,  "cost_basis": 24450.14},
    "COHR": {"qty": 92,  "cost_basis": 24670.89},
    "ETN":  {"qty": 51,  "cost_basis": 20829.68},
    "GEV":  {"qty": 54,  "cost_basis": 48935.44},
    "GOOG": {"qty": 51,  "cost_basis": 16698.99},
    "MPWR": {"qty": 24,  "cost_basis": 27845.59},
    "NVDA": {"qty": 190, "cost_basis": 35526.08},
    "VRT":  {"qty": 161, "cost_basis": 36057.36},
    # 新增持仓（待补全 qty / cost_basis）
    "CIEN": {"qty": 0,   "cost_basis": 0},
    "TXN":  {"qty": 0,   "cost_basis": 0},
    "ONTO": {"qty": 0,   "cost_basis": 0},
    "LITE": {"qty": 0,   "cost_basis": 0},
    "PWR":  {"qty": 0,   "cost_basis": 0},
    "GLW":  {"qty": 0,   "cost_basis": 0},
    "DRAM": {"qty": 0,   "cost_basis": 0},
    "INTC": {"qty": 0,   "cost_basis": 0},
    "MU":   {"qty": 0,   "cost_basis": 0},
    "SNDK": {"qty": 0,   "cost_basis": 0},
    "TSEM": {"qty": 0,   "cost_basis": 0},
}

IRA_HOLDINGS = {
    # "TICKER": {"qty": N, "cost_basis": XXXXX.XX},
}

IRA_OPTIONS = {
    # "TICKER": {"type": "call", "strike": 450, "expiry": "2027-01-16", "qty": 2, "cost_basis": 3200},
}

# 宏观/ETF 观测（不计算期权建议）
MACRO_WATCH = [
    "GLD", "QQQ", "SLV", "ETHA", "XBI", "COIN", "FPX", "FLJH",
]

# 组一：高优先级 Watchlist（每次必跑）
PRIORITY_WATCHLIST = [
    # 存储/内存
    "MRVL", "NVMI", "WDC", "STX",
    # 半导体设备/ETF
    "AEHR", "KLAC", "TSM", "SMH",
    # 大型半导体/科技
    "ARM", "AVGO", "AMD",
    # 光纤/网络
    "ANET",
    # 近期信号活跃
    "NBIS", "PLTR", "GS", "CEG", "FTAI",
]

# 组二：扩展 Watchlist（盘后单独跑）
EXTENDED_WATCHLIST = [
    "BDRY", "COPX", "FRO", "HEWJ", "MP", "NEE", "VST", "MSFT",
    "LNG", "XOM", "DHT", "TNK", "DUK", "RTX", "AVAV",
    "SE", "DOCN", "EQIX", "RKLB", "SPCX",
    "XMMO", "IWM", "BNO", "UTES", "REMX", "GDX", "USD",
]


# ═══════════════════════════════════════════════════════════════════════════
# 层一：技术指标计算
# ═══════════════════════════════════════════════════════════════════════════

def get_ohlcv(ticker: str, period: str = "6mo") -> pd.DataFrame:
    try:
        df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        return df if not df.empty else pd.DataFrame()
    except Exception as e:
        log.debug(f"  {ticker}: OHLCV 获取失败 {e}")
        return pd.DataFrame()


def calc_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> dict | None:
    """
    Supertrend(10, 3) — NaN 安全版
    返回: direction(UP/DOWN), value, bars_since_flip, near_flip
    """
    try:
        high  = df["High"].values.astype(float)
        low   = df["Low"].values.astype(float)
        close = df["Close"].values.astype(float)
        n = len(close)
        if n < period * 2 + 5:
            return None

        tr = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i]  - close[i - 1]),
            )

        # Wilder ATR
        atr = np.full(n, np.nan)
        atr[period] = tr[1:period + 1].mean()
        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

        hl2     = (high + low) / 2.0
        up_band = hl2 + multiplier * atr
        dn_band = hl2 - multiplier * atr

        final_up = np.full(n, np.nan)
        final_dn = np.full(n, np.nan)
        trend    = np.zeros(n, dtype=int)  # 0=warmup, 1=bullish, -1=bearish

        for i in range(1, n):
            if np.isnan(up_band[i]):
                continue

            fu_prev = final_up[i - 1]
            fd_prev = final_dn[i - 1]

            # Seed at first valid ATR bar
            final_up[i] = (
                up_band[i] if (np.isnan(fu_prev) or up_band[i] < fu_prev or close[i - 1] > fu_prev)
                else fu_prev
            )
            final_dn[i] = (
                dn_band[i] if (np.isnan(fd_prev) or dn_band[i] > fd_prev or close[i - 1] < fd_prev)
                else fd_prev
            )

            prev = trend[i - 1]
            if prev == 0:
                trend[i] = 1 if close[i] > final_dn[i] else -1
            elif prev == 1:
                trend[i] = -1 if close[i] < final_dn[i] else 1
            else:
                trend[i] =  1 if close[i] > final_up[i] else -1

        if trend[-1] == 0:
            return None

        direction  = "UP" if trend[-1] == 1 else "DOWN"
        line_raw   = final_dn[-1] if trend[-1] == 1 else final_up[-1]
        line_value = None if np.isnan(line_raw) else round(float(line_raw), 2)

        # Count consecutive bars in current direction
        bars_since_flip = 0
        for i in range(n - 2, -1, -1):
            if trend[i] == 0:
                continue
            if trend[i] == trend[-1]:
                bars_since_flip += 1
            else:
                break

        # near_flip: price within 1% of Supertrend line
        near_flip = False
        if line_value is not None:
            near_flip = bool(abs(float(close[-1]) - line_value) / float(close[-1]) <= 0.01)

        return {
            "direction":      direction,
            "value":          line_value,
            "bars_since_flip": bars_since_flip,
            "near_flip":      near_flip,
        }
    except Exception as e:
        log.debug(f"calc_supertrend error: {e}")
        return None


def calc_sqzmom(df: pd.DataFrame, bb_period: int = 20, bb_mult: float = 2.0,
                kc_period: int = 20, kc_mult: float = 1.5) -> dict | None:
    """
    SQZ Momentum (LazyBear: BB 20/2 inside KC 20/1.5)
    返回: sqz_state(SQUEEZE/RELEASED/NO_SQUEEZE), momentum_val, momentum_dir(INCREASING/DECREASING/FLIPPING)
    """
    try:
        close = df["Close"].values.astype(float)
        high  = df["High"].values.astype(float)
        low   = df["Low"].values.astype(float)
        n = len(close)
        if n < bb_period + 10:
            return None

        cs  = pd.Series(close)
        ma  = cs.rolling(bb_period).mean()
        std = cs.rolling(bb_period).std()
        bb_up = (ma + bb_mult * std).values
        bb_dn = (ma - bb_mult * std).values

        tr = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i]  - close[i - 1]),
            )
        atr_s = pd.Series(tr).rolling(kc_period).mean()
        kc_up = (ma + kc_mult * atr_s).values
        kc_dn = (ma - kc_mult * atr_s).values

        sqz_now  = bool(bb_up[-1] < kc_up[-1] and bb_dn[-1] > kc_dn[-1])
        sqz_prev = bool(bb_up[-2] < kc_up[-2] and bb_dn[-2] > kc_dn[-2]) if n >= 2 else sqz_now

        if sqz_now:
            sqz_state = "SQUEEZE"
        elif not sqz_now and sqz_prev:
            sqz_state = "RELEASED"
        else:
            sqz_state = "NO_SQUEEZE"

        # Momentum via linear regression on delta
        highest = pd.Series(high).rolling(bb_period).max().values
        lowest  = pd.Series(low).rolling(bb_period).min().values
        delta   = close - (highest + lowest) / 2.0 - ma.values

        x = np.arange(bb_period, dtype=float)

        def _slope(arr_slice):
            if len(arr_slice) < bb_period or np.any(np.isnan(arr_slice)):
                return None
            return float(np.polyfit(x, arr_slice, 1)[0])

        mom_now  = _slope(delta[-bb_period:])
        mom_prev = _slope(delta[-(bb_period + 1):-1]) if n > bb_period else mom_now

        if mom_now is None:
            return None

        if mom_prev is None:
            mom_prev = mom_now

        if (mom_now > 0) != (mom_prev > 0):
            momentum_dir = "FLIPPING"
        elif abs(mom_now) >= abs(mom_prev):
            momentum_dir = "INCREASING"
        else:
            momentum_dir = "DECREASING"

        return {
            "sqz_state":    sqz_state,
            "momentum_val": round(mom_now, 4),
            "momentum_dir": momentum_dir,
        }
    except Exception as e:
        log.debug(f"calc_sqzmom error: {e}")
        return None


def calc_adx(df: pd.DataFrame, period: int = 14) -> dict | None:
    """
    ADX + DI± (Wilder smoothing)
    返回: adx, di_pos, di_neg, trend_strength(STRONG/MODERATE/WEAK)
    """
    try:
        high  = df["High"].values.astype(float)
        low   = df["Low"].values.astype(float)
        close = df["Close"].values.astype(float)
        n = len(close)
        if n < period * 3:
            return None

        tr  = np.zeros(n)
        pdm = np.zeros(n)
        mdm = np.zeros(n)
        for i in range(1, n):
            h_diff = high[i] - high[i - 1]
            l_diff = low[i - 1] - low[i]
            tr[i]  = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
            pdm[i] = h_diff if h_diff > l_diff and h_diff > 0 else 0
            mdm[i] = l_diff if l_diff > h_diff and l_diff > 0 else 0

        def _wilder(arr, p):
            out = np.zeros(n)
            out[p] = arr[1:p + 1].sum()
            for i in range(p + 1, n):
                out[i] = out[i - 1] - out[i - 1] / p + arr[i]
            return out

        atr_w = _wilder(tr,  period)
        pDM_w = _wilder(pdm, period)
        mDM_w = _wilder(mdm, period)

        with np.errstate(divide="ignore", invalid="ignore"):
            di_p = np.where(atr_w > 0, pDM_w / atr_w * 100, 0.0)
            di_m = np.where(atr_w > 0, mDM_w / atr_w * 100, 0.0)
            dx   = np.where((di_p + di_m) > 0,
                            np.abs(di_p - di_m) / (di_p + di_m) * 100, 0.0)

        adx_arr = _wilder(dx, period)
        adx_val = round(float(adx_arr[-1]) / period, 1)
        dip_val = round(float(di_p[-1]), 1)
        dim_val = round(float(di_m[-1]), 1)

        strength = "STRONG" if adx_val >= 30 else ("MODERATE" if adx_val >= 20 else "WEAK")

        return {
            "adx":           adx_val,
            "di_pos":        dip_val,
            "di_neg":        dim_val,
            "trend_strength": strength,
        }
    except Exception as e:
        log.debug(f"calc_adx error: {e}")
        return None


def calc_mas(df: pd.DataFrame) -> dict | None:
    """MA 20/50/120 + alignment"""
    try:
        close = df["Close"].values.astype(float)
        n = len(close)
        ma20  = round(float(np.mean(close[-20:])),  2) if n >= 20  else None
        ma50  = round(float(np.mean(close[-50:])),  2) if n >= 50  else None
        ma120 = round(float(np.mean(close[-120:])), 2) if n >= 120 else None
        price = close[-1]

        vs_ma20 = ("ABOVE" if price > ma20 else "BELOW") if ma20 is not None else None

        if ma20 and ma50 and ma120:
            if ma20 > ma50 > ma120:
                alignment = "BULLISH"
            elif ma20 < ma50 < ma120:
                alignment = "BEARISH"
            else:
                alignment = "MIXED"
        else:
            alignment = "MIXED"

        return {
            "ma20":         ma20,
            "ma50":         ma50,
            "ma120":        ma120,
            "price_vs_ma20": vs_ma20,
            "ma_alignment": alignment,
        }
    except Exception as e:
        log.debug(f"calc_mas error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# 层二：信号判断
# ═══════════════════════════════════════════════════════════════════════════

def get_signal(st: dict, sqz: dict, adx: dict, ma: dict) -> str:
    """四项指标 → 综合信号"""
    if not st or not adx:
        return "⚪ 数据不足"

    st_dir   = st.get("direction", "")
    st_flip  = st.get("bars_since_flip", 99)
    st_near  = st.get("near_flip", False)
    sqz_st   = sqz.get("sqz_state", "") if sqz else ""
    sqz_mom  = sqz.get("momentum_val", 0) if sqz else 0
    sqz_dir  = sqz.get("momentum_dir", "") if sqz else ""
    adx_val  = adx.get("adx", 0)
    dip      = adx.get("di_pos", 0)
    dim      = adx.get("di_neg", 0)

    # ⚡ 突破关注：价格接近 ST 线 ≤1% 且 SQZ 处于 SQUEEZE 状态
    if st_near and sqz_st == "SQUEEZE":
        return "⚡ 突破关注"

    # 💚 强势上涨：ST 持续 UP + SQZ 正增强 + ADX 强 + DI+ 领先
    if (st_dir == "UP" and st_flip > 3
            and sqz_mom > 0 and sqz_dir == "INCREASING"
            and adx_val >= 30 and dip > dim):
        return "💚 强势上涨"

    # 🟢 趋势初确认：ST 刚翻 UP（≤3根）+ DI+ 领先
    if st_dir == "UP" and st_flip <= 3 and dip > dim:
        return "🟢 趋势初确认"

    # 🔴 强烈看跌：ST DOWN + SQZ 负增强 + ADX≥25 + DI- 领先
    if (st_dir == "DOWN"
            and sqz_mom < 0 and sqz_dir == "INCREASING"
            and adx_val >= 25 and dim > dip):
        return "🔴 强烈看跌"

    # 🟠 走弱观察：ST DOWN + SQZ 负或减弱
    if st_dir == "DOWN" and (sqz_mom < 0 or sqz_dir in ("DECREASING", "INCREASING")):
        return "🟠 走弱观察"

    # 🟡 震荡整理（默认）
    return "🟡 震荡整理"


def generate_action(signal: str, holding: dict | None = None) -> str:
    """信号 + 持仓状态 → 操作建议"""
    unr_pct = holding.get("_unr_pct") if holding else None

    if signal == "💚 强势上涨":
        return "持仓，可考虑中期期权补仓"
    elif signal == "🟢 趋势初确认":
        return "可加仓，LEAP 期权时机"
    elif signal == "⚡ 突破关注":
        return "等待再确认 1-2 根 K 线后操作"
    elif signal == "🟡 震荡整理":
        return "等待突破方向确认，暂不操作"
    elif signal == "🟠 走弱观察":
        if unr_pct is not None and unr_pct < -15:
            return f"浮亏 {unr_pct:+.1f}%，检查止损位"
        return "不加仓，关注走弱趋势"
    elif signal == "🔴 强烈看跌":
        if unr_pct is not None and unr_pct > 0:
            return f"浮盈 {unr_pct:+.1f}%，考虑减仓锁定利润"
        return "不操作，等待信号改善"
    return "持续观察"


# ═══════════════════════════════════════════════════════════════════════════
# 层三：期权建议
# ═══════════════════════════════════════════════════════════════════════════

def _next_jan_expiry(months_min: int = 12, months_max: int = 18) -> str:
    """最近满足 12-18 个月的标准 1 月第三个周五到期日"""
    today = date.today()
    for year in [today.year + 1, today.year + 2]:
        jan1 = date(year, 1, 1)
        days_to_fri = (4 - jan1.weekday()) % 7
        first_fri   = date(year, 1, 1 + days_to_fri)
        third_fri   = date(year, 1, first_fri.day + 14)
        delta_months = (third_fri.year - today.year) * 12 + third_fri.month - today.month
        if months_min <= delta_months <= months_max:
            return third_fri.strftime("%Y-%m-%d")
    return f"{today.year + 1}-01-17"


def _next_mid_expiry(months_min: int = 3, months_max: int = 6) -> str:
    """最近满足 3-6 个月的月度第三个周五到期日"""
    today = date.today()
    for m_offset in range(months_min, months_max + 1):
        year  = today.year + (today.month + m_offset - 1) // 12
        month = (today.month + m_offset - 1) % 12 + 1
        d1 = date(year, month, 1)
        days_to_fri = (4 - d1.weekday()) % 7
        first_fri   = date(year, month, 1 + days_to_fri)
        third_fri   = date(year, month, first_fri.day + 14)
        if third_fri > today:
            return third_fri.strftime("%Y-%m-%d")
    return ""


def get_option_rec(st: dict, sqz: dict, adx: dict, holding: dict | None = None,
                   price: float = 0.0) -> dict:
    """指标 → 期权建议（LEAP / MID_TERM / NO_ACTION）"""
    if not st or not adx:
        return {"recommendation": "NO_ACTION", "rationale": "数据不足"}

    st_dir  = st.get("direction", "")
    st_flip = st.get("bars_since_flip", 99)
    sqz_mom = sqz.get("momentum_val", 0) if sqz else 0
    sqz_dir = sqz.get("momentum_dir", "") if sqz else ""
    adx_val = adx.get("adx", 0)
    dip     = adx.get("di_pos", 0)
    dim     = adx.get("di_neg", 0)
    ts      = adx.get("trend_strength", "WEAK")

    # NO_ACTION：ST DOWN + SQZ 负增强
    if st_dir == "DOWN" and sqz_mom < 0 and sqz_dir == "INCREASING":
        neg_tickers = ""
        return {
            "recommendation": "NO_ACTION",
            "rationale": f"ST↓ SQZ负增强 ADX{adx_val} — 信号不支持",
        }

    # LEAP 条件：ST 刚翻 UP (≤3根), 或 SQZ FLIPPING, 或价格 >500（长期结构性）
    is_leap = (
        (st_dir == "UP" and st_flip <= 3)
        or sqz_dir == "FLIPPING"
        or price > 500
    )

    # MID_TERM 条件：ST UP 持续 (>3根) + SQZ 正增强 + ADX≥30
    is_mid = (
        st_dir == "UP" and st_flip > 3
        and sqz_mom > 0 and sqz_dir == "INCREASING"
        and adx_val >= 30
    )

    # 两者都不满足 → NO_ACTION
    if not is_leap and not is_mid:
        return {
            "recommendation": "NO_ACTION",
            "rationale": f"ST{'+' if st_dir=='UP' else '-'}({st_flip}根) ADX{adx_val} — 等待信号确认",
        }

    if is_leap and not is_mid:
        rec     = "LEAP"
        expiry  = _next_jan_expiry(12, 18)
        delta_s = "0.70-0.80"
        reasons = []
        if st_dir == "UP" and st_flip <= 3:
            reasons.append(f"ST刚翻UP {st_flip}根")
        if sqz_dir == "FLIPPING":
            reasons.append("SQZ动能转向")
        if price > 500:
            reasons.append("高价股长期结构性多头")
        reasons.append(f"ADX{adx_val} {'趋势初建' if ts=='MODERATE' else ts}")
        rationale = "，".join(reasons)
    else:
        rec     = "MID_TERM"
        expiry  = _next_mid_expiry(3, 6)
        delta_s = "0.50-0.65"
        rationale = f"ST持续UP {st_flip}根，SQZ正增强，ADX{adx_val}≥30 — 中期势头确立"

    result: dict = {
        "recommendation": rec,
        "rationale":      rationale,
        "suggested_expiry": expiry,
        "suggested_delta":  delta_s,
        "account":        "IRA优先",
    }

    if holding:
        cost = holding.get("cost_basis", 0)
        limit_pct = 0.20 if rec == "LEAP" else 0.15
        result["max_position_cost"] = round(cost * limit_pct, 2)

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 单股分析
# ═══════════════════════════════════════════════════════════════════════════

def analyze_ticker(ticker: str, holding: dict | None = None) -> dict:
    df = get_ohlcv(ticker, period="6mo")
    if df.empty or len(df) < 30:
        return {"ticker": ticker, "error": "数据不足"}

    price    = round(float(df["Close"].iloc[-1]), 2)
    prev_c   = float(df["Close"].iloc[-2]) if len(df) >= 2 else price
    day_chg  = round((price - prev_c) / prev_c * 100, 2)

    st  = calc_supertrend(df)
    sqz = calc_sqzmom(df)
    adx = calc_adx(df)
    ma  = calc_mas(df)

    signal = get_signal(st, sqz, adx, ma)

    # 浮盈计算
    unr_pct = None
    if holding:
        cost = holding.get("cost_basis", 0)
        qty  = holding.get("qty", 0)
        if cost > 0:
            unr_pct = round((price * qty - cost) / cost * 100, 1)
        holding = dict(holding)
        holding["_unr_pct"] = unr_pct

    action = generate_action(signal, holding)
    opt    = get_option_rec(st, sqz, adx, holding, price) if holding is not None or price > 100 else None

    return {
        "ticker":             ticker,
        "price":              price,
        "day_chg":            day_chg,
        "supertrend":         st,
        "sqzmom":             sqz,
        "adx":                adx,
        "ma":                 ma,
        "signal":             signal,
        "action":             action,
        "option_rec":         opt,
        "unrealized_pnl_pct": unr_pct,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 层四：推送消息构建
# ═══════════════════════════════════════════════════════════════════════════

SIGNAL_ORDER = [
    "💚 强势上涨",
    "🟢 趋势初确认",
    "⚡ 突破关注",
    "🟡 震荡整理",
    "🟠 走弱观察",
    "🔴 强烈看跌",
    "⚪ 数据不足",
]


def _ticker_detail(r: dict) -> str:
    """单行：TICKER $price ST↑/↓ SQZ... ADX... DI±"""
    st  = r.get("supertrend") or {}
    sqz = r.get("sqzmom")    or {}
    adx = r.get("adx")       or {}

    price    = r.get("price", 0)
    st_dir   = st.get("direction", "?")
    st_flip  = st.get("bars_since_flip", 0)
    sqz_st   = sqz.get("sqz_state", "")
    sqz_mdir = sqz.get("momentum_dir", "")
    adx_v    = adx.get("adx", "?")
    dip      = adx.get("di_pos", "?")
    dim      = adx.get("di_neg", "?")
    unr      = r.get("unrealized_pnl_pct")

    arrow = "↑" if st_dir == "UP" else "↓"
    flip_s = f"({st_flip}根)" if st_flip <= 5 else ""

    sqz_map = {"SQUEEZE": "SQZ红", "RELEASED": "SQZ绿出", "NO_SQUEEZE": "SQZ绿"}
    sqz_s   = sqz_map.get(sqz_st, "")
    mom_map = {"INCREASING": "↑", "DECREASING": "↓", "FLIPPING": "⇄"}
    sqz_s  += mom_map.get(sqz_mdir, "")

    unr_s = f"  [{unr:+.1f}%]" if unr is not None else ""
    return f"  {r['ticker']:<5} ${price:<9.2f} ST{arrow}{flip_s} {sqz_s} ADX{adx_v} DI+{dip}/DI-{dim}{unr_s}"


def build_message(session: str, regular: list, ira: list, watchlist: list) -> str:
    tz_cst   = timezone(timedelta(hours=8))
    date_str = datetime.now(tz_cst).strftime("%Y-%m-%d")
    sess_cn  = "盘前" if session == "pre" else "盘后"

    lines = [f"📊 技术信号日报 {date_str} {sess_cn}", ""]

    # ── 普通账户持仓信号 ─────────────────────────────────────────────────
    if regular:
        lines.append("━━━ 🏦 普通账户持仓信号 ━━━")
        by_sig: dict = {}
        for r in regular:
            if "error" in r:
                continue
            by_sig.setdefault(r.get("signal", "⚪ 数据不足"), []).append(r)

        for sig in SIGNAL_ORDER:
            items = by_sig.get(sig)
            if not items:
                continue
            lines.append(f"\n{sig}")
            for r in items:
                lines.append(_ticker_detail(r))
            # Action summary for the group
            actions = {r.get("action", "") for r in items if r.get("action")}
            for a in actions:
                lines.append(f"  → {a}")

    # ── IRA 账户持仓 ──────────────────────────────────────────────────────
    if ira:
        lines.append("\n━━━ 🏦 IRA 账户持仓信号 ━━━")
        by_sig_ira: dict = {}
        for r in ira:
            if "error" in r:
                continue
            by_sig_ira.setdefault(r.get("signal", "⚪ 数据不足"), []).append(r)
        for sig in SIGNAL_ORDER:
            items = by_sig_ira.get(sig)
            if not items:
                continue
            lines.append(f"\n{sig}")
            for r in items:
                lines.append(_ticker_detail(r))

    # ── 期权建议 ──────────────────────────────────────────────────────────
    all_holdings = [r for r in regular + ira if "error" not in r]
    leap_list  = [r for r in all_holdings if r.get("option_rec", {}).get("recommendation") == "LEAP"]
    mid_list   = [r for r in all_holdings if r.get("option_rec", {}).get("recommendation") == "MID_TERM"]
    wait_list  = [r for r in all_holdings if r.get("option_rec", {}).get("recommendation") == "NO_ACTION"
                  and r.get("signal") not in ("🔴 强烈看跌",)]
    no_list    = [r for r in all_holdings if r.get("option_rec", {}).get("recommendation") == "NO_ACTION"
                  and r.get("signal") == "🔴 强烈看跌"]

    if leap_list or mid_list:
        lines.append("\n━━━ 📋 期权建议（IRA 优先）━━━")

    if leap_list:
        lines.append("\nLEAP 时机（12-18个月 ITM call）：")
        for r in leap_list:
            opt = r.get("option_rec", {})
            expiry    = opt.get("suggested_expiry", "")
            delta_s   = opt.get("suggested_delta", "")
            max_cost  = opt.get("max_position_cost")
            rationale = opt.get("rationale", "")[:60]
            lines.append(f"  ✅ {r['ticker']:<5} — {rationale}")
            cost_s = f"，上限 ${max_cost:,.0f}" if max_cost else ""
            lines.append(f"     建议 {expiry} Delta {delta_s}{cost_s}")

    if mid_list:
        lines.append("\n中期期权（3-6个月）：")
        for r in mid_list:
            opt = r.get("option_rec", {})
            expiry   = opt.get("suggested_expiry", "")
            delta_s  = opt.get("suggested_delta", "")
            max_cost = opt.get("max_position_cost")
            lines.append(f"  ✅ {r['ticker']:<5} — {opt.get('rationale','')[:60]}")
            cost_s = f"，上限 ${max_cost:,.0f}" if max_cost else ""
            lines.append(f"     建议 {expiry} Delta {delta_s}{cost_s}")

    if wait_list:
        lines.append("\n等待信号：")
        for r in wait_list:
            opt = r.get("option_rec", {})
            lines.append(f"  ⏳ {r['ticker']:<5} — {opt.get('rationale','')[:50]}")

    if no_list:
        tickers_str = " / ".join(r["ticker"] for r in no_list)
        lines.append(f"\n不建议：")
        lines.append(f"  ❌ {tickers_str} — 信号不支持")

    # ── Watchlist 扫描 ────────────────────────────────────────────────────
    if watchlist:
        lines.append("\n━━━ 👀 Watchlist 信号扫描 ━━━")

        bull    = [r for r in watchlist if r.get("signal") in ("💚 强势上涨", "🟢 趋势初确认")]
        side    = [r for r in watchlist if r.get("signal") in ("🟡 震荡整理", "⚡ 突破关注")]
        weak    = [r for r in watchlist if r.get("signal") in ("🟠 走弱观察", "🔴 强烈看跌")]

        if bull:
            lines.append("\n强势（可关注建仓）：")
            lines.append("  " + "  ".join(
                f"{r['ticker']} {r['signal'].split()[0]}" for r in bull
            ))
        if side:
            lines.append("\n震荡等待：")
            lines.append("  " + "  ".join(
                f"{r['ticker']} {r['signal'].split()[0]}" for r in side
            ))
        if weak:
            lines.append("\n走弱回避：")
            lines.append("  " + "  ".join(
                f"{r['ticker']} {r['signal'].split()[0]}" for r in weak
            ))

    lines += ["", "⚠️ 仅供参考，不构成投资建议"]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# data.json 写入
# ═══════════════════════════════════════════════════════════════════════════

def _sanitize(obj):
    if isinstance(obj, bool):          # must be before int/np.integer (bool is subclass of int)
        return obj
    if isinstance(obj, float):
        return None if (obj != obj or obj == float("inf") or obj == float("-inf")) else obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.bool_):      # numpy boolean
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    return obj


def save_signal_data(session: str, group: str,
                     regular: list, ira: list,
                     macro: list, priority: list, extended: list):
    tz_cst = timezone(timedelta(hours=8))
    # 用美东时间（ET）确定交易日期，避免 UTC 21:30 盘后运行跨到 CST 次日
    try:
        import pytz
        _et = pytz.timezone("America/New_York")
        today = datetime.now(_et).strftime("%Y-%m-%d")
    except Exception:
        today = datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")

    def _to_dict(results):
        out = {}
        for r in results:
            if "error" in r:
                continue
            t = r["ticker"]
            out[t] = _sanitize({
                "price":        r.get("price"),
                "day_chg":      r.get("day_chg"),
                "supertrend":   r.get("supertrend"),
                "sqzmom":       r.get("sqzmom"),
                "adx":          r.get("adx"),
                "ma":           r.get("ma"),
                "signal":       r.get("signal"),
                "action":       r.get("action"),
                "option_rec":   r.get("option_rec"),
                "unrealized_pnl_pct": r.get("unrealized_pnl_pct"),
            })
        return out

    # 加载已有数据（extended 组需要 merge，不覆盖 priority 组结果）
    data = {}
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing = data.get(today, {}).get("signal_advisor", {})

    payload: dict = {
        "date":    today,
        "session": "pre_market" if session == "pre" else "post_market",
        # 保留已有字段，本次覆盖对应分组
        "regular_account":    existing.get("regular_account", {}),
        "ira_account":        existing.get("ira_account", {}),
        "macro_watch":        existing.get("macro_watch", {}),
        "priority_watchlist": existing.get("priority_watchlist", {}),
        "extended_watchlist": existing.get("extended_watchlist", {}),
        "option_recommendations": existing.get("option_recommendations", []),
    }

    if group in ("priority", "all"):
        payload["regular_account"]    = _to_dict(regular)
        payload["ira_account"]        = _to_dict(ira)
        payload["macro_watch"]        = _to_dict(macro)
        payload["priority_watchlist"] = _to_dict(priority)
        payload["option_recommendations"] = _sanitize([
            {"ticker": r["ticker"], **(r.get("option_rec") or {})}
            for r in regular + ira
            if (r.get("option_rec") or {}).get("recommendation") in ("LEAP", "MID_TERM")
        ])

    if group in ("extended", "all"):
        payload["extended_watchlist"] = _to_dict(extended)

    # 合并 watchlist 供前端使用（向后兼容）
    payload["watchlist"] = {
        **payload.get("macro_watch", {}),
        **payload.get("priority_watchlist", {}),
        **payload.get("extended_watchlist", {}),
    }

    if today not in data:
        data[today] = {}
    data[today]["updated"]        = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M CST")
    data[today]["signal_advisor"] = _sanitize(payload)

    DOCS_DIR.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"💾 signal_advisor [{group}] 已写入 data.json: {today}")


# ═══════════════════════════════════════════════════════════════════════════
# 推送
# ═══════════════════════════════════════════════════════════════════════════

def _push_wxpusher(content: str, summary: str):
    if not WXPUSHER_TOKEN or not WXPUSHER_UIDS:
        log.info("⚠️ WxPusher 未配置，跳过推送")
        return
    try:
        resp = requests.post(
            "https://wxpusher.zjiecode.com/api/send/message",
            json={
                "appToken":    WXPUSHER_TOKEN,
                "content":     content,
                "summary":     summary,
                "contentType": 1,
                "uids":        WXPUSHER_UIDS,
            },
            timeout=15,
        )
        resp.raise_for_status()
        log.info("📨 WxPusher 推送成功")
    except Exception as e:
        log.warning(f"WxPusher 推送失败: {e}")


def _push_serverchan(content: str, title: str):
    if not SERVERCHAN_KEY:
        return
    try:
        requests.post(
            f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
            data={"title": title, "desp": content},
            timeout=15,
        )
        log.info("📨 Server酱 推送成功")
    except Exception as e:
        log.warning(f"Server酱 推送失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════

def _scan(tickers: list, holding_map: dict, label: str) -> list:
    results = []
    log.info(f"\n▶ {label} ({len(tickers)} 只) ...")
    for ticker in tickers:
        h = holding_map.get(ticker)
        r = analyze_ticker(ticker, h)
        results.append(r)
        if "error" not in r:
            log.info(f"  {ticker:<6} {r['signal']}  ${r['price']}")
        else:
            log.warning(f"  {ticker:<6} ⚠️ {r['error']}")
    return results


def run_advisor(session: str = "post", group: str = "all", dry_run: bool = False):
    try:
        import pytz
        et_tz = pytz.timezone("America/New_York")
    except ImportError:
        et_tz = timezone(timedelta(hours=-4))

    now_et = datetime.now(et_tz) if hasattr(et_tz, "localize") else datetime.now(et_tz)
    if now_et.weekday() >= 5:
        log.info(f"⏭️ 周末跳过 ({now_et.strftime('%Y-%m-%d %A')})")
        return

    sess_cn = "盘前" if session == "pre" else "盘后"
    log.info("=" * 60)
    log.info(f"📊 Signal Advisor v2.0  {now_et.strftime('%Y-%m-%d')}  {sess_cn}  [{group}]")
    log.info("=" * 60)

    holding_tickers = set(REGULAR_HOLDINGS) | set(IRA_HOLDINGS)

    regular, ira, macro, priority, extended = [], [], [], [], []

    if group in ("priority", "all"):
        regular  = _scan(list(REGULAR_HOLDINGS), REGULAR_HOLDINGS, "普通账户持仓")
        ira      = _scan(list(IRA_HOLDINGS),     IRA_HOLDINGS,     "IRA 账户持仓") if IRA_HOLDINGS else []
        macro    = _scan([t for t in MACRO_WATCH        if t not in holding_tickers], {}, "宏观/ETF 观测")
        priority = _scan([t for t in PRIORITY_WATCHLIST if t not in holding_tickers], {}, "优先 Watchlist")

    if group in ("extended", "all"):
        extended = _scan([t for t in EXTENDED_WATCHLIST if t not in holding_tickers], {}, "扩展 Watchlist")

    if not dry_run:
        save_signal_data(session, group, regular, ira, macro, priority, extended)

    # 推送（priority 组或 all 组才推送持仓信号）
    all_wl = macro + priority + extended
    msg   = build_message(session, regular, ira, all_wl)
    title = f"📊 技术信号{sess_cn}[{group}] {now_et.strftime('%m/%d')}"

    log.info("\n" + "─" * 60)
    log.info(msg[:600])
    log.info("─" * 60)

    if not dry_run:
        # 微信推送已停用（微信只推送新闻简报），信号仅保存到网页
        log.info("⏭️ 微信推送已停用（微信只推送新闻简报），信号仅保存到网页")

    total = regular + ira + macro + priority + extended
    ok  = sum(1 for r in total if "error" not in r)
    err = len(total) - ok
    log.info(f"\n✅ 完成：{ok} 只成功，{err} 只失败")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="技术信号与期权建议模块 v2.0")
    parser.add_argument("--session",  choices=["pre", "post"], default="post")
    parser.add_argument("--group",    choices=["priority", "extended", "all"], default="all")
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()
    run_advisor(args.session, args.group, args.dry_run)
