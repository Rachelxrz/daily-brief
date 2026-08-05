# -*- coding: utf-8 -*-
"""板块强弱 · 资金流向面板（真实价格驱动）→ docs/data.json 的 "sector_board" key。

在「📌 市场结构」页、六因子闸门（结果闸门）正下方展示一张结构化表格：
  板块/资产 · 今日% · 3个月% · 年初至今(YTD)% · 相对大盘(RS vs SPY, 3M) · 资金方向

「资金方向（流入/流出）」用**相对大盘强弱**推算（真实资金流数据无免费来源）：
  RS_3M = 该板块3个月涨幅 − SPY 3个月涨幅
  RS ≥ +3% 强势流入 / ≥ 0 流入 / ≤ −3% 明显流出 / < 0 流出 / ≈0 中性。

复用 signal_advisor.get_ohlcv（yfinance, auto_adjust）。不发微信、不联网 LLM。
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from signal_advisor import get_ohlcv

log = logging.getLogger("sector_board")

DOCS_DIR = Path(__file__).resolve().parent / "docs"
DATA_FILE = DOCS_DIR / "data.json"

BENCH = "SPY"

# (ticker, 中文, English, emoji, 类别)  —— 11 大 GICS 板块 + 关键资产
SECTORS = [
    ("XLK",  "科技",        "Technology",        "💻", "sector"),
    ("XLC",  "通信服务",     "Communication",     "📡", "sector"),
    ("XLY",  "非必需消费",   "Cons. Discretionary","🛍️", "sector"),
    ("XLP",  "必需消费",     "Cons. Staples",     "🧴", "sector"),
    ("XLV",  "医疗保健",     "Health Care",       "💊", "sector"),
    ("XLF",  "金融",        "Financials",        "🏦", "sector"),
    ("XLI",  "工业",        "Industrials",       "🏭", "sector"),
    ("XLE",  "能源",        "Energy",            "⚡", "sector"),
    ("XLU",  "公用事业",     "Utilities",         "🔌", "sector"),
    ("XLRE", "房地产",       "Real Estate",       "🏠", "sector"),
    ("XLB",  "材料",        "Materials",         "🧱", "sector"),
    ("SMH",  "半导体",       "Semiconductors",    "🔬", "asset"),
    ("GLD",  "黄金",        "Gold",              "🥇", "asset"),
    ("TLT",  "长期国债",     "Long Treasuries",   "🏛️", "asset"),
]


def _now_cst() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M CST")


def _today_et() -> str:
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")


def _pct(new: float, old: float):
    if old is None or old == 0 or new is None or (isinstance(old, float) and np.isnan(old)):
        return None
    return round((new / old - 1) * 100, 2)


def _metrics(ticker: str):
    """返回 dict(last, day_pct, m3_pct, ytd_pct, asof) 或 None。"""
    df = get_ohlcv(ticker, period="2y")
    if df is None or df.empty or "Close" not in df:
        return None
    close = df["Close"].dropna()
    if len(close) < 2:
        return None
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    # 3 个月 ≈ 63 个交易日
    m3_base = float(close.iloc[-64]) if len(close) >= 64 else None
    # YTD：以「上一年最后一个交易日」收盘为基准
    cur_year = close.index[-1].year
    prior = close[close.index.year < cur_year]
    ytd_base = float(prior.iloc[-1]) if len(prior) else None
    return {
        "last": round(last, 2),
        "day_pct": _pct(last, prev),
        "m3_pct": _pct(last, m3_base),
        "ytd_pct": _pct(last, ytd_base),
        "asof": close.index[-1].strftime("%Y-%m-%d"),
    }


def _flow(rs):
    """由相对大盘强弱 RS_3M 推算资金方向标签。"""
    if rs is None:
        return {"cn": "数据不足", "en": "n/a", "tone": "muted", "icon": "⚪"}
    if rs >= 3.0:
        return {"cn": "强势流入", "en": "Strong inflow", "tone": "green", "icon": "🟢"}
    if rs >= 0.0:
        return {"cn": "流入",     "en": "Inflow",        "tone": "green", "icon": "🟢"}
    if rs <= -3.0:
        return {"cn": "明显流出", "en": "Heavy outflow",  "tone": "red",   "icon": "🔴"}
    return {"cn": "流出", "en": "Outflow", "tone": "red", "icon": "🔴"}


def build() -> dict:
    bench = _metrics(BENCH)
    spy_m3 = bench["m3_pct"] if bench else None

    rows = []
    for tk, cn, en, emoji, kind in SECTORS:
        try:
            mt = _metrics(tk)
        except Exception as e:
            log.warning("sector %s 取数失败: %s", tk, e)
            mt = None
        if not mt:
            rows.append({"ticker": tk, "cn": cn, "en": en, "emoji": emoji,
                         "kind": kind, "last": None, "day_pct": None,
                         "m3_pct": None, "ytd_pct": None, "rs_m3": None,
                         "flow": _flow(None), "asof": None})
            continue
        rs = round(mt["m3_pct"] - spy_m3, 2) if (mt["m3_pct"] is not None and spy_m3 is not None) else None
        rows.append({
            "ticker": tk, "cn": cn, "en": en, "emoji": emoji, "kind": kind,
            "last": mt["last"], "day_pct": mt["day_pct"],
            "m3_pct": mt["m3_pct"], "ytd_pct": mt["ytd_pct"],
            "rs_m3": rs, "flow": _flow(rs), "asof": mt["asof"],
        })

    # 相对强弱降序（最强流入在上）；无数据置底
    rows.sort(key=lambda r: (r["rs_m3"] is None, -(r["rs_m3"] if r["rs_m3"] is not None else 0)))

    return {
        "date": _today_et(),
        "updated": _now_cst(),
        "benchmark": {"ticker": BENCH, "day_pct": bench["day_pct"] if bench else None,
                       "m3_pct": spy_m3, "ytd_pct": bench["ytd_pct"] if bench else None,
                       "asof": bench["asof"] if bench else None},
        "note_cn": "资金方向按「相对大盘（SPY）3个月强弱」推算：跑赢=流入，跑输=流出（无免费实时资金流数据）。",
        "note_en": "Fund direction is inferred from 3-month relative strength vs SPY (outperform=inflow, underperform=outflow); no free real fund-flow feed.",
        "sectors": rows,
    }


def save_web(payload: dict):
    data = {}
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    today = payload["date"]
    data.setdefault(today, {})
    data[today]["updated"] = payload["updated"]
    data[today]["sector_board"] = payload
    DOCS_DIR.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sum(1 for r in payload["sectors"] if r["last"] is not None)
    log.info("💾 sector_board 已写入 data.json：%s  有效 %d/%d", today, n, len(payload["sectors"]))


def run(dry_run: bool = False):
    payload = build()
    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload
    save_web(payload)
    return payload


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
