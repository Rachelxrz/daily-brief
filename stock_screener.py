"""
stock_screener.py
-----------------
每日自动筛选轮动板块中的强势股
整合进 rachelxrz.github.io/daily-brief 项目

数据源: yfinance (Yahoo Finance) - 免费无需API Key
运行时间: 每个交易日 收盘后 (UTC 21:30 = 美东 4:30PM)
"""

import yfinance as yf
import pandas as pd
import json
import os
import requests
from datetime import datetime, date
import pytz

# ─────────────────────────────────────────────
# 1. 配置区
# ─────────────────────────────────────────────

# 当前轮动板块 ETF (用于判断今日哪些板块最强)
SECTOR_ETFS = {
    "Energy":           "XLE",
    "Industrials":      "XLI",
    "Utilities":        "XLU",
    "Materials":        "XLB",
    "Consumer Staples": "XLP",
}

# 各板块代表性大盘股候选池 (市值 ≥ $15B, 价格 ≥ $100)
SECTOR_STOCKS = {
    "Energy": [
        "XOM", "CVX", "COP", "EOG", "SLB", "PSX", "MPC", "VLO",
        "OXY", "HAL", "KMI", "WMB", "LNG", "DVN", "FANG"
    ],
    "Industrials": [
        "GE", "CAT", "RTX", "HON", "LMT", "UNP", "DE", "ETN",
        "EMR", "GEV", "GNRC", "PWR", "URI", "FDX", "NOC"
    ],
    "Utilities": [
        "NEE", "CEG", "SO", "DUK", "SRE", "D", "AEP", "EXC",
        "XEL", "PCG", "ED", "ETR", "FE", "NRG", "VST"
    ],
    "Materials": [
        "LIN", "APD", "SHW", "FCX", "NEM", "NUE", "VMC", "MLM",
        "CF", "MOS", "ALB", "PPG", "IP", "PKG", "SON"
    ],
    "Consumer Staples": [
        "WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "MDLZ",
        "CL", "KHC", "GIS", "K", "HSY", "SYY", "BG"
    ],
}

# Screener 过滤条件 (对应你的 ThinkorSwim "2024 bull" 设置)
SCREENER_CONFIG = {
    "min_price":        100,       # 股价 ≥ $100
    "min_market_cap_b": 15,        # 市值 ≥ $15B
    "min_avg_volume":   300_000,   # 平均成交量 ≥ 300,000
    "min_eps":          0.25,      # EPS ≥ 0.25 (盈利为正)
    "ma_periods":       [25, 50, 125],  # 均线周期
    "ma_thresholds":    [0.001, 0.002, 0.007],  # 收盘价高于均线的最小幅度
    "top_n":            3,         # 最终输出前N名
}

# 通知配置 (从 GitHub Secrets 读取)
SERVERCHAN_KEY  = os.environ.get("SERVERCHAN_KEY", "")
WXPUSHER_TOKEN  = os.environ.get("WXPUSHER_TOKEN", "")
WXPUSHER_UIDS   = os.environ.get("WXPUSHER_UIDS", "").split(",")


# ─────────────────────────────────────────────
# 2. 获取板块今日表现，选出最强板块
# ─────────────────────────────────────────────

def get_leading_sectors(top_n=3):
    """返回今日涨幅最大的 top_n 个板块"""
    print("📊 获取板块今日表现...")
    results = {}
    for sector, ticker in SECTOR_ETFS.items():
        try:
            etf = yf.Ticker(ticker)
            hist = etf.history(period="2d")
            if len(hist) >= 2:
                prev_close = hist["Close"].iloc[-2]
                today_close = hist["Close"].iloc[-1]
                pct = (today_close - prev_close) / prev_close * 100
                results[sector] = round(pct, 2)
                print(f"  {sector} ({ticker}): {pct:+.2f}%")
        except Exception as e:
            print(f"  ⚠️ {sector} 获取失败: {e}")

    # 按涨幅排序，取前N
    sorted_sectors = sorted(results.items(), key=lambda x: x[1], reverse=True)
    leading = [s[0] for s in sorted_sectors[:top_n]]
    print(f"\n✅ 今日领涨板块: {leading}")
    return leading, dict(sorted_sectors)


# ─────────────────────────────────────────────
# 3. 对候选股票做 Screener 过滤
# ─────────────────────────────────────────────

