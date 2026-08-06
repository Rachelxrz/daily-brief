# -*- coding: utf-8 -*-
"""stock_classifier.py — 个股基本面分档（写入 watchlist.json 的 classification）

档位（纯基本面，回撤/波动/Beta 只作为「特性」记录，供交易层用，不参与定档）：
  · 题材投机 : 当前亏损(trailing<0) 或 上市 < 3年
  · 核心     : 市值≥$50B 且 上市≥8年 且 近3年逐年净利润为正
        - 成长性核心 : 最新年净利润 > 3年前(不看波动)
        - 稳定核心   : 年年为正但未超3年前(持平/下滑) 且 年化波动≤45%(够稳当压舱石)
        - 利润不增长但波动>45%(如 TSLA) → 归 趋势成长(波动型非成长)
  · 趋势成长 : 有盈利但够不到核心(有亏损年 / 市值或年限不够)
  · ETF/基金 : 不适用个股分档

另：稳定核心若「近3年价格年化 < QQQ」→ 移入 Secondary Watchlist(reason=3年回报低于QQQ)，
   即用QQQ替代低效稳定核心；回到QQQ之上再放回。此闸门由本半年任务复查(不走周线MA回归)。

每半年运行一次（.github/workflows/stock_classify.yml），重新确认每只属性；
档位变化写入 watchlist_changelog.json。以后引用某只股票即可查它属于哪一类。
"""
import json
import logging
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

import watchlist_manager as wm

log = logging.getLogger("stock_classifier")

HERE = Path(__file__).resolve().parent
ETF_FLAGS = HERE / "etf_flags.json"

MIN_MCAP_CORE  = 50e9   # 核心：市值 ≥ $50B
MIN_YEARS_CORE = 8      # 核心：上市 ≥ 8年
MIN_YEARS_SPEC = 3      # 题材投机：上市 < 3年
STABLE_MAX_VOL = 45     # 稳定核心：利润不增长时，年化波动 ≤此值 才算「稳定」，否则→趋势成长


def _etf_set():
    try:
        d = json.loads(ETF_FLAGS.read_text(encoding="utf-8"))
        return {k for k, v in d.items() if v is True}
    except Exception:
        return set()


def _annual_ni(t):
    try:
        inc = t.income_stmt
        if inc is None or inc.empty or "Net Income" not in inc.index:
            return None
        return [float(v) for v in inc.loc["Net Income"].values if pd.notna(v)] or None
    except Exception:
        return None


def _trailing_ni(t):
    try:
        q = t.quarterly_income_stmt
        if q is None or q.empty or "Net Income" not in q.index:
            return None
        vals = [float(v) for v in q.loc["Net Income"].values if pd.notna(v)][:4]
        return sum(vals) if vals else None
    except Exception:
        return None


def factors(tk, spy_ret):
    t = yf.Ticker(tk)
    h = t.history(period="max", auto_adjust=True)
    close = h["Close"].dropna()
    if len(close) < 60:
        return None
    years = (close.index[-1] - close.index[0]).days / 365.25
    base  = close[close.index >= "2015-01-01"]
    base  = base if len(base) > 30 else close
    maxdd = float((base / base.cummax() - 1).min()) * 100
    rets  = close.pct_change().dropna()
    rr    = rets[-504:] if len(rets) >= 504 else rets
    vol   = float(rr.std() * np.sqrt(252)) * 100
    beta  = None
    try:
        common = rets.index.intersection(spy_ret.index)
        if len(common) > 120:
            a = rets.loc[common].values; b = spy_ret.loc[common].values
            beta = float(np.cov(a, b)[0, 1] / np.var(b))
    except Exception:
        pass
    mcap = 0
    try:
        mcap = getattr(t.fast_info, "market_cap", 0) or 0
    except Exception:
        pass
    a5  = _annual_ni(t)
    tni = _trailing_ni(t)
    latest_ni = a5[0] if a5 else None
    all_pos = grew = False
    change = None
    if a5 and len(a5) >= 3:
        q = a5[:3]                                   # 最新在前
        all_pos = all(x > 0 for x in q)
        change  = (q[0] / q[2] - 1) if (q[2] and q[2] > 0) else None
        grew    = bool(all_pos and change is not None and change > 0)
    has_fin = (a5 is not None) or (tni is not None)
    r3y = None                                        # 3年价格年化收益(%)
    if len(close) >= 756:
        r3y = round(((float(close.iloc[-1]) / float(close.iloc[-756])) ** (1 / 3) - 1) * 100, 1)
    return dict(years=years, maxdd=round(maxdd, 1), vol=round(vol, 1),
                beta=round(beta, 2) if beta is not None else None, r3y=r3y,
                mcap=mcap, all_pos=all_pos, grew=grew, change=change,
                tni=tni, latest_ni=latest_ni, has_fin=has_fin)


def _profit_tag(f):
    if not f["all_pos"]:
        return "利润未达标"
    if f["grew"]:
        return "利润增长"
    if f["change"] is not None and f["change"] >= -0.15:
        return "利润稳定"
    return "利润下滑"


