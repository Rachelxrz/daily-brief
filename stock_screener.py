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
import pytz
import numpy as np
import pandas as pd

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
# 模块 A 配置 — 板块 ETF + 候选股池
# ═══════════════════════════════════════════════

SECTORS = {
    "Energy": {
        "etf": "XLE", "etf_name": "Energy Select Sector SPDR", "emoji": "⛽",
        "stocks": ["XOM","CVX","COP","EOG","SLB","PSX","MPC","VLO",
                   "OXY","HAL","KMI","WMB","LNG","DVN","FANG"],
    },
    "Industrials": {
        "etf": "XLI", "etf_name": "Industrial Select Sector SPDR", "emoji": "🏗️",
        "stocks": ["GE","CAT","RTX","HON","LMT","UNP","DE","ETN",
                   "EMR","GEV","GNRC","PWR","URI","FDX","NOC"],
    },
    "Utilities": {
        "etf": "XLU", "etf_name": "Utilities Select Sector SPDR", "emoji": "🔌",
        "stocks": ["NEE","CEG","SO","DUK","SRE","D","AEP","EXC",
                   "XEL","PCG","ED","ETR","FE","NRG","VST"],
    },
    "Materials": {
        "etf": "XLB", "etf_name": "Materials Select Sector SPDR", "emoji": "⚗️",
        "stocks": ["LIN","APD","SHW","FCX","NEM","NUE","VMC","MLM",
                   "CF","MOS","ALB","PPG","IP","PKG","SON"],
    },
    "Consumer Staples": {
        "etf": "XLP", "etf_name": "Consumer Staples Select Sector SPDR", "emoji": "🛒",
        "stocks": ["WMT","COST","PG","KO","PEP","PM","MO","MDLZ",
                   "CL","KHC","GIS","K","HSY","SYY","BG"],
    },
    "Gold": {
        "etf": "GLD", "etf_name": "SPDR Gold Shares", "emoji": "🥇",
        "stocks": ["NEM","AEM","WPM","GOLD","KGC","AGI","HL","EGO","AU","BTG","OR","IAG"],
        "relaxed_screener": True,
    },
    "Copper": {
        "etf": "COPX", "etf_name": "Global X Copper Miners ETF", "emoji": "🔶",
        "stocks": ["FCX","SCCO","TECK","HBM","VALE","BHP","RIO"],
        "relaxed_screener": True,
    },
}

