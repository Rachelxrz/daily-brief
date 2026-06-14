#!/usr/bin/env python3
"""
wheel_strategy.py — Wheel Strategy 日报 (v1.1)

v1.0 候选筛选: 从动态 Watchlist 筛选卖 Put 候选，生成 Strike/到期/Premium 建议
v1.1 持仓追踪: 读取 wheel_positions，计算安全/注意/危险状态，生成操作建议

用法:
  python wheel_strategy.py            # 运行 + 推送
  python wheel_strategy.py --dry-run  # 仅打印，不推送不保存
"""

import json
import logging
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

from config import Config
from market_monitor import push_serverchan, push_wecom, push_wxpusher
from save_to_web import save_wheel
from watchlist_manager import get_full_watchlist, load_watchlist

log = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

# ── Screening rules ───────────────────────────────────────────────────────
PUT_RULES = {
    "above_ma20":     True,
    "above_ma50":     True,
    "adx_min":        20,
    "rsi_min":        35,
    "rsi_max":        70,
    "min_iv":         0.20,   # 20%+ IV（放宽以覆盖低波动标的）
    "min_price":      15.0,
    "min_avg_volume": 500_000,
}

MAX_CANDIDATES  = 6    # 最多展示候选数
HIST_PERIOD     = "6mo"
TARGET_DTE      = 30   # 目标到期天数（中心值）
MIN_DTE         = 18
MAX_DTE         = 50


# ── Technical indicators ──────────────────────────────────────────────────

def calc_rsi(closes, period: int = 14) -> float | None:
    import pandas as pd
    if len(closes) < period + 1:
        return None
    s     = pd.Series(closes, dtype=float)
    delta = s.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, 1e-10)
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1)


def calc_adx(df, period: int = 14) -> float | None:
    """Wilder 14-period ADX。df 需含 High / Low / Close 列。"""
    import pandas as pd
    if len(df) < period * 2:
        return None
    high  = df["High"].astype(float)
    low   = df["Low"].astype(float)
    close = df["Close"].astype(float)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)

    up   = high.diff()
    down = -low.diff()
    dm_p = up.where((up > down) & (up > 0), 0.0)
    dm_m = down.where((down > up) & (down > 0), 0.0)

    a = 1 / period
    atr   = tr.ewm(alpha=a, adjust=False).mean()
    di_p  = 100 * dm_p.ewm(alpha=a, adjust=False).mean() / atr
    di_m  = 100 * dm_m.ewm(alpha=a, adjust=False).mean() / atr
    diff  = (di_p - di_m).abs()
    summ  = (di_p + di_m).replace(0, 1e-10)
    adx   = (diff / summ * 100).ewm(alpha=a, adjust=False).mean()
    return round(float(adx.iloc[-1]), 1)


# ── IV & expiry ───────────────────────────────────────────────────────────

def get_iv(ticker_obj, current_price: float) -> float:
    """从 yfinance 期权链获取近月 ATM Put 的隐含波动率，失败返回默认值。"""
    try:
        exps = ticker_obj.options
        if not exps:
            return 0.35
        today = datetime.now(timezone.utc).date()
        best  = min(
            exps,
            key=lambda e: abs((datetime.strptime(e, "%Y-%m-%d").date() - today).days - TARGET_DTE),
        )
        dte = (datetime.strptime(best, "%Y-%m-%d").date() - today).days
        if dte < 7 and len(exps) > 1:
            best = exps[1]
        chain = ticker_obj.option_chain(best)
        puts  = chain.puts
        if puts.empty:
            return 0.35
        liq   = puts[puts["volume"] > 0] if not puts[puts["volume"] > 0].empty else puts
        top   = liq.iloc[(liq["strike"] - current_price).abs().argsort()[:3]]
        iv    = float(top["impliedVolatility"].mean())
        return round(iv, 3) if 0.05 < iv < 3.0 else 0.35
    except Exception:
        return 0.35