def classify(f):
    prof = f["tni"] if f["tni"] is not None else f["latest_ni"]
    if (prof is not None and prof < 0) or f["years"] < MIN_YEARS_SPEC:
        return "题材投机"
    if (f["mcap"] >= MIN_MCAP_CORE) and (f["years"] >= MIN_YEARS_CORE) and f["all_pos"]:
        if f["grew"]:
            return "成长性核心"                       # 利润增长 → 成长核心(不看波动)
        # 利润不增长：只有波动够小才算「稳定核心」，波动大的是「波动型非成长」→ 趋势成长
        if f["vol"] is not None and f["vol"] <= STABLE_MAX_VOL:
            return "稳定核心"
        return "趋势成长"
    return "趋势成长"


def _qqq_r3y():
    try:
        c = yf.Ticker("QQQ").history(period="4y", auto_adjust=True)["Close"].dropna()
        if len(c) >= 756:
            return round(((float(c.iloc[-1]) / float(c.iloc[-756])) ** (1 / 3) - 1) * 100, 1)
    except Exception:
        pass
    return None


def build(tickers):
    """返回 (out, qqq_r3)。out[tk] 含 archetype/profit/特性/r3y/beats_qqq。"""
    etfs = _etf_set()
    spy = yf.Ticker("SPY").history(period="3y", auto_adjust=True)["Close"].pct_change().dropna()
    qqq_r3 = _qqq_r3y()
    out = {}
    for tk in tickers:
        if tk in etfs:
            out[tk] = {"archetype": "ETF/基金"}
            continue
        try:
            f = factors(tk, spy)
        except Exception as e:
            log.warning("factors %s 失败: %s", tk, e)
            f = None
        if f is None or not f["has_fin"]:
            out[tk] = {"archetype": "ETF/基金" if (f and not f["has_fin"]) else "无数据"}
            continue
        beats = (f["r3y"] is not None and qqq_r3 is not None and f["r3y"] >= qqq_r3)
        out[tk] = {
            "archetype": classify(f),
            "profit": _profit_tag(f),
            "mcap_b": round(f["mcap"] / 1e9, 1) if f["mcap"] else None,
            "years": round(f["years"], 1),
            "vol": f["vol"], "beta": f["beta"], "maxdd": f["maxdd"],
            "r3y": f["r3y"], "beats_qqq": beats,
        }
    return out, qqq_r3


def run(dry_run: bool = False):
    tickers = sorted(set(wm.get_full_watchlist()) | wm.get_suspended_tickers())
    log.info("个股分档：%d 只", len(tickers))
    new, qqq_r3 = build(tickers)

    data = wm.load_watchlist()
    today = wm._today()
    old = (data.get("classification") or {}).get("tickers", {})
    # 档位变化 → 审计日志
    events = []
    for tk, info in new.items():
        oa = (old.get(tk) or {}).get("archetype")
        na = info.get("archetype")
        if oa and oa != na:
            events.append({"ticker": tk, "action": "reclassify", "source": "classifier",
                           "reason": f"{oa} → {na}"})

    if dry_run:
        from collections import Counter
        print(Counter(v["archetype"] for v in new.values()))
        under = [tk for tk, v in new.items() if v.get("archetype") == "稳定核心" and v.get("beats_qqq") is False]
        print(f"QQQ 3年年化={qqq_r3}%  稳定核心跑输QQQ(将移入Secondary): {under}")
        return new

    data["classification"] = {"updated": today, "qqq_r3y": qqq_r3, "tickers": new}
    wm.save_watchlist(data)
    if events:
        wm.log_watchlist_changes(events)

    # ── 用QQQ替代低效稳定核心：3年年化<QQQ 的稳定核心 → 移入 Secondary（reason=3年回报低于QQQ）──
    data2 = wm.load_watchlist()
    qqq_susp = {s["ticker"] for s in data2.get("suspended", [])
                if isinstance(s, dict) and "QQQ" in (s.get("reason") or "")}
    to_susp, to_res = [], []
    for tk, info in new.items():
        is_qqq_susp = tk in qqq_susp
        underperf = (info.get("archetype") == "稳定核心" and info.get("beats_qqq") is False)
        if underperf and not is_qqq_susp:
            to_susp.append({"ticker": tk, "source": wm.ticker_source(data2, tk),
                            "reason": "3年回报低于QQQ",
                            "detail": f"3年年化 {info.get('r3y')}% < QQQ {qqq_r3}%（不如直接持有QQQ）"})
        elif is_qqq_susp and not underperf:   # 回到QQQ之上 或 已不是稳定核心 → 放回主 watchlist
            to_res.append({"ticker": tk, "reason": "3年回报回到QQQ之上",
                           "detail": f"3年年化 {info.get('r3y')}% ≥ QQQ {qqq_r3}%"})
    if to_susp or to_res:
        wm.apply_suspension(to_susp, to_res)
        log.info("QQQ闸门：移入Secondary %d，放回 %d", len(to_susp), len(to_res))

    log.info("✅ classification 已写入（%d 只，档位变化 %d，QQQ跑输 %d）",
             len(new), len(events), len(to_susp))
    return new


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="个股基本面分档 → watchlist.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
