#!/usr/bin/env python3
"""
research/backtest.py — 统一回测框架 (专项研究课题 Phase 3)

目标:输入「价格序列 + 信号序列」→ 输出**命中率 / 领先时间 / 规避回撤 / Sharpe / vs 基准**,
供各模型(macro_gate 闸门、dalio_bubble 分档、fragility、market_breadth …)插入历史检验。

设计要点(避免常见回测陷阱):
  · **无前视偏差**:信号按 `lag`(默认 1 交易日)滞后执行 —— 今天的信号,明天才据以调仓。
  · **仓位型 & 事件型 两用**:weight∈[0,1] 做「信号择时 vs 买入持有」;二元 risk-off 事件做「规避回撤 + 领先时间」。
  · 纯 pandas/numpy,确定性,可复现;不依赖当前时间。数据(yfinance)只在有网时用,单测用合成序列。

核心 API:
  perf_stats(returns)                         → CAGR / vol / Sharpe / MaxDD
  max_drawdown(equity)                        → 最大回撤(负数)
  backtest(prices, weight, lag=1)             → 策略 vs 买入持有 + 规避回撤 + 敞口 + 换手
  event_eval(prices, risk_off, fwd=63)        → 事件型:命中率 + 领先时间 + 规避回撤
"""
import argparse
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _to_returns(prices: pd.Series) -> pd.Series:
    return prices.astype(float).pct_change().dropna()


def max_drawdown(equity: pd.Series) -> float:
    """权益曲线的最大回撤(负数,如 -0.35)。"""
    equity = equity.dropna()
    if len(equity) < 2:
        return float("nan")
    peak = equity.cummax()
    return float((equity / peak - 1.0).min())


def perf_stats(returns: pd.Series, rf: float = 0.0) -> dict:
    """日收益序列 → CAGR / 年化波动 / Sharpe / MaxDD。"""
    r = returns.dropna()
    n = len(r)
    if n < 2:
        return {"cagr": float("nan"), "vol": float("nan"), "sharpe": float("nan"),
                "maxdd": float("nan"), "days": n}
    equity = (1.0 + r).cumprod()
    cagr = float(equity.iloc[-1] ** (TRADING_DAYS / n) - 1.0)
    vol = float(r.std(ddof=0) * np.sqrt(TRADING_DAYS))
    sharpe = float((r.mean() * TRADING_DAYS - rf) / vol) if vol > 0 else float("nan")
    return {"cagr": round(cagr, 4), "vol": round(vol, 4),
            "sharpe": round(sharpe, 3), "maxdd": round(max_drawdown(equity), 4), "days": n}


def backtest(prices: pd.Series, weight: pd.Series, lag: int = 1, rf_daily: float = 0.0) -> dict:
    """仓位型回测:weight∈[0,1] 的择时策略 vs 买入持有。
    weight 按 lag 滞后执行(无前视);未投资部分按 rf_daily(默认 0)计。"""
    prices = prices.astype(float).dropna()
    rets = prices.pct_change()
    w = weight.reindex(prices.index).ffill().shift(lag).clip(0, 1).fillna(0.0)
    strat_r = (w * rets + (1 - w) * rf_daily).dropna()
    bh_r = rets.dropna()

    strat = perf_stats(strat_r)
    bh = perf_stats(bh_r)
    exposure = float(w.reindex(strat_r.index).mean())          # 平均在市比例
    turnover = float(w.diff().abs().reindex(strat_r.index).sum())  # 累计换手(调仓总量)
    dd_avoided = (round(strat["maxdd"] - bh["maxdd"], 4)
                  if not (np.isnan(strat["maxdd"]) or np.isnan(bh["maxdd"])) else float("nan"))
    return {
        "strategy": strat, "buy_hold": bh,
        "drawdown_avoided_pp": dd_avoided,   # 正=比买入持有少跌多少(百分点,小数)
        "exposure": round(exposure, 3),
        "turnover": round(turnover, 2),
        "excess_cagr": (round(strat["cagr"] - bh["cagr"], 4)
                        if not (np.isnan(strat["cagr"]) or np.isnan(bh["cagr"])) else float("nan")),
    }


