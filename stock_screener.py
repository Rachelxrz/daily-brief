"""
stock_screener.py  v3.0
-----------------------
两个独立模块，每日自动运行：

模块 A — 板块轮动强势股筛选
  · 获取 7 个板块 ETF 今日表现，选出领涨板块
  · 对领涨板块内候选股做 screener 过滤（均线/EPS/市值/成交量）
  · 每个板块输出 TOP 3

模块 B — 自选股技术分析（Watchlist）★ 新增
  · 对固定 26 只自选股每日计算：
    1. 是否在 MA20 / MA50 上方
    2. 是否连续3日收盘价递增（up streak）
    3. 是否连续3日收盘价递减（down streak）
  · 结果推送微信 + 写入 JSON 供网页展示

数据源: yfinance (Yahoo Finance) — 免费无需 API Key
运行时间: 每个交易日三次 (UTC 18:00 / 19:30 / 20:30)
"""

import yfinance as yf
import json
import os
import requests
from datetime import datetime
from pathlib import Path
import pytz
import numpy as np
import pandas as pd

DOCS_DIR = Path(__file__).resolve().parent / "docs"

# ═══════════════════════════════════════════════
# ★ 模块 B 配置 — 自选股 Watchlist
# ═══════════════════════════════════════════════

WATCHLIST = [
    "ALB", "ANET", "AVGO", "BDRY", "CEG",  "CIEN",
    "COHR","COPX", "ETHA", "FRO",  "GEV",  "GS",
    "HEWJ","LITE", "MP",   "NEE",  "NVDA", "PLTR",
    "PWR", "VRT",  "VST",  "MPWR", "ADI",  "GOOG",
    "NBIS","MPC",
]


# ═══════════════════════════════════════════════
# 模块 A 配置 — 资金流入板块 强势股筛选（v4.0）
# ═══════════════════════════════════════════════
#
# 【新规则】从 sector_board 的「资金流入板块」中，每个板块取前 3 名：
#   1. 市值 > 2 亿美元（$200M）
#   2. 20MA > 50MA > 150MA（多头排列）
#   3. 逐月递增：现价 > 1个月前 > 2个月前（且隐含 2 个月收益为正）
#   排序：按 2 个月涨幅（动量）降序取前 3。
#
# 「资金流入板块」= sector_board 中 flow.tone == 'green'（相对大盘 3 月 RS ≥ 0）。
# 候选股池 = 各板块 ETF 的代表性成分股（大/中盘）。

SCREEN = {
    "min_market_cap_usd": 200_000_000,   # 2 亿美元
    "mom_month_days": 21,                 # 1 个月 ≈ 21 交易日
    "top_per_sector": 3,
    "min_hist": 155,                      # 需 ≥150 根算 MA150
}

# sector_board ticker → 候选成分股（TLT 无股票，跳过）
SECTOR_UNIVERSE = {
    "XLK":  ["AAPL","MSFT","NVDA","AVGO","ORCL","CRM","CSCO","ACN","AMD","ADBE",
             "TXN","QCOM","IBM","NOW","INTU","AMAT","MU","LRCX","ANET","PLTR"],
    "XLC":  ["GOOGL","META","NFLX","DIS","TMUS","VZ","T","CMCSA","CHTR","EA",
             "TTWO","WBD","OMC","LYV","MTCH"],
    "XLY":  ["AMZN","TSLA","HD","MCD","BKNG","LOW","NKE","SBUX","TJX","ORLY",
             "MAR","GM","F","CMG","HLT","RCL","DHI","ROST"],
    "XLP":  ["WMT","COST","PG","KO","PEP","PM","MO","MDLZ","CL","KHC",
             "GIS","KMB","STZ","KDP","HSY"],
    "XLV":  ["LLY","UNH","JNJ","MRK","ABBV","TMO","ABT","DHR","AMGN","ISRG",
             "PFE","VRTX","BSX","MDT","GILD","REGN","ELV","CI","SYK"],
    "XLF":  ["JPM","V","MA","BAC","WFC","GS","MS","AXP","SPGI","BLK",
             "C","SCHW","CB","PGR","KKR","PNC","BX","MMC"],
    "XLI":  ["GE","CAT","RTX","HON","UNP","BA","DE","LMT","ETN","UPS",
             "GEV","PH","TT","EMR","PWR","GD","NOC","CSX","ITW"],
    "XLE":  ["XOM","CVX","COP","EOG","SLB","PSX","MPC","VLO","OXY","WMB",
             "KMI","LNG","HES","DVN","FANG","HAL"],
    "XLU":  ["NEE","CEG","SO","DUK","SRE","D","AEP","EXC","XEL","PCG",
             "ED","VST","ETR","PEG","EIX"],
    "XLRE": ["PLD","AMT","EQIX","WELL","SPG","PSA","O","CCI","DLR","CBRE",
             "EXR","VICI","AVB","IRM"],
    "XLB":  ["LIN","SHW","APD","ECL","FCX","NEM","NUE","DOW","CTVA","VMC",
             "MLM","ALB","PPG","IFF"],
    "SMH":  ["NVDA","TSM","AVGO","AMD","ASML","QCOM","TXN","AMAT","MU","LRCX",
             "KLAC","ADI","MRVL","NXPI","MCHP","ON","MPWR","TER"],
    "GLD":  ["NEM","AEM","WPM","GOLD","KGC","AGI","FNV","RGLD","HL","EGO"],
}

SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")
WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN", "")
WXPUSHER_UIDS  = os.environ.get("WXPUSHER_UIDS", "").split(",")


# ═══════════════════════════════════════════════
# 共用工具函数
# ═══════════════════════════════════════════════

def get_realtime_change(ticker_obj):
    """用 fast_info 获取实时当日涨幅和价格（盘中/盘后均准确）"""
    try:
        fi      = ticker_obj.fast_info
        current = getattr(fi, "last_price", None)
        prev    = getattr(fi, "regular_market_previous_close", None)
        if current and prev and prev > 0:
            return round(current, 2), round((current - prev) / prev * 100, 2)
    except Exception:
        pass
    return None, None


def get_hist(symbol, period="3mo"):
    """获取历史数据，返回 DataFrame 或 None"""
    try:
        t    = yf.Ticker(symbol)
        hist = t.history(period=period)
        return t, hist if not hist.empty else None
    except Exception:
        return None, None


def calc_adx_di(hist, period=14):
    """Wilder-smoothed ADX + DI+ / DI-"""
    try:
        high  = hist["High"].values.astype(float)
        low   = hist["Low"].values.astype(float)
        close = hist["Close"].values.astype(float)
        n = len(close)
        if n < period * 2 + 1:
            return None

        tr  = np.zeros(n)
        pdm = np.zeros(n)
        mdm = np.zeros(n)
        for i in range(1, n):
            tr[i]  = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
            up     = high[i] - high[i-1]
            down   = low[i-1] - low[i]
            pdm[i] = up   if (up > down and up > 0)   else 0
            mdm[i] = down if (down > up and down > 0) else 0

        def wilder(arr, p):
            out = np.zeros(n)
            out[p] = arr[1:p+1].sum()
            for i in range(p+1, n):
                out[i] = out[i-1] - out[i-1]/p + arr[i]
            return out

        atr = wilder(tr,  period)
        pDM = wilder(pdm, period)
        mDM = wilder(mdm, period)
        with np.errstate(divide="ignore", invalid="ignore"):
            di_p = np.where(atr > 0, pDM / atr * 100, 0)
            di_m = np.where(atr > 0, mDM / atr * 100, 0)
            dx   = np.where((di_p + di_m) > 0, np.abs(di_p - di_m) / (di_p + di_m) * 100, 0)
        adx_arr = wilder(dx, period)
        # Wilder smoothing accumulates ~period× the average; divide back to 0-100
        return {
            "adx":      round(float(adx_arr[-1]) / period, 1),
            "di_plus":  round(float(di_p[-1]),             1),
            "di_minus": round(float(di_m[-1]),             1),
        }
    except Exception:
        return None


