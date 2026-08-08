#!/usr/bin/env python3
"""
market_breadth.py — 市场广度 / 集中度信号 (专项研究课题 Phase 2:框架化建模)

> 把多位分析师共用的「内部结构 / 集中度 / 拥挤」方法**可计算化**,只用流动 ETF:
>   · Hussman —「市场内部结构一致性」(trend uniformity)
>   · Slok / Kolanovic —「前十大集中度、涨势变窄」
>   · Burry —「拥挤、广度差 = 反转时更脆」
> 与三体制模型互补:广度差 = 内部结构弱 → 印证 fragility_gate(B 仓位)与 dalio_bubble 的泡沫内部(A 估值)。
> 不发买卖信号,只量化「涨势有多窄」。

信号(均自流动 ETF,yfinance):
  1. 等权 vs 市值权重  RSP/SPY 比率近 ~3 月趋势   下行=集中/变窄
  2. 小盘 vs 大盘      IWM/SPY 比率近 ~3 月趋势   下行=市场变窄
  3. 板块广度         11 个 SPDR 板块站上各自 200 日线的比例   低=广度差

狭窄计分 narrow_score(0–3,越高越窄/越脆):三条各命中记 1。
输出:docs/data.json 的 [today]["market_breadth"](网页「结构监控」页)。不推送微信。不构成投资建议。
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

BASE_DIR  = Path(__file__).parent
DATA_FILE = BASE_DIR / "docs" / "data.json"

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
TREND_DAYS = 63          # ~3 个月交易日
BREADTH_WEAK = 0.50      # 站上200日线比例 < 50% = 广度差


def _today_et() -> str:
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")


def _now_cst() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M CST")


def _dl(tickers, period="2y") -> pd.DataFrame:
    """批量下载收盘价 → DataFrame(列=ticker)。整体/个别失败 → 空/缺列。"""
    try:
        d = yf.download(tickers, period=period, auto_adjust=True, progress=False)
    except Exception as e:
        log.warning(f"  下载失败: {str(e)[:80]}")
        return pd.DataFrame()
    if d is None or len(d) == 0:
        return pd.DataFrame()
    if isinstance(d.columns, pd.MultiIndex):
        d = d["Close"]
    else:
        d = d[["Close"]]
        d.columns = [tickers if isinstance(tickers, str) else tickers[0]]
    return d.dropna(how="all")


def _col(df, name) -> pd.Series:
    if isinstance(df, pd.DataFrame) and name in df.columns:
        return df[name].dropna()
    return pd.Series(dtype=float)


def _ratio_trend(a: pd.Series, b: pd.Series, days: int) -> float:
    """比率 a/b 近 days 交易日的变化率;数据不足 → nan。"""
    if len(a) < days + 5 or len(b) < days + 5:
        return float("nan")
    r = (a / b.reindex(a.index, method="ffill")).dropna()
    if len(r) < days + 1:
        return float("nan")
    return float(r.iloc[-1] / r.iloc[-1 - days] - 1.0)


def compute() -> dict:
    px = _dl(["SPY", "RSP", "IWM"] + SECTORS, period="2y")

    spy, rsp, iwm = _col(px, "SPY"), _col(px, "RSP"), _col(px, "IWM")
    rsp_spy = _ratio_trend(rsp, spy, TREND_DAYS)      # 等权 vs 市值权重
    iwm_spy = _ratio_trend(iwm, spy, TREND_DAYS)      # 小盘 vs 大盘

    # 板块广度:站上各自 200 日线的比例
    above, total = 0, 0
    for s in SECTORS:
        c = _col(px, s)
        if len(c) >= 200:
            total += 1
            ma200 = float(c.rolling(200).mean().iloc[-1])
            if not np.isnan(ma200) and float(c.iloc[-1]) > ma200:
                above += 1
    breadth = (above / total) if total else float("nan")

    def sig(name, name_en, val, weak, detail, detail_en):
        return {"name": name, "name_en": name_en, "value": val, "weak": bool(weak),
                "detail": detail, "detail_en": detail_en}

    s1_weak = (not np.isnan(rsp_spy)) and rsp_spy < 0
    s2_weak = (not np.isnan(iwm_spy)) and iwm_spy < 0
    s3_weak = (not np.isnan(breadth)) and breadth < BREADTH_WEAK

    signals = [
        sig("等权/市值 RSP÷SPY 近3月", "Equal/cap RSP÷SPY 3m",
            f"{rsp_spy*100:+.1f}%" if not np.isnan(rsp_spy) else "—", s1_weak,
            "下行=涨势集中在权重股、变窄", "falling = gains concentrating in mega-caps, narrowing"),
        sig("小盘/大盘 IWM÷SPY 近3月", "Small/large IWM÷SPY 3m",
            f"{iwm_spy*100:+.1f}%" if not np.isnan(iwm_spy) else "—", s2_weak,
            "下行=小盘落后、市场变窄", "falling = small-caps lag, market narrowing"),
        sig("板块广度(站上200日线)", "Sector breadth (above 200-DMA)",
            f"{above}/{total}={breadth*100:.0f}%" if not np.isnan(breadth) else "—", s3_weak,
            f"<{BREADTH_WEAK*100:.0f}% = 广度差", f"<{BREADTH_WEAK*100:.0f}% = weak breadth"),
    ]
    # 只在有数据的信号里计分(避免缺数据被当成健康)
    scored = [s for s in signals if s["value"] != "—"]
    narrow_score = sum(1 for s in scored if s["weak"])
    n_used = len(scored)

    if n_used == 0:
        color, verdict, verdict_en = "muted", "数据不足,广度未评估。", "Insufficient data; breadth not evaluated."
    elif narrow_score >= 2:
        color = "red"
        verdict = "🔴 市场狭窄 / 内部结构弱——涨势集中在少数股,反转时更脆(印证 fragility 与泡沫内部)。"
        verdict_en = "🔴 Narrow market / weak internals — gains concentrated in a few names, more fragile on reversal (corroborates fragility & bubble internals)."
    elif narrow_score == 1:
        color = "amber"
        verdict = "🟡 广度中性偏弱——部分变窄信号亮起,留意内部结构。"
        verdict_en = "🟡 Breadth neutral-to-weak — some narrowing signals lit; watch internals."
    else:
        color = "green"
        verdict = "🟢 广度健康——普涨、内部结构稳。"
        verdict_en = "🟢 Healthy breadth — broad participation, stable internals."

    return {
        "date": _today_et(),
        "updated": _now_cst(),
        "narrow_score": narrow_score,
        "signals_used": n_used,
        "signals_total": len(signals),
        "breadth_pct": None if np.isnan(breadth) else round(breadth * 100),
        "color": color,
        "signals": signals,
        "verdict": verdict,
        "verdict_en": verdict_en,
        "note": ("市场广度/集中度信号(RSP÷SPY、IWM÷SPY、板块200日线广度)· 操作化 Hussman 内部结构 / Slok·Kolanovic 集中度 / Burry 拥挤 · "
                 "与三体制正交,印证 fragility(B)与 dalio_bubble 内部(A)· 仅流动 ETF · 不构成投资建议"),
        "note_en": ("Breadth/concentration signal (RSP÷SPY, IWM÷SPY, sector 200-DMA breadth) — operationalizes Hussman internals / Slok·Kolanovic concentration / Burry crowding · "
                    "orthogonal to the three regimes, corroborates fragility (B) and dalio_bubble internals (A) · liquid ETFs only · not investment advice"),
    }


def save(payload: dict):
    data = {}
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    today = payload["date"]
    data.setdefault(today, {})
    data[today]["updated"] = payload["updated"]
    data[today]["market_breadth"] = payload
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"💾 market_breadth 已写入 data.json：{today}  狭窄计分={payload['narrow_score']}/{payload['signals_used']} · {payload['color']}")


def run(dry_run: bool = False):
    log.info("=" * 60)
    log.info("📐 市场广度 / 集中度信号 (Phase 2)")
    log.info("=" * 60)
    payload = compute()
    log.info(f"  狭窄计分 {payload['narrow_score']}/{payload['signals_used']} · {payload['verdict']}")
    for s in payload["signals"]:
        log.info(f"    {'⚠️' if s['weak'] else '·'} {s['name']}: {s['value']}")
    if dry_run:
        log.info("🧪 dry-run：不写文件")
        return payload
    save(payload)
    log.info("✅ 完成")
    return payload


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="市场广度/集中度信号")
    p.add_argument("--dry-run", action="store_true", help="不写文件,仅打印")
    args = p.parse_args()
    run(args.dry_run)