def next_option_expiry() -> tuple:
    """返回 (expiry_str, dte) — 离 TARGET_DTE 最近的月度期权到期日（第3个周五）。"""
    today = datetime.now(CST).date()
    candidates = []
    for delta_m in range(4):
        year  = today.year + (today.month + delta_m - 1) // 12
        month = (today.month + delta_m - 1) % 12 + 1
        first = datetime(year, month, 1)
        first_fri = first + timedelta(days=(4 - first.weekday()) % 7)
        third_fri = (first_fri + timedelta(weeks=2)).date()
        dte = (third_fri - today).days
        if dte >= MIN_DTE:
            candidates.append((abs(dte - TARGET_DTE), dte, third_fri))
    candidates.sort()
    _, dte, exp = candidates[0]
    return exp.strftime("%Y-%m-%d"), dte


def suggest_put_strike(price: float) -> float:
    """建议 Put Strike = 当前价 × 92%（OTM ~8%）。"""
    raw = price * 0.92
    if price < 50:
        return round(raw)
    elif price < 200:
        return round(raw / 5) * 5
    else:
        return round(raw / 10) * 10


def suggest_call_strike(price: float) -> float:
    """建议 Call Strike = 当前价 × 108%（OTM ~8%）。"""
    raw = price * 1.08
    if price < 50:
        return round(raw)
    elif price < 200:
        return round(raw / 5) * 5
    else:
        return round(raw / 10) * 10


def estimate_premium(price: float, iv: float, dte: int, otm_pct: float) -> float:
    """简化 BS 估算 OTM 期权 premium（Put 或 Call 均适用）。"""
    t        = max(dte, 1) / 365
    atm_val  = price * iv * math.sqrt(t) * 0.4
    discount = math.exp(-abs(otm_pct) * 8)
    return max(round(atm_val * discount, 2), 0.05)


# ── Screening ─────────────────────────────────────────────────────────────

def screen_candidates(congress_set: set) -> list:
    """遍历完整 Watchlist，返回通过 Put 筛选规则的候选列表（按 IV×ADX 排序）。"""
    tickers   = get_full_watchlist()
    rules     = PUT_RULES
    exp_str, dte = next_option_expiry()
    results   = []

    log.info(f"   🔍 筛选 {len(tickers)} 只标的 (到期: {exp_str}, DTE={dte})")

    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker)
            hist = t.history(period=HIST_PERIOD)
            if hist is None or hist.empty or len(hist) < 55:
                continue

            closes = hist["Close"].dropna().tolist()
            price  = closes[-1]

            if price < rules["min_price"]:
                continue
            avg_vol = float(hist["Volume"].mean())
            if avg_vol < rules["min_avg_volume"]:
                continue

            # MA
            ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
            ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
            if ma20 is None or ma50 is None:
                continue
            if price <= ma20 or price <= ma50:
                continue

            # RSI
            rsi = calc_rsi(closes)
            if rsi is None or not (rules["rsi_min"] <= rsi <= rules["rsi_max"]):
                continue

            # ADX
            adx = calc_adx(hist)
            if adx is None or adx < rules["adx_min"]:
                continue

            # IV
            iv = get_iv(t, price)
            if iv < rules["min_iv"]:
                continue

            strike  = suggest_put_strike(price)
            otm_pct = (price - strike) / price
            premium = estimate_premium(price, iv, dte, otm_pct)

            results.append({
                "ticker":         ticker,
                "price":          round(price, 2),
                "ma20":           round(ma20, 2),
                "ma50":           round(ma50, 2),
                "rsi":            rsi,
                "adx":            adx,
                "iv":             iv,
                "strike":         strike,
                "expiry":         exp_str,
                "dte":            dte,
                "premium":        premium,
                "premium_per_contract": round(premium * 100, 0),
                "congress_signal": ticker in congress_set,
            })
            log.info(f"   ✅ {ticker:6s} ${price:.2f}  MA✅  RSI={rsi}  ADX={adx}  IV={iv:.0%}  Strike=${strike}")

        except Exception as e:
            log.debug(f"   ⏭️ {ticker}: {e}")

    results.sort(key=lambda r: r["iv"] * r["adx"], reverse=True)
    return results[:MAX_CANDIDATES]


# ── Covered Call screening ────────────────────────────────────────────────