def calc_supertrend(hist, period=10, factor=3.0):
    """ATR-based Supertrend indicator (NaN-safe initialization)"""
    try:
        high  = hist["High"].values.astype(float)
        low   = hist["Low"].values.astype(float)
        close = hist["Close"].values.astype(float)
        n = len(close)
        if n < period * 2:
            return None

        tr = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))

        # Simple rolling ATR (NaN for warmup period)
        atr = np.full(n, np.nan)
        for i in range(period, n):
            atr[i] = tr[i-period+1:i+1].mean()

        hl2     = (high + low) / 2
        up_band = hl2 + factor * atr   # NaN for warmup
        dn_band = hl2 - factor * atr

        final_up = np.full(n, np.nan)
        final_dn = np.full(n, np.nan)
        trend    = np.zeros(n, dtype=int)   # 0=warmup, 1=bullish, -1=bearish

        for i in range(1, n):
            if np.isnan(up_band[i]):
                continue  # still in warmup, keep 0

            # When previous final band is NaN (first valid bar), seed from raw band
            fu_prev = final_up[i-1]
            fd_prev = final_dn[i-1]

            if np.isnan(fu_prev):
                final_up[i] = up_band[i]
            else:
                final_up[i] = up_band[i] if (up_band[i] < fu_prev or close[i-1] > fu_prev) else fu_prev

            if np.isnan(fd_prev):
                final_dn[i] = dn_band[i]
            else:
                final_dn[i] = dn_band[i] if (dn_band[i] > fd_prev or close[i-1] < fd_prev) else fd_prev

            prev_trend = trend[i-1]
            if prev_trend == 0:
                # First valid bar: initialize direction from price vs lower band
                trend[i] = 1 if close[i] > final_dn[i] else -1
            elif prev_trend == 1:
                trend[i] = -1 if close[i] < final_dn[i] else 1
            else:
                trend[i] =  1 if close[i] > final_up[i] else -1

        if trend[-1] == 0:
            return None

        direction = "bullish" if trend[-1] == 1 else "bearish"
        val_raw   = final_dn[-1] if trend[-1] == 1 else final_up[-1]
        value     = None if np.isnan(val_raw) else round(float(val_raw), 2)
        return {"direction": direction, "value": value}
    except Exception:
        return None