SCREENER_STRICT = {
    "min_price": 100, "min_market_cap_b": 15,
    "min_avg_volume": 300_000, "min_eps": 0.25,
    "ma_periods": [25, 50, 125], "ma_thresholds": [0.001, 0.002, 0.007],
    "top_per_sector": 3,
}
SCREENER_RELAXED = {
    "min_price": 5, "min_market_cap_b": 2,
    "min_avg_volume": 200_000, "min_eps": None,
    "ma_periods": [25, 50], "ma_thresholds": [0.0, 0.0],
    "top_per_sector": 3,
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
    """ATR-based Supertrend indicator"""
    try:
        high  = hist["High"].values.astype(float)
        low   = hist["Low"].values.astype(float)
        close = hist["Close"].values.astype(float)
        n = len(close)
        if n < period + 1:
            return None

        tr = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
        atr = pd.Series(tr).rolling(period).mean().values

        hl2     = (high + low) / 2
        up_band = hl2 + factor * atr
        dn_band = hl2 - factor * atr

        final_up = np.copy(up_band)
        final_dn = np.copy(dn_band)
        trend    = np.ones(n)
        for i in range(1, n):
            final_up[i] = up_band[i] if (up_band[i] < final_up[i-1] or close[i-1] > final_up[i-1]) else final_up[i-1]
            final_dn[i] = dn_band[i] if (dn_band[i] > final_dn[i-1] or close[i-1] < final_dn[i-1]) else final_dn[i-1]
            if trend[i-1] == 1:
                trend[i] = -1 if close[i] < final_dn[i] else 1
            else:
                trend[i] =  1 if close[i] > final_up[i] else -1

        direction = "bullish" if trend[-1] == 1 else "bearish"
        value = round(float(final_dn[-1] if trend[-1] == 1 else final_up[-1]), 2)
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
            if sqz_d and sqz_d["sqz_dir"] == "up":               score += 1
            if up3:                                                score += 1
            if dn3:                                                score  = max(0, score - 1)
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
# 模块 A — ETF 板块表现
# ═══════════════════════════════════════════════

def get_etf_day_change(symbol):
    t = yf.Ticker(symbol)
    price, pct = get_realtime_change(t)
    if price is not None:
        return pct, price
    hist = t.history(period="5d")
    if len(hist) >= 2:
        prev = hist["Close"].iloc[-2]
        last = hist["Close"].iloc[-1]
        return round((last - prev) / prev * 100, 2), round(last, 2)
    return 0.0, 0.0


def get_all_sector_perf():
    print("📊 模块 A — 板块 ETF 今日表现\n")
    perf = {}
    for sector, cfg in SECTORS.items():
        etf = cfg["etf"]
        try:
            pct, price = get_etf_day_change(etf)
            perf[sector] = {"pct": pct, "price": price, "etf": etf}
            print(f"  {cfg['emoji']} {sector:22s} {etf}: ${price:<8.2f} {pct:+.2f}%")
        except Exception as e:
            perf[sector] = {"pct": 0, "price": 0, "etf": etf}
            print(f"  ⚠️ {sector} ({etf}): {e}")
    return perf


def passes_screener(ticker_obj, hist_1y, cfg):
    metrics = {}
    try:
        info  = ticker_obj.fast_info
        current = getattr(info, "last_price", None)
        price = current if current else hist_1y["Close"].iloc[-1]
        metrics["price"] = round(price, 2)
        if price < cfg["min_price"]:
            return False, metrics

        market_cap_b = (getattr(info, "market_cap", 0) or 0) / 1e9
        metrics["market_cap_b"] = round(market_cap_b, 1)
        if market_cap_b < cfg["min_market_cap_b"]:
            return False, metrics

        avg_vol = hist_1y["Volume"].mean()
        metrics["avg_volume"] = int(avg_vol)
        if avg_vol < cfg["min_avg_volume"]:
            return False, metrics

        # 今日涨幅
        try:
            fi   = ticker_obj.fast_info
            cur  = getattr(fi, "last_price", None)
            prev = getattr(fi, "regular_market_previous_close", None)
            if cur and prev and prev > 0:
                metrics["day_change_pct"] = round((cur - prev) / prev * 100, 2)
                metrics["price"] = round(cur, 2)
            else:
                raise ValueError
        except Exception:
            if len(hist_1y) >= 2:
                p = hist_1y["Close"].iloc[-2]
                c = hist_1y["Close"].iloc[-1]
                metrics["day_change_pct"] = round((c - p) / p * 100, 2)
            else:
                metrics["day_change_pct"] = 0

        if cfg["min_eps"] is not None:
            try:
                eps = ticker_obj.info.get("trailingEps", None)
                metrics["eps"] = eps
                if eps is not None and eps < cfg["min_eps"]:
                    return False, metrics
            except:
                metrics["eps"] = None
        else:
            metrics["eps"] = None

        closes = hist_1y["Close"]
        for period, threshold in zip(cfg["ma_periods"], cfg["ma_thresholds"]):
            if len(closes) < period:
                return False, metrics
            ma      = closes.rolling(period).mean().iloc[-1]
            pct_abv = (closes.iloc[-1] - ma) / ma
            metrics[f"ma{period}"]           = round(ma, 2)
            metrics[f"pct_above_ma{period}"] = round(pct_abv * 100, 2)
            if pct_abv < threshold:
                return False, metrics

        return True, metrics
    except Exception as e:
        print(f"    screener error: {e}")
        return False, {}


def screen_sector(sector_name, sector_cfg, screener_cfg):
    candidates = sector_cfg["stocks"]
    emoji      = sector_cfg["emoji"]
    min_hist   = max(screener_cfg["ma_periods"] + [30])
    print(f"\n  🔍 {emoji} {sector_name} ({len(candidates)} 只候选股)...")

    passed = []
    for symbol in candidates:
        try:
            t, hist = get_hist(symbol, "1y")
            if hist is None or len(hist) < min_hist:
                continue
            ok, metrics = passes_screener(t, hist, screener_cfg)
            if ok:
                metrics["symbol"] = symbol
                metrics["sector"] = sector_name
                adx_d = calc_adx_di(hist)
                st_d  = calc_supertrend(hist)
                sqz_d = calc_sqzmom(hist)
                if adx_d:
                    metrics.update(adx_d)
                if st_d:
                    metrics["supertrend"] = st_d["direction"]
                    metrics["st_value"]   = st_d["value"]
                if sqz_d:
                    metrics["sqz_on"]  = sqz_d["sqz_on"]
                    metrics["sqz_dir"] = sqz_d["sqz_dir"]
                    metrics["sqz_mom"] = sqz_d["sqz_mom"]
                passed.append(metrics)
                print(f"    ✅ {symbol}: ${metrics['price']}  {metrics['day_change_pct']:+.2f}%")
            else:
                print(f"    ❌ {symbol}")
        except Exception as e:
            print(f"    ⚠️ {symbol}: {e}")

    passed.sort(key=lambda x: x.get("day_change_pct", 0), reverse=True)
    return passed[:screener_cfg["top_per_sector"]]


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
    print(f"🚀 Stock Screener v3.0 — {today_str}")
    print(f"{'═'*55}")

    # ── 模块 B：Watchlist 技术分析（无条件每日运行）──
    watchlist_results = analyze_watchlist()

    # ── 模块 A：板块轮动筛选 ──
    print(f"\n{'─'*55}")
    sector_perf = get_all_sector_perf()

    leading = sorted(
        [s for s, p in sector_perf.items() if p["pct"] > 0],
        key=lambda s: sector_perf[s]["pct"], reverse=True,
    )

    results_by_sector = {}
    if leading:
        print(f"\n✅ 今日上涨板块 ({len(leading)}个): {leading}")
        for s in leading:
            cfg = SCREENER_RELAXED if SECTORS[s].get("relaxed_screener") else SCREENER_STRICT
            results_by_sector[s] = screen_sector(s, SECTORS[s], cfg)
    else:
        print("⚠️ 今日所有板块均下跌，模块 A 跳过")

    # ── 汇总报告 ──
    report = {
        "date":         today_str,
        "generated_at": today.strftime("%Y-%m-%d %H:%M ET"),
        # 模块 B
        "watchlist": watchlist_results,
        # 模块 A
        "leading_sectors":   leading,
        "sector_perf": {
            s: {
                **sector_perf[s],
                "etf_name":   SECTORS[s]["etf_name"],
                "emoji":      SECTORS[s]["emoji"],
                "is_leading": s in leading,
            }
            for s in SECTORS
        },
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
    leading = report.get("leading_sectors", [])
    if leading:
        lines.append("📈 今日领涨板块强势股")
        for s in leading:
            info   = report["sector_perf"][s]
            stocks = report["results_by_sector"].get(s, [])
            lines.append(f"  {info['emoji']} {s} | {info['etf']} {info['pct']:+.2f}%")
            for i, st in enumerate(stocks, 1):
                lines.append(f"    #{i} {st['symbol']}  ${st['price']}  {st['day_change_pct']:+.2f}%")
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
        msg = build_message(report)
        push_serverchan(msg)
        push_wxpusher(msg)
        print("\n✅ 全部完成！")
    else:
        print("\n⏭️ 今日跳过")