def screen_covered_calls() -> list:
    """对 wheel_positions 中的 stock 仓位生成卖 Covered Call 建议。"""
    data    = load_watchlist()
    stocks  = [p for p in data.get("wheel_positions", [])
               if p.get("type") == "stock"
               and p.get("status") == "open"
               and p.get("shares", 0) >= 100]
    if not stocks:
        return []

    # 已有的 short_call 仓位，避免重复建议
    existing_calls = {p["ticker"] for p in data.get("wheel_positions", [])
                      if p.get("type") == "short_call" and p.get("status") == "open"}

    exp_str, dte = next_option_expiry()
    results = []

    log.info(f"   📋 扫描 {len(stocks)} 只股票持仓（Covered Call）")

    for pos in stocks:
        ticker    = pos["ticker"]
        shares    = pos["shares"]
        contracts = shares // 100
        cost      = pos.get("cost_basis", 0)

        already_covered = ticker in existing_calls

        try:
            t     = yf.Ticker(ticker)
            price = t.fast_info.last_price
            if not price:
                hist  = t.history(period="5d")
                price = float(hist["Close"].iloc[-1]) if not hist.empty else None
            if not price:
                continue

            strike   = suggest_call_strike(price)
            iv       = get_iv(t, price)
            otm_pct  = (strike - price) / price
            premium  = estimate_premium(price, iv, dte, otm_pct)
            unreal_pct = round((price - cost) / cost * 100, 1) if cost > 0 else None

            results.append({
                "ticker":               ticker,
                "price":                round(price, 2),
                "shares":               shares,
                "contracts":            contracts,
                "cost_basis":           round(cost, 2),
                "unrealized_pct":       unreal_pct,
                "strike":               strike,
                "expiry":               exp_str,
                "dte":                  dte,
                "premium":              premium,
                "premium_per_contract": round(premium * 100, 0),
                "iv":                   iv,
                "otm_pct":              round(otm_pct * 100, 1),
                "already_covered":      already_covered,
            })
            note = "  ⚠️已有Call" if already_covered else ""
            log.info(f"   ✅ [卖Call] {ticker:6s} ${price:.2f}  Strike=${strike}"
                     f"  OTM+{otm_pct:.0%}  IV={iv:.0%}{note}")

        except Exception as e:
            log.warning(f"   ⚠️ [卖Call] {ticker}: {e}")

    results.sort(key=lambda r: r["iv"] * r["contracts"], reverse=True)
    return results


# ── Position tracking ─────────────────────────────────────────────────────

STATUS_COLORS = {"安全": "🟢", "注意": "🟡", "危险": "🔴"}


def calc_position_status(pos: dict, current_price: float) -> dict:
    """计算单个 Wheel 仓位的状态、距 Strike 距离和操作建议。"""
    strike     = pos["strike"]
    pos_type   = pos.get("type", "short_put").lower()
    expiry_str = pos.get("expiry", "")
    premium    = pos.get("premium_received", 0)
    today      = datetime.now(CST).date()

    try:
        exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        dte      = max((exp_date - today).days, 0)
    except Exception:
        dte = 0

    # 距 Strike 距离（正 = 有利方向）
    if "put" in pos_type:
        dist_pct = (current_price - strike) / current_price * 100  # 正 = 股价高于strike（安全）
    else:
        dist_pct = (strike - current_price) / current_price * 100  # 正 = 股价低于strike（安全）

    # 状态判断
    if dist_pct > 5:
        status = "安全"
    elif dist_pct > 2:
        status = "注意"
    else:
        status = "危险"

    # 操作建议
    if "put" in pos_type:
        if status == "安全" and dte > 7:
            advice = "持有，继续收 Theta"
        elif status == "注意":
            advice = "关注，可在 50% 利润时止盈买回"
        elif status == "危险":
            advice = "警告：接近被行权，考虑 Roll Down 或 Roll Out"
        elif dte <= 5:
            advice = "即将到期，准备下一张或接收股票"
        else:
            advice = "持有观察"
    else:  # covered call / short call
        if dist_pct > 5 and dte > 7:
            advice = "持有，继续收 Theta"
        elif dist_pct <= 2:
            advice = "注意：即将被 Call 走，确认是否接受交割"
        elif premium > 0 and (premium * 100 * pos.get("contracts", 1)) > 0:
            advice = "已接近 50% 利润，可考虑买回锁定"
        else:
            advice = "持有观察"

    return {
        "ticker":      pos["ticker"],
        "type":        pos_type,
        "strike":      strike,
        "expiry":      expiry_str,
        "dte":         dte,
        "price":       round(current_price, 2),
        "dist_pct":    round(dist_pct, 1),
        "status":      status,
        "advice":      advice,
        "premium":     premium,
        "contracts":   pos.get("contracts", 1),
        "opened_date": pos.get("opened_date", ""),
    }