def calc_sqzmom(hist, bb_len=20, kc_mult=1.5):
    """Squeeze Momentum: BB inside KC + linear regression momentum"""
    try:
        close = hist["Close"].values.astype(float)
        high  = hist["High"].values.astype(float)
        low   = hist["Low"].values.astype(float)
        n = len(close)
        if n < bb_len + 5:
            return None

        close_s = pd.Series(close)
        ma      = close_s.rolling(bb_len).mean()
        std     = close_s.rolling(bb_len).std()
        bb_up   = (ma + 2 * std).values
        bb_dn   = (ma - 2 * std).values

        tr = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
        atr_s = pd.Series(tr).rolling(bb_len).mean()
        kc_up = (ma + kc_mult * atr_s).values
        kc_dn = (ma - kc_mult * atr_s).values

        sqz_on = bool(bb_up[-1] < kc_up[-1] and bb_dn[-1] > kc_dn[-1])

        highest = pd.Series(high).rolling(bb_len).max().values
        lowest  = pd.Series(low).rolling(bb_len).min().values
        delta   = close - (highest + lowest) / 2 - ma.values
        y = delta[-bb_len:]
        if len(y) < bb_len or np.any(np.isnan(y)):
            return None
        slope = float(np.polyfit(np.arange(bb_len, dtype=float), y, 1)[0])
        return {
            "sqz_on":  sqz_on,
            "sqz_mom": round(slope, 4),
            "sqz_dir": "up" if slope > 0 else "down",
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════
# 模块 B — Watchlist 技术分析
# ═══════════════════════════════════════════════

def analyze_watchlist():
    """
    对 WATCHLIST 中每只股票计算：
    - 当前价格 / 今日涨幅
    - MA20 / MA50（简单移动均线，基于收盘价）
    - 是否在 MA20 上方 / MA50 上方
    - 连续3日收盘递增（up3）
    - 连续3日收盘递减（dn3）
    返回结果列表
    """
    print(f"\n{'─'*55}")
    print("📋 模块 B — Watchlist 技术分析")
    print(f"{'─'*55}")

    results = []
    for symbol in WATCHLIST:
        try:
            t, hist = get_hist(symbol, period="3mo")
            if hist is None or len(hist) < 22:
                results.append({"symbol": symbol, "error": "数据不足"})
                print(f"  ⏭️ {symbol}: 历史数据不足")
                continue

            closes = hist["Close"].dropna().tolist()
            n      = len(closes)

            # 实时价格（优先）
            price, day_chg = get_realtime_change(t)
            if price is None:
                price   = round(closes[-1], 2)
                day_chg = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if n >= 2 else 0

            # MA20 / MA50
            ma20 = round(sum(closes[-20:]) / 20, 2) if n >= 20 else None
            ma50 = round(sum(closes[-50:]) / 50, 2) if n >= 50 else None

            above_ma20 = (price > ma20) if ma20 is not None else None
            above_ma50 = (price > ma50) if ma50 is not None else None

            # 连续3日涨/跌（比较最近4个收盘价）
            up3 = (n >= 4 and
                   closes[-1] > closes[-2] > closes[-3] > closes[-4])
            dn3 = (n >= 4 and
                   closes[-1] < closes[-2] < closes[-3] < closes[-4])

            # 最近3日收盘价（便于展示）
            last3 = [round(c, 2) for c in closes[-3:]] if n >= 3 else []

            # 高级技术指标
            adx_d = calc_adx_di(hist)
            st_d  = calc_supertrend(hist)
            sqz_d = calc_sqzmom(hist)

            # 综合强势评分 (0-10)
            score = 0
            if above_ma20:                                         score += 2
            if above_ma50:                                         score += 2
            if adx_d and adx_d["adx"] >= 25:                     score += 1
            if adx_d and adx_d["di_plus"] > adx_d["di_minus"]:  score += 1
            if st_d  and st_d["direction"] == "bullish":          score += 2
            if sqz_d:
                if sqz_d["sqz_dir"] == "up":                      score += 1   # 动量向上
                elif sqz_d["sqz_on"] and sqz_d["sqz_dir"]=="down": score -= 1  # 挤压中动量向下，警告
            if up3:                                                score += 1
            if dn3:                                                score -= 1
            score = max(0, min(10, score))
            GRADE_MAP = [(9,"超强势"), (7,"强势"), (5,"中性"), (3,"偏弱"), (0,"弱势")]
            grade = next(label for thr, label in GRADE_MAP if score >= thr)

            entry = {
                "symbol":         symbol,
                "price":          price,
                "day_chg":        day_chg,
                "ma20":           ma20,
                "ma50":           ma50,
                "above_ma20":     above_ma20,
                "above_ma50":     above_ma50,
                "up3":            up3,
                "dn3":            dn3,
                "last3":          last3,
                "adx":            adx_d["adx"]       if adx_d  else None,
                "di_plus":        adx_d["di_plus"]   if adx_d  else None,
                "di_minus":       adx_d["di_minus"]  if adx_d  else None,
                "supertrend":     st_d["direction"]  if st_d   else None,
                "st_value":       st_d["value"]      if st_d   else None,
                "sqz_on":         sqz_d["sqz_on"]    if sqz_d  else None,
                "sqz_dir":        sqz_d["sqz_dir"]   if sqz_d  else None,
                "sqz_mom":        sqz_d["sqz_mom"]   if sqz_d  else None,
                "strength_score": score,
                "strength_grade": grade,
            }
            results.append(entry)

            # 控制台简洁输出
            ma20_str = f"MA20={'✅' if above_ma20 else '❌'}"
            ma50_str = f"MA50={'✅' if above_ma50 else '❌'}"
            streak   = " 📈3日连涨" if up3 else (" 📉3日连跌" if dn3 else "")
            print(f"  {symbol:6s} ${price:<8.2f} {day_chg:+.2f}%  {ma20_str}  {ma50_str}{streak}")

        except Exception as e:
            results.append({"symbol": symbol, "error": str(e)})
            print(f"  ⚠️ {symbol}: {e}")

    # 统计摘要
    ok      = [r for r in results if "error" not in r]
    up_both = [r for r in ok if r.get("above_ma20") and r.get("above_ma50")]
    dn_both = [r for r in ok if r.get("above_ma20") == False and r.get("above_ma50") == False]
    up3s    = [r for r in ok if r.get("up3")]
    dn3s    = [r for r in ok if r.get("dn3")]

    print(f"\n  ✅ MA20+MA50均在上方: {[r['symbol'] for r in up_both]}")
    print(f"  ❌ MA20+MA50均在下方: {[r['symbol'] for r in dn_both]}")
    print(f"  📈 连续3日收涨: {[r['symbol'] for r in up3s]}")
    print(f"  📉 连续3日收跌: {[r['symbol'] for r in dn3s]}")

    return results


# ═══════════════════════════════════════════════
# 模块 A — 资金流入板块 强势股筛选（v4.0）
# ═══════════════════════════════════════════════

def load_sector_board():
    """读取 sector_board（优先 docs/data.json 最近一期；否则现算）。"""
    try:
        d = json.loads((DOCS_DIR / "data.json").read_text(encoding="utf-8"))
        for dt in sorted(d.keys(), reverse=True):
            sb = d[dt].get("sector_board")
            if sb and sb.get("sectors"):
                return sb
    except Exception as e:
        print(f"  ⚠️ 读取 data.json sector_board 失败: {e}")
    try:
        import sector_board
        return sector_board.build()
    except Exception as e:
        print(f"  ⚠️ 现算 sector_board 失败: {e}")
        return None


def get_inflow_sectors(sb):
    """返回资金流入板块列表（有候选股池的）：[{ticker,cn,en,emoji,rs_m3,m3_pct,ytd_pct,flow_cn}]。"""
    inflow = []
    for r in (sb.get("sectors", []) if sb else []):
        tk = r.get("ticker")
        if tk not in SECTOR_UNIVERSE:                 # TLT 等无股票池 → 跳过
            continue
        if (r.get("flow", {}).get("tone")) != "green":  # 只要流入（RS≥0）
            continue
        inflow.append({
            "ticker": tk, "cn": r.get("cn"), "en": r.get("en"),
            "emoji": r.get("emoji"), "rs_m3": r.get("rs_m3"),
            "m3_pct": r.get("m3_pct"), "ytd_pct": r.get("ytd_pct"),
            "flow_cn": r.get("flow", {}).get("cn"),
        })
    # 已按 RS 降序（sector_board 已排），这里再保险排一次
    inflow.sort(key=lambda x: (x["rs_m3"] is None, -(x["rs_m3"] or 0)))
    return inflow


def screen_stock(symbol):
    """按新三条件筛选单只股票；通过则返回 metrics，否则 None。"""
    t, hist = get_hist(symbol, "1y")
    if hist is None or len(hist) < SCREEN["min_hist"]:
        return None
    closes = hist["Close"].dropna()
    if len(closes) < SCREEN["min_hist"]:
        return None
    cl = closes.values.astype(float)

    # 现价 / 今日涨幅（实时优先）
    price, day_chg = get_realtime_change(t)
    if price is None:
        price   = round(float(cl[-1]), 2)
        day_chg = round((cl[-1] - cl[-2]) / cl[-2] * 100, 2) if len(cl) >= 2 else 0.0

    # 1) 市值 > 2 亿美元
    mcap = 0
    try:
        mcap = getattr(t.fast_info, "market_cap", 0) or 0
    except Exception:
        mcap = 0
    if mcap and mcap < SCREEN["min_market_cap_usd"]:
        return None

    # 2) 20MA > 50MA > 150MA（多头排列）
    ma20  = float(np.mean(cl[-20:]))
    ma50  = float(np.mean(cl[-50:]))
    ma150 = float(np.mean(cl[-150:]))
    if not (ma20 > ma50 > ma150):
        return None

    # 3) 逐月递增：现价 > 1个月前 > 2个月前
    md = SCREEN["mom_month_days"]
    c_now, c_1m, c_2m = float(cl[-1]), float(cl[-1 - md]), float(cl[-1 - 2 * md])
    if not (c_now > c_1m > c_2m):
        return None

    ret_2m   = round((c_now / c_2m - 1) * 100, 2)   # 2 个月总涨幅（排序键，隐含>0）
    ret_1m   = round((c_now / c_1m - 1) * 100, 2)   # 近 1 个月
    ret_prev = round((c_1m / c_2m - 1) * 100, 2)    # 前 1 个月

    metrics = {
        "symbol": symbol, "price": round(price, 2), "day_change_pct": day_chg,
        "market_cap_b": round(mcap / 1e9, 2) if mcap else None,
        "ma20": round(ma20, 2), "ma50": round(ma50, 2), "ma150": round(ma150, 2),
        "ret_2m": ret_2m, "ret_1m": ret_1m, "ret_prev_m": ret_prev,
    }
    st_d = calc_supertrend(hist)
    if st_d:
        metrics["supertrend"] = st_d["direction"]
    adx_d = calc_adx_di(hist)
    if adx_d:
        metrics["adx"] = adx_d["adx"]
    return metrics


def screen_sector(sec):
    """筛选单个流入板块，返回按 2 个月涨幅降序的前 3 名。"""
    tk = sec["ticker"]
    candidates = SECTOR_UNIVERSE.get(tk, [])
    print(f"\n  🔍 {sec['emoji']} {sec['cn']} ({tk}, {len(candidates)} 只候选)  RS={sec['rs_m3']}...")
    passed = []
    for symbol in candidates:
        try:
            m = screen_stock(symbol)
            if m:
                m["sector"] = tk
                passed.append(m)
                print(f"    ✅ {symbol}: 2月{m['ret_2m']:+.1f}%  今日{m['day_change_pct']:+.2f}%")
        except Exception as e:
            print(f"    ⚠️ {symbol}: {e}")
    passed.sort(key=lambda x: x.get("ret_2m", -999), reverse=True)
    return passed[:SCREEN["top_per_sector"]]


# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════

def run_all():
    et_tz     = pytz.timezone("America/New_York")
    today     = datetime.now(et_tz)
    today_str = today.strftime("%Y-%m-%d")

    if today.weekday() >= 5:
        print(f"⏭️ 周末跳过 ({today_str})")
        return None

    print(f"\n{'═'*55}")
    print(f"🚀 Stock Screener v4.0 — {today_str}")
    print(f"{'═'*55}")

    # ── 模块 B：Watchlist 技术分析（无条件每日运行）──
    watchlist_results = analyze_watchlist()

    # ── 模块 A：资金流入板块 强势股筛选 ──
    print(f"\n{'─'*55}")
    print("📊 模块 A — 资金流入板块 强势股（市值>2亿 · 20>50>150MA · 逐月递增 · 按2月涨幅取前3）")
    sb = load_sector_board()
    inflow = get_inflow_sectors(sb)

    results_by_sector = {}
    if inflow:
        print(f"\n✅ 资金流入板块 ({len(inflow)}个): {[s['ticker'] for s in inflow]}")
        for s in inflow:
            results_by_sector[s["ticker"]] = screen_sector(s)
    else:
        print("⚠️ 无资金流入板块（或 sector_board 缺失），模块 A 跳过")

    # sector_board 全部板块（含流出）供前端「板块强弱条」展示
    sector_flow = {}
    for r in (sb.get("sectors", []) if sb else []):
        tk = r.get("ticker")
        sector_flow[tk] = {
            "cn": r.get("cn"), "en": r.get("en"), "emoji": r.get("emoji"),
            "rs_m3": r.get("rs_m3"), "m3_pct": r.get("m3_pct"),
            "ytd_pct": r.get("ytd_pct"), "day_pct": r.get("day_pct"),
            "flow_cn": r.get("flow", {}).get("cn"),
            "flow_tone": r.get("flow", {}).get("tone"),
            "is_inflow": r.get("flow", {}).get("tone") == "green",
            "has_stocks": tk in SECTOR_UNIVERSE,
        }

    # ── 汇总报告 ──
    report = {
        "date":         today_str,
        "generated_at": today.strftime("%Y-%m-%d %H:%M ET"),
        "screen_criteria": "资金流入板块 · 市值>2亿 · 20MA>50MA>150MA · 逐月递增（现价>1月前>2月前）· 按2月涨幅取前3",
        # 模块 B
        "watchlist": watchlist_results,
        # 模块 A（v4.0）
        "inflow_sectors":    [s["ticker"] for s in inflow],
        "sector_flow":       sector_flow,
        "results_by_sector": results_by_sector,
    }
    return report


# ═══════════════════════════════════════════════
# 保存 JSON
# ═══════════════════════════════════════════════

def _sanitize(obj):
    """递归将 NaN/Inf 替换为 None，确保合法 JSON。"""
    if isinstance(obj, float):
        return None if (obj != obj or obj == float('inf') or obj == float('-inf')) else obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def save_json(report, path="docs/data/stock_screener.json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    history = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            history = json.load(f).get("history", [])
    history = [h for h in history if h.get("date") != report["date"]]
    history.insert(0, report)
    payload = _sanitize({"latest": report, "history": history[:30],
                          "updated_at": report["generated_at"]})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON 已保存: {path}")


# ═══════════════════════════════════════════════
# 推送通知
# ═══════════════════════════════════════════════

def build_message(report):
    lines = [f"📊 每日股票分析 {report['date']}", ""]

    # ── 模块 B 摘要 ──
    wl = [r for r in report.get("watchlist", []) if "error" not in r]

    up_both = [r["symbol"] for r in wl if r.get("above_ma20") and r.get("above_ma50")]
    dn_both = [r["symbol"] for r in wl if r.get("above_ma20") == False and r.get("above_ma50") == False]
    up3s    = [r["symbol"] for r in wl if r.get("up3")]
    dn3s    = [r["symbol"] for r in wl if r.get("dn3")]

    lines.append("📋 自选股技术分析")
    lines.append(f"  ✅ MA20+MA50均上方 ({len(up_both)}只): {', '.join(up_both) or '无'}")
    lines.append(f"  ❌ MA20+MA50均下方 ({len(dn_both)}只): {', '.join(dn_both) or '无'}")
    lines.append(f"  📈 连续3日收涨 ({len(up3s)}只): {', '.join(up3s) or '无'}")
    lines.append(f"  📉 连续3日收跌 ({len(dn3s)}只): {', '.join(dn3s) or '无'}")
    lines.append("")

    # ── 模块 A 摘要 ──
    inflow = report.get("inflow_sectors", [])
    flow   = report.get("sector_flow", {})
    if inflow:
        lines.append("📈 资金流入板块 强势股（2月涨幅前3）")
        for tk in inflow:
            info   = flow.get(tk, {})
            stocks = report["results_by_sector"].get(tk, [])
            rs = info.get("rs_m3")
            lines.append(f"  {info.get('emoji','')} {info.get('cn',tk)} | {tk} RS{('%+.1f'%rs) if rs is not None else '—'}%")
            for i, st in enumerate(stocks, 1):
                lines.append(f"    #{i} {st['symbol']}  ${st['price']}  2月{st['ret_2m']:+.1f}%")
        lines.append("")

    lines += ["⚠️ 仅供参考，不构成投资建议",
              "🔗 https://rachelxrz.github.io/daily-brief/"]
    return "\n".join(lines)


def push_serverchan(msg, title="📊 每日股票分析"):
    if not SERVERCHAN_KEY:
        return
    requests.post(f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
                  data={"title": title, "desp": msg}, timeout=10)
    print("📨 Server酱已推送")


def push_wxpusher(msg, title="📊 每日股票分析"):
    if not WXPUSHER_TOKEN or not WXPUSHER_UIDS[0]:
        return
    requests.post("https://wxpusher.zjiecode.com/api/send/message",
                  json={"appToken": WXPUSHER_TOKEN, "content": msg,
                        "summary": title, "contentType": 1,
                        "uids": WXPUSHER_UIDS}, timeout=10)
    print("📨 WxPusher已推送")


# ═══════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    report = run_all()
    if report:
        save_json(report)
        # 微信推送已停用（微信只推送新闻简报），结果仅保存到网页
        print("⏭️ 微信推送已停用（微信只推送新闻简报），结果仅保存到网页")
        print("\n✅ 全部完成！")
    else:
        print("\n⏭️ 今日跳过")