def passes_screener(ticker_obj, hist_1y, cfg):
    """
    检查单只股票是否满足所有 screener 条件
    返回 (passed: bool, metrics: dict)
    """
    metrics = {}
    try:
        info = ticker_obj.fast_info

        # 价格
        price = getattr(info, "last_price", None) or hist_1y["Close"].iloc[-1]
        metrics["price"] = round(price, 2)
        if price < cfg["min_price"]:
            return False, metrics

        # 市值
        market_cap = getattr(info, "market_cap", 0) or 0
        market_cap_b = market_cap / 1e9
        metrics["market_cap_b"] = round(market_cap_b, 1)
        if market_cap_b < cfg["min_market_cap_b"]:
            return False, metrics

        # 成交量
        avg_vol = hist_1y["Volume"].mean()
        metrics["avg_volume"] = int(avg_vol)
        if avg_vol < cfg["min_avg_volume"]:
            return False, metrics

        # 今日涨幅
        if len(hist_1y) >= 2:
            prev = hist_1y["Close"].iloc[-2]
            curr = hist_1y["Close"].iloc[-1]
            day_chg = (curr - prev) / prev * 100
            metrics["day_change_pct"] = round(day_chg, 2)
        else:
            metrics["day_change_pct"] = 0

        # EPS (trailing)
        try:
            full_info = ticker_obj.info
            eps = full_info.get("trailingEps", None)
            metrics["eps"] = eps
            if eps is not None and eps < cfg["min_eps"]:
                return False, metrics
        except:
            metrics["eps"] = None

        # 均线条件: 收盘价高于 MA25, MA50, MA125
        closes = hist_1y["Close"]
        for period, threshold in zip(cfg["ma_periods"], cfg["ma_thresholds"]):
            if len(closes) < period:
                return False, metrics
            ma = closes.rolling(period).mean().iloc[-1]
            last = closes.iloc[-1]
            pct_above = (last - ma) / ma
            metrics[f"ma{period}"] = round(ma, 2)
            metrics[f"pct_above_ma{period}"] = round(pct_above * 100, 2)
            if pct_above < threshold:
                return False, metrics

        return True, metrics

    except Exception as e:
        print(f"    screener error: {e}")
        return False, {}


def screen_sector(sector, cfg):
    """筛选某板块所有候选股，返回通过的股票列表（按今日涨幅排序）"""
    candidates = SECTOR_STOCKS.get(sector, [])
    print(f"\n🔍 筛选 {sector} ({len(candidates)} 只候选股)...")

    results = []
    for symbol in candidates:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")
            if hist.empty or len(hist) < 130:
                continue

            passed, metrics = passes_screener(ticker, hist, cfg)
            if passed:
                metrics["symbol"] = symbol
                metrics["sector"] = sector
                results.append(metrics)
                print(f"  ✅ {symbol}: 价格${metrics['price']} 今日{metrics['day_change_pct']:+.2f}%")
            else:
                print(f"  ❌ {symbol}: 未通过")
        except Exception as e:
            print(f"  ⚠️ {symbol} 出错: {e}")

    # 按今日涨幅排序
    results.sort(key=lambda x: x.get("day_change_pct", 0), reverse=True)
    return results


# ─────────────────────────────────────────────
# 4. 主流程
# ─────────────────────────────────────────────

def run_screener():
    et_tz = pytz.timezone("America/New_York")
    today = datetime.now(et_tz)
    today_str = today.strftime("%Y-%m-%d")
    weekday = today.weekday()  # 0=Monday, 6=Sunday

    # 周末跳过
    if weekday >= 5:
        print(f"⏭️ 今天是周末 ({today_str})，跳过筛选")
        return None

    print(f"\n{'='*50}")
    print(f"🚀 Stock Screener 开始运行 - {today_str}")
    print(f"{'='*50}\n")

    # Step 1: 找出今日领涨板块
    leading_sectors, sector_perf = get_leading_sectors(top_n=3)

    # Step 2: 只筛选正涨的板块
    leading_sectors = [s for s in leading_sectors if sector_perf.get(s, 0) > 0]
    if not leading_sectors:
        print("⚠️ 今日所有轮动板块均下跌，跳过")
        return None

    # Step 3: 对领涨板块做 screener 筛选
    cfg = SCREENER_CONFIG
    all_passed = []
    for sector in leading_sectors:
        passed = screen_sector(sector, cfg)
        all_passed.extend(passed)

    # Step 4: 全局按今日涨幅排序，取 top_n
    all_passed.sort(key=lambda x: x.get("day_change_pct", 0), reverse=True)
    top_stocks = all_passed[:cfg["top_n"]]

    if not top_stocks:
        print("\n⚠️ 没有股票通过所有筛选条件")
        return None

    # Step 5: 构建报告数据
    report = {
        "date": today_str,
        "generated_at": today.strftime("%Y-%m-%d %H:%M ET"),
        "leading_sectors": {s: sector_perf[s] for s in leading_sectors},
        "sector_performance": sector_perf,
        "screener_config": {
            "min_price": cfg["min_price"],
            "min_market_cap_b": cfg["min_market_cap_b"],
            "min_avg_volume": cfg["min_avg_volume"],
            "min_eps": cfg["min_eps"],
            "ma_conditions": "Close > MA25(0.1%), MA50(0.2%), MA125(0.7%)",
        },
        "top_stocks": top_stocks,
    }

    print(f"\n{'='*50}")
    print(f"🏆 今日 TOP {cfg['top_n']} 强势股:")
    print(f"{'='*50}")
    for i, s in enumerate(top_stocks, 1):
        print(f"  #{i} {s['symbol']} ({s['sector']})")
        print(f"      今日涨幅: {s['day_change_pct']:+.2f}%  价格: ${s['price']}")
        print(f"      均线状态: MA25+{s.get('pct_above_ma25',0):.1f}% / MA50+{s.get('pct_above_ma50',0):.1f}% / MA125+{s.get('pct_above_ma125',0):.1f}%")

    return report