def track_positions() -> list:
    """读取 wheel_positions 中的期权仓位（short_put / short_call），返回状态列表。"""
    data      = load_watchlist()
    positions = [p for p in data.get("wheel_positions", [])
                 if p.get("status") == "open"
                 and p.get("type") in ("short_put", "short_call")]
    if not positions:
        return []

    results = []
    for pos in positions:
        ticker = pos["ticker"]
        try:
            t     = yf.Ticker(ticker)
            price = t.fast_info.last_price
            if not price:
                hist  = t.history(period="5d")
                price = float(hist["Close"].iloc[-1]) if not hist.empty else None
            if price:
                results.append(calc_position_status(pos, price))
                log.info(f"   📊 {ticker} ${price:.2f} → {results[-1]['status']}")
        except Exception as e:
            log.warning(f"   ⚠️ {ticker} 持仓追踪失败: {e}")
    return results


# ── Monthly summary ───────────────────────────────────────────────────────

def monthly_summary() -> dict:
    """统计本月已关闭仓位的 premium 收入（closed/assigned 状态）。"""
    data   = load_watchlist()
    today  = datetime.now(CST)
    month  = today.strftime("%Y-%m")
    earned = 0.0
    closed = 0
    for pos in data.get("wheel_positions", []):
        if pos.get("status") in ("closed", "assigned"):
            opened = pos.get("opened_date", "")
            if opened.startswith(month):
                earned += pos.get("premium_received", 0) * pos.get("contracts", 1) * 100
                closed += 1
    return {"month": month, "premium_earned": round(earned, 0), "positions_closed": closed}


# ── Push message ──────────────────────────────────────────────────────────

def build_push_message(today_str: str, candidates: list, call_candidates: list,
                       positions: list, summary: dict) -> str:
    lines = [f"🎡 Wheel Strategy 日报 {today_str}", ""]

    # 候选
    lines.append("━━━ 📋 今日候选（卖 Put） ━━━")
    if candidates:
        for i, c in enumerate(candidates, 1):
            badge = "  ⭐国会信号" if c["congress_signal"] else ""
            otm_pct = round((1 - c["strike"] / c["price"]) * 100, 1)
            lines.append(
                f"\n{i}. 【卖Put】{c['ticker']}  ${c['price']}{badge}"
            )
            lines.append(
                f"   Strike: ${c['strike']}（OTM {otm_pct}%）  到期: {c['expiry']} ({c['dte']}天)"
                f"  IV: {c['iv']:.0%}"
            )
            lines.append(
                f"   预估 Premium: ~${c['premium']}/股"
                f"（${int(c['premium_per_contract'])}/张）"
            )
            lines.append(
                f"   技术面: MA20✅ MA50✅  ADX:{c['adx']}  RSI:{c['rsi']}"
            )
    else:
        lines.append("  今日无符合条件的候选标的")

    # 持仓
    # 卖Call候选
    lines.append("\n━━━ 📋 今日候选（卖 Covered Call） ━━━")
    if call_candidates:
        for i, c in enumerate(call_candidates, 1):
            covered_note = "  ⚠️ 已有Call仓位" if c.get("already_covered") else ""
            unreal = f"  持仓浮盈: {c['unrealized_pct']:+.1f}%" if c["unrealized_pct"] is not None else ""
            lines.append(
                f"\n{i}. 【卖Call】{c['ticker']}  ${c['price']}{covered_note}"
            )
            lines.append(
                f"   持{c['shares']}股 → 可卖 {c['contracts']} 张{unreal}"
            )
            lines.append(
                f"   Strike: ${c['strike']}（OTM +{c['otm_pct']}%）  到期: {c['expiry']} ({c['dte']}天)"
                f"  IV: {c['iv']:.0%}"
            )
            lines.append(
                f"   预估 Premium: ~${c['premium']}/股"
                f"（${int(c['premium_per_contract'])}/张）"
            )
    else:
        lines.append("  暂无持股仓位（wheel_positions 中添加 type=stock 记录）")

    lines.append("\n━━━ 📊 当前期权仓位 ━━━")
    if positions:
        for p in positions:
            icon    = STATUS_COLORS.get(p["status"], "⚪")
            pt_cn   = "卖Put" if "put" in p["type"] else "卖Covered Call"
            dist_sign = "+" if p["dist_pct"] >= 0 else ""
            lines.append(
                f"\n[{pt_cn}] {p['ticker']} ${p['strike']}  到期 {p['expiry']}  剩 {p['dte']} 天"
            )
            lines.append(
                f"  当前价: ${p['price']}  距Strike: {dist_sign}{p['dist_pct']:.1f}%  {icon}{p['status']}"
            )
            lines.append(f"  建议: {p['advice']}")
    else:
        lines.append("  暂无活跃仓位（在 watchlist.json 的 wheel_positions 中添加）")

    # 月度
    lines.append("\n━━━ 💰 本月 Wheel 收益 ━━━")
    if summary["premium_earned"] > 0:
        lines.append(f"  已收 Premium: ${summary['premium_earned']:.0f}")
        lines.append(f"  已关闭仓位: {summary['positions_closed']} 张")
    else:
        lines.append("  本月暂无已关闭仓位")

    lines.append("\n⚠️ 仅供参考，不构成投资建议 | Premium 为估算值，实际以市场为准")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────

