"""
stock_screener.py  v2.0
-----------------------
每日自动筛选轮动板块中的强势股
整合进 rachelxrz.github.io/daily-brief 项目

更新内容:
- 每个板块独立输出 TOP 3（而非全局 TOP 3）
- 每个板块配对应 ETF 及其今日表现
- 新增 Gold（黄金）和 Copper（铜）板块
- 铜/金特殊处理：放宽均线阈值，适配商品股波动

数据源: yfinance (Yahoo Finance) - 免费无需 API Key
运行时间: 每个交易日收盘后 (UTC 21:30 = 美东 4:30PM)
"""

import yfinance as yf
import json
import os
import requests
from datetime import datetime
import pytz

# ─────────────────────────────────────────────
# 1. 板块配置：ETF + 候选股池
# ─────────────────────────────────────────────

SECTORS = {
    "Energy": {
        "etf": "XLE",
        "etf_name": "Energy Select Sector SPDR",
        "emoji": "⛽",
        "stocks": [
            "XOM", "CVX", "COP", "EOG", "SLB", "PSX", "MPC", "VLO",
            "OXY", "HAL", "KMI", "WMB", "LNG", "DVN", "FANG",
        ],
    },
    "Industrials": {
        "etf": "XLI",
        "etf_name": "Industrial Select Sector SPDR",
        "emoji": "🏗️",
        "stocks": [
            "GE", "CAT", "RTX", "HON", "LMT", "UNP", "DE", "ETN",
            "EMR", "GEV", "GNRC", "PWR", "URI", "FDX", "NOC",
        ],
    },
    "Utilities": {
        "etf": "XLU",
        "etf_name": "Utilities Select Sector SPDR",
        "emoji": "🔌",
        "stocks": [
            "NEE", "CEG", "SO", "DUK", "SRE", "D", "AEP", "EXC",
            "XEL", "PCG", "ED", "ETR", "FE", "NRG", "VST",
        ],
    },
    "Materials": {
        "etf": "XLB",
        "etf_name": "Materials Select Sector SPDR",
        "emoji": "⚗️",
        "stocks": [
            "LIN", "APD", "SHW", "FCX", "NEM", "NUE", "VMC", "MLM",
            "CF", "MOS", "ALB", "PPG", "IP", "PKG", "SON",
        ],
    },
    "Consumer Staples": {
        "etf": "XLP",
        "etf_name": "Consumer Staples Select Sector SPDR",
        "emoji": "🛒",
        "stocks": [
            "WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "MDLZ",
            "CL", "KHC", "GIS", "K", "HSY", "SYY", "BG",
        ],
    },
    "Gold": {
        "etf": "GLD",
        "etf_name": "SPDR Gold Shares",
        "emoji": "🥇",
        "stocks": [
            "NEM", "AEM", "WPM", "GOLD", "KGC", "AGI",
            "HL", "EGO", "AU", "BTG", "OR", "IAG",
        ],
        "relaxed_screener": True,
    },
    "Copper": {
        "etf": "COPX",
        "etf_name": "Global X Copper Miners ETF",
        "emoji": "🔶",
        "stocks": [
            "FCX", "SCCO", "TECK", "HBM", "VALE", "BHP", "RIO",
        ],
        "relaxed_screener": True,
    },
}

# ─────────────────────────────────────────────
# 2. Screener 过滤条件
# ─────────────────────────────────────────────

SCREENER_STRICT = {
    "min_price":        100,
    "min_market_cap_b": 15,
    "min_avg_volume":   300_000,
    "min_eps":          0.25,
    "ma_periods":       [25, 50, 125],
    "ma_thresholds":    [0.001, 0.002, 0.007],
    "top_per_sector":   3,
}

# 黄金/铜板块放宽条件
SCREENER_RELAXED = {
    "min_price":        5,
    "min_market_cap_b": 2,
    "min_avg_volume":   200_000,
    "min_eps":          None,
    "ma_periods":       [25, 50],
    "ma_thresholds":    [0.0, 0.0],
    "top_per_sector":   3,
}

SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")
WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN", "")
WXPUSHER_UIDS  = os.environ.get("WXPUSHER_UIDS", "").split(",")


# ─────────────────────────────────────────────
# 3. 获取所有板块 ETF 今日表现
# ─────────────────────────────────────────────

def get_all_sector_perf():
    print("📊 获取板块 ETF 今日表现...\n")
    perf = {}
    for sector, cfg in SECTORS.items():
        etf = cfg["etf"]
        try:
            t    = yf.Ticker(etf)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                prev  = hist["Close"].iloc[-2]
                today = hist["Close"].iloc[-1]
                pct   = (today - prev) / prev * 100
                price = round(today, 2)
                perf[sector] = {"pct": round(pct, 2), "price": price, "etf": etf}
                print(f"  {cfg['emoji']} {sector:22s} {etf:5s}: ${price:<8.2f} {pct:+.2f}%")
        except Exception as e:
            perf[sector] = {"pct": 0, "price": 0, "etf": etf}
            print(f"  ⚠️ {sector} ({etf}) 获取失败: {e}")
    return perf


# ─────────────────────────────────────────────
# 4. 单只股票 Screener 检查
# ─────────────────────────────────────────────

def passes_screener(ticker_obj, hist_1y, cfg):
    metrics = {}
    try:
        info  = ticker_obj.fast_info
        price = getattr(info, "last_price", None) or hist_1y["Close"].iloc[-1]
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

        if len(hist_1y) >= 2:
            prev = hist_1y["Close"].iloc[-2]
            curr = hist_1y["Close"].iloc[-1]
            metrics["day_change_pct"] = round((curr - prev) / prev * 100, 2)
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


# ─────────────────────────────────────────────
# 5. 筛选单个板块，返回 TOP N
# ─────────────────────────────────────────────

def screen_sector(sector_name, sector_cfg, screener_cfg):
    candidates = sector_cfg["stocks"]
    emoji      = sector_cfg["emoji"]
    min_hist   = max(screener_cfg["ma_periods"] + [30])
    print(f"\n🔍 {emoji} {sector_name} ({len(candidates)} 只候选股)...")

    passed_list = []
    for symbol in candidates:
        try:
            ticker = yf.Ticker(symbol)
            hist   = ticker.history(period="1y")
            if hist.empty or len(hist) < min_hist:
                print(f"  ⏭️ {symbol}: 历史数据不足")
                continue
            passed, metrics = passes_screener(ticker, hist, screener_cfg)
            if passed:
                metrics["symbol"] = symbol
                metrics["sector"] = sector_name
                passed_list.append(metrics)
                print(f"  ✅ {symbol}: ${metrics['price']}  今日{metrics['day_change_pct']:+.2f}%")
            else:
                print(f"  ❌ {symbol}: 未通过 (${metrics.get('price','?')})")
        except Exception as e:
            print(f"  ⚠️ {symbol}: {e}")

    passed_list.sort(key=lambda x: x.get("day_change_pct", 0), reverse=True)
    return passed_list[:screener_cfg["top_per_sector"]]


# ─────────────────────────────────────────────
# 6. 主流程
# ─────────────────────────────────────────────

