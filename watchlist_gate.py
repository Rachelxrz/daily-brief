# -*- coding: utf-8 -*-
"""watchlist_gate.py — 周线200MA 暂停/恢复引擎

规则（对 watchlist 全部标的：core_holdings + long_term + screener_signals）：
  · 暂停触发：周线收盘 < 200周MA  → 移出活跃跟踪（不再给买卖信号），记住来源以便恢复。
  · 恢复触发（全部满足）：周线收盘 > 150周MA 且 > 20周MA 且 连续2季度净利润>0且上升。
    —— ETF/无财报标的（GLD/QQQ/COPX/ETHA…）无利润，恢复仅看价格（>150MA 且 >20MA）。
  · 200MA暂停 / 150MA恢复 → 迟滞带，避免反复横跳。

被暂停的标的：均线信号页显示「已暂停」，不给买卖信号；变动写入 watchlist_changelog.json。
每个交易日在 ma_cross_signal 之前运行（见 daily_brief.yml）。
"""
import logging
import numpy as np
import yfinance as yf

import watchlist_manager as wm

log = logging.getLogger("watchlist_gate")

WK_LONG   = 200   # 周线 200MA（暂停闸门）
WK_MID    = 150   # 周线 150MA（恢复闸门·价格）
WK_SHORT  = 20    # 周线 20MA（恢复闸门·价格）


def _weekly_closes(t: yf.Ticker):
    try:
        df = t.history(period="6y", interval="1wk", auto_adjust=True)
    except Exception:
        return None
    if df is None or df.empty or "Close" not in df:
        return None
    cl = df["Close"].dropna().values.astype(float)
    return cl if len(cl) else None


def _profit_2q(t: yf.Ticker) -> dict:
    """最近2季度净利润。ok = 两季都>0 且 环比上升(q0>q1)。has_data=False 表示无财报(如ETF)。"""
    fin = None
    for attr in ("quarterly_income_stmt", "quarterly_financials"):
        try:
            df = getattr(t, attr)
            if df is not None and not df.empty:
                fin = df
                break
        except Exception:
            continue
    if fin is None or fin.empty:
        return {"has_data": False, "ok": False, "q": None}
    try:
        fin = fin.reindex(sorted(fin.columns, reverse=True), axis=1)
    except Exception:
        pass
    row = None
    for k in ("Net Income", "Net Income Common Stockholders",
              "Net Income From Continuing Operation Net Minority Interest",
              "Net Income Continuous Operations", "NetIncome"):
        if k in fin.index:
            row = fin.loc[k]
            break
    if row is None:
        return {"has_data": False, "ok": False, "q": None}
    vals = []
    for v in row.values:
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv == fv:
            vals.append(fv)
        if len(vals) == 2:
            break
    if len(vals) < 2:
        return {"has_data": False, "ok": False, "q": None}
    q0, q1 = vals
    return {"has_data": True, "ok": bool(q0 > 0 and q1 > 0 and q0 > q1),
            "q": [round(q0 / 1e6, 1), round(q1 / 1e6, 1)]}


def _ma(cl, n):
    return float(np.mean(cl[-n:])) if len(cl) >= n else None


def evaluate() -> dict:
    data = wm.load_watchlist()
    suspended = wm.get_suspended_tickers()
    # core_holdings（GLD/QQQ/TLT/WTI 等战略锚仓，无财报）豁免本闸门，只对个股(long_term+screener)生效
    exempt = {(h.get("ticker") if isinstance(h, dict) else h) for h in data.get("core_holdings", [])}
    universe  = sorted((set(wm.get_full_watchlist()) | suspended) - exempt)

    to_suspend, to_resume, skipped = [], [], []
    for tk in universe:
        try:
            t  = yf.Ticker(tk)
            cl = _weekly_closes(t)
            if cl is None:
                skipped.append(tk)
                continue
            close = float(cl[-1])
            ma200 = _ma(cl, WK_LONG)
            ma150 = _ma(cl, WK_MID)
            ma20  = _ma(cl, WK_SHORT)
            is_susp = tk in suspended

            if not is_susp:
                # 活跃 → 是否跌破200周MA
                if ma200 is not None and close < ma200:
                    to_suspend.append({
                        "ticker": tk, "source": wm.ticker_source(data, tk),
                        "reason": "周线跌破200MA",
                        "detail": f"周收{close:.1f} < 200wMA {ma200:.1f}",
                    })
            else:
                # 暂停中 → 是否满足全部恢复条件
                if ma150 is None or ma20 is None:
                    continue
                price_ok = close > ma150 and close > ma20
                prof = _profit_2q(t)
                prof_ok = prof["ok"] if prof["has_data"] else True   # ETF无利润→仅看价格
                if price_ok and prof_ok:
                    pdet = "无财报(仅价格)" if not prof["has_data"] else f"近2季净利{prof['q']}↑"
                    to_resume.append({
                        "ticker": tk,
                        "reason": "回到周线150/20MA上方" + ("且连续2季盈利上升" if prof["has_data"] else ""),
                        "detail": f"周收{close:.1f} >150wMA {ma150:.1f} & >20wMA {ma20:.1f}；{pdet}",
                    })
        except Exception as e:
            log.warning("gate %s 失败: %s", tk, e)
            skipped.append(tk)

    res = wm.apply_suspension(to_suspend, to_resume)
    res["skipped"] = skipped
    return res


def run():
    r = evaluate()
    print(f"🚦 watchlist_gate：暂停 {r['suspended']} | 恢复 {r['resumed']} | 跳过(数据不足) {len(r['skipped'])}只")
    return r


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