def run_wheel_strategy(dry_run: bool = False) -> dict:
    tz_cst    = timezone(timedelta(hours=8))
    now       = datetime.now(tz_cst)
    today_str = now.strftime("%Y-%m-%d")

    log.info("=" * 60)
    log.info("🎡 Wheel Strategy 任务启动")
    log.info(f"   时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log.info("=" * 60)

    # 国会信号标的集合（用于候选加星）
    congress_set = {s["ticker"] for s in load_watchlist().get("congress_signals", [])}

    log.info("\n📋 步骤 1 — 卖Put候选筛选")
    candidates = screen_candidates(congress_set)
    log.info(f"   → {len(candidates)} 只通过筛选")

    log.info("\n📋 步骤 2 — Covered Call 候选（持股仓位）")
    call_candidates = screen_covered_calls()
    log.info(f"   → {len(call_candidates)} 只生成建议")

    log.info("\n📊 步骤 3 — 期权仓位追踪")
    positions = track_positions()
    log.info(f"   → {len(positions)} 个活跃期权仓位")

    summary = monthly_summary()

    wheel_data = {
        "date":            today_str,
        "candidates":      candidates,
        "call_candidates": call_candidates,
        "positions":       positions,
        "summary":         summary,
    }

    message = build_push_message(today_str, candidates, call_candidates, positions, summary)

    if dry_run:
        log.info("\n🔍 [Dry Run] 推送内容预览：\n" + message)
        log.info("\n🔍 [Dry Run] JSON 数据：\n"
                 + json.dumps(wheel_data, ensure_ascii=False, indent=2))
        return {"message": message, "data": wheel_data}

    log.info("\n📲 推送 Wheel Strategy 日报...")
    if Config.SERVERCHAN_SENDKEY:
        push_serverchan(f"🎡 Wheel Strategy {today_str}", message)
    if Config.WECOM_WEBHOOK_URL:
        push_wecom(message)
    if Config.WXPUSHER_APP_TOKEN:
        push_wxpusher(f"🎡 Wheel Strategy {today_str}", message)

    try:
        save_wheel(wheel_data)
        log.info("🌐 Wheel 数据已保存到网页")
    except Exception as e:
        log.warning(f"⚠️ 网页数据保存失败: {e}")

    log.info("\n" + "=" * 60)
    log.info("✅ Wheel Strategy 任务完成")
    log.info("=" * 60)

    return {"message": message, "data": wheel_data}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_wheel_strategy(dry_run="--dry-run" in sys.argv)