def run_screener():
    et_tz     = pytz.timezone("America/New_York")
    today     = datetime.now(et_tz)
    today_str = today.strftime("%Y-%m-%d")

    if today.weekday() >= 5:
        print(f"⏭️ 周末跳过 ({today_str})")
        return None

    print(f"\n{'='*55}")
    print(f"🚀 Stock Screener v2.0 — {today_str}")
    print(f"{'='*55}\n")

    # 所有板块 ETF 表现
    sector_perf = get_all_sector_perf()

    # 今日上涨板块（按涨幅排序）
    leading = sorted(
        [s for s, p in sector_perf.items() if p["pct"] > 0],
        key=lambda s: sector_perf[s]["pct"],
        reverse=True,
    )
    if not leading:
        print("⚠️ 今日所有板块均下跌")
        return None

    print(f"\n✅ 今日上涨板块 ({len(leading)}个): {leading}")

    # 逐板块筛选 TOP 3
    results_by_sector = {}
    for s in leading:
        cfg  = SCREENER_RELAXED if SECTORS[s].get("relaxed_screener") else SCREENER_STRICT
        results_by_sector[s] = screen_sector(s, SECTORS[s], cfg)

    # 汇总打印
    print(f"\n{'='*55}")
    print("🏆 筛选结果汇总")
    print(f"{'='*55}")
    for s in leading:
        p      = sector_perf[s]
        emoji  = SECTORS[s]["emoji"]
        etf    = SECTORS[s]["etf"]
        stocks = results_by_sector.get(s, [])
        print(f"\n  {emoji} {s} | ETF {etf}: ${p['price']} ({p['pct']:+.2f}%)")
        if stocks:
            for i, st in enumerate(stocks, 1):
                print(f"    #{i} {st['symbol']:6s} ${st['price']:>8.2f}  今日{st['day_change_pct']:+.2f}%")
        else:
            print("    （无股票通过筛选条件）")

    return {
        "date":              today_str,
        "generated_at":      today.strftime("%Y-%m-%d %H:%M ET"),
        "leading_sectors":   leading,
        "sector_perf":       {
            s: {
                **sector_perf[s],
                "etf_name":   SECTORS[s]["etf_name"],
                "emoji":      SECTORS[s]["emoji"],
                "is_leading": s in leading,
            }
            for s in SECTORS
        },
        "results_by_sector": results_by_sector,
        "screener_config": {
            "strict_note":  "Energy/Industrials/Utilities/Materials/Staples",
            "relaxed_note": "Gold/Copper — 放宽价格、市值、EPS、均线条件",
        },
    }


# ─────────────────────────────────────────────
# 7. 保存 JSON
# ─────────────────────────────────────────────

def save_json(report, path="docs/data/stock_screener.json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    history = []
    if os.path.exists(path):
        with open(path) as f:
            history = json.load(f).get("history", [])
    history = [h for h in history if h.get("date") != report["date"]]
    history.insert(0, report)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"latest": report, "history": history[:30],
                   "updated_at": report["generated_at"]},
                  f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON 已保存: {path}")


# ─────────────────────────────────────────────
# 8. 推送通知
# ─────────────────────────────────────────────

def build_message(report):
    lines = [f"📈 每日强势股筛选 {report['date']}", ""]
    for s in report["leading_sectors"]:
        info   = report["sector_perf"][s]
        stocks = report["results_by_sector"].get(s, [])
        lines.append(f"{info['emoji']} {s} | {info['etf']} {info['pct']:+.2f}%")
        if stocks:
            for i, st in enumerate(stocks, 1):
                lines.append(f"  #{i} {st['symbol']}  ${st['price']}  今日{st['day_change_pct']:+.2f}%")
        else:
            lines.append("  （无通过筛选）")
        lines.append("")
    lines += ["⚠️ 仅供参考，不构成投资建议",
              "🔗 https://rachelxrz.github.io/daily-brief/"]
    return "\n".join(lines)


def push_serverchan(msg, title="📈 每日强势股筛选"):
    if not SERVERCHAN_KEY:
        return
    requests.post(f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
                  data={"title": title, "desp": msg}, timeout=10)
    print("📨 Server酱已推送")


def push_wxpusher(msg, title="📈 每日强势股筛选"):
    if not WXPUSHER_TOKEN or not WXPUSHER_UIDS[0]:
        return
    requests.post("https://wxpusher.zjiecode.com/api/send/message",
                  json={"appToken": WXPUSHER_TOKEN, "content": msg,
                        "summary": title, "contentType": 1,
                        "uids": WXPUSHER_UIDS}, timeout=10)
    print("📨 WxPusher已推送")


# ─────────────────────────────────────────────
# 9. 入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    report = run_screener()
    if report:
        save_json(report)
        msg = build_message(report)
        push_serverchan(msg)
        push_wxpusher(msg)
        print("\n✅ 全部完成！")
    else:
        print("\n⏭️ 今日无结果，程序正常退出")