# ─────────────────────────────────────────────
# 5. 保存 JSON 给 GitHub Pages
# ─────────────────────────────────────────────

def save_json(report, path="docs/data/stock_screener.json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 追加历史记录
    history = []
    if os.path.exists(path):
        with open(path, "r") as f:
            existing = json.load(f)
            history = existing.get("history", [])

    # 避免重复日期
    history = [h for h in history if h.get("date") != report["date"]]
    history.insert(0, report)
    history = history[:30]  # 保留最近30天

    output = {
        "latest": report,
        "history": history,
        "updated_at": report["generated_at"],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON 已保存: {path}")


# ─────────────────────────────────────────────
# 6. 推送通知
# ─────────────────────────────────────────────

def build_message(report):
    """构建通知文本（中英双语）"""
    date_str = report["date"]
    sectors_str = "  ".join(
        [f"{s}({v:+.1f}%)" for s, v in report["leading_sectors"].items()]
    )

    lines = [
        f"📈 **每日强势股筛选** {date_str}",
        f"",
        f"🔄 今日领涨板块: {sectors_str}",
        f"",
        f"🏆 TOP 强势股 (均线多头 + 大盘股):",
    ]

    for i, s in enumerate(report["top_stocks"], 1):
        lines.append(
            f"  #{i} **{s['symbol']}** ({s['sector']})"
            f"  今日 {s['day_change_pct']:+.2f}%  ${s['price']}"
        )
        lines.append(
            f"      MA25+{s.get('pct_above_ma25',0):.1f}%"
            f" | MA50+{s.get('pct_above_ma50',0):.1f}%"
            f" | MA125+{s.get('pct_above_ma125',0):.1f}%"
        )

    lines += [
        f"",
        f"⚠️ 仅供参考，不构成投资建议",
        f"🔗 https://rachelxrz.github.io/daily-brief/",
    ]

    return "\n".join(lines)


def push_serverchan(message, title="📈 每日强势股筛选"):
    """推送到 Server酱"""
    if not SERVERCHAN_KEY:
        print("⏭️ SERVERCHAN_KEY 未设置，跳过")
        return
    url = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"
    resp = requests.post(url, data={"title": title, "desp": message}, timeout=10)
    print(f"📨 Server酱推送: {resp.status_code}")


def push_wxpusher(message, title="📈 每日强势股筛选"):
    """推送到 WxPusher"""
    if not WXPUSHER_TOKEN or not WXPUSHER_UIDS[0]:
        print("⏭️ WXPUSHER 未设置，跳过")
        return
    url = "https://wxpusher.zjiecode.com/api/send/message"
    payload = {
        "appToken": WXPUSHER_TOKEN,
        "content": message,
        "summary": title,
        "contentType": 1,
        "uids": WXPUSHER_UIDS,
    }
    resp = requests.post(url, json=payload, timeout=10)
    print(f"📨 WxPusher推送: {resp.status_code}")


# ─────────────────────────────────────────────
# 7. 入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    report = run_screener()

    if report:
        # 保存 JSON
        save_json(report)

        # 推送通知
        msg = build_message(report)
        push_serverchan(msg)
        push_wxpusher(msg)

        print("\n✅ 全部完成！")
    else:
        print("\n⏭️ 今日无筛选结果，程序正常退出")