def event_eval(prices: pd.Series, risk_off: pd.Series, fwd: int = 63) -> dict:
    """事件型评估:risk_off 为布尔序列(True=模型示警/风险偏离)。
      · 命中率 hit_rate:示警日之后 fwd 交易日的前瞻收益<0 的比例(示警对不对)。
      · 判别力 discrimination:示警日 vs 非示警日的平均前瞻收益之差(越负,防御越有效)。
      · 规避回撤:示警日前瞻窗口内的平均最大回撤 vs 非示警日(示警应更深=提前预警)。
      · 领先时间 lead:每段示警起点 → 其后 fwd 窗口内价格低点的平均交易日数。
    """
    prices = prices.astype(float).dropna()
    ro = risk_off.reindex(prices.index).fillna(False).astype(bool)
    # 前瞻 fwd 日收益
    fwd_ret = prices.shift(-fwd) / prices - 1.0
    # 前瞻窗口内最大回撤(相对起点)
    fwd_dd = pd.Series(index=prices.index, dtype=float)
    vals = prices.values
    for i in range(len(prices)):
        window = vals[i:i + fwd + 1]
        if len(window) >= 2:
            fwd_dd.iloc[i] = float(window.min() / window[0] - 1.0)
    on = ro & fwd_ret.notna()
    off = (~ro) & fwd_ret.notna()
    n_on = int(on.sum())
    hit_rate = float((fwd_ret[on] < 0).mean()) if n_on else float("nan")
    disc = (float(fwd_ret[on].mean() - fwd_ret[off].mean())
            if n_on and off.sum() else float("nan"))
    dd_on = float(fwd_dd[on].mean()) if n_on else float("nan")
    dd_off = float(fwd_dd[off].mean()) if off.sum() else float("nan")

    # 领先时间:每段连续 risk_off 的起点 → 其后 fwd 窗口价格低点的交易日距离
    leads = []
    arr = ro.values
    for i in range(len(arr)):
        if arr[i] and (i == 0 or not arr[i - 1]):        # 一段示警的起点
            window = vals[i:i + fwd + 1]
            if len(window) >= 2:
                leads.append(int(np.argmin(window)))
    lead = float(np.mean(leads)) if leads else float("nan")

    return {
        "n_signals_days": n_on, "n_episodes": len(leads),
        "hit_rate": None if np.isnan(hit_rate) else round(hit_rate, 3),
        "discrimination_fwd": None if np.isnan(disc) else round(disc, 4),   # 负=示警后收益更差(有效)
        "avg_fwd_dd_riskoff": None if np.isnan(dd_on) else round(dd_on, 4),
        "avg_fwd_dd_riskon": None if np.isnan(dd_off) else round(dd_off, 4),
        "avg_lead_days_to_trough": None if np.isnan(lead) else round(lead, 1),
        "fwd_days": fwd,
    }


def _demo():
    """自包含演示:合成一段「涨→崩→复」的价格 + 一个 200日线趋势信号,跑仓位型回测。
    有网时可改为真实 ETF(见 __main__)。"""
    n = 900
    up = np.linspace(100, 200, 400)
    crash = np.linspace(200, 120, 120)
    recover = np.linspace(120, 210, n - 520)
    px = pd.Series(np.concatenate([up, crash, recover]), index=pd.RangeIndex(n)).astype(float)
    ma = px.rolling(200).mean()
    weight = (px > ma).astype(float)     # 价>200线满仓,否则空仓
    print("=== 演示:200日线趋势择时 vs 买入持有(合成价) ===")
    res = backtest(px, weight)
    print("  策略  :", res["strategy"])
    print("  买入持有:", res["buy_hold"])
    print(f"  规避回撤 {res['drawdown_avoided_pp']*100:+.1f}pp · 在市 {res['exposure']*100:.0f}% · 超额CAGR {res['excess_cagr']*100:+.1f}%")
    print("=== 事件型:以 价<200线 为 risk-off ===")
    print("  ", event_eval(px, px < ma, fwd=63))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="统一回测框架(演示)")
    ap.add_argument("--ticker", help="有网时用真实标的跑 200日线择时(如 QQQ);缺省用合成演示")
    args = ap.parse_args()
    if args.ticker:
        import yfinance as yf
        d = yf.download(args.ticker, period="max", auto_adjust=True, progress=False)
        px = (d["Close"] if "Close" in d else d.iloc[:, 0]).dropna()
        if isinstance(px, pd.DataFrame):
            px = px.iloc[:, 0]
        ma = px.rolling(200).mean()
        res = backtest(px, (px > ma).astype(float))
        print(f"=== {args.ticker} 200日线择时 vs 买入持有 ===")
        print("  策略  :", res["strategy"])
        print("  买入持有:", res["buy_hold"])
        print(f"  规避回撤 {res['drawdown_avoided_pp']*100:+.1f}pp · 在市 {res['exposure']*100:.0f}%")
    else:
        _demo()
