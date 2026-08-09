#!/usr/bin/env python3
"""
research/backtest_models.py — Phase 3 续:四模型历史重算 + 回测

把 macro_gate / fragility_gate / dalio_bubble / market_breadth 四个模型的
**历史信号序列**(point-in-time,无前视)逐日/逐月重算出来,喂进
`research/backtest.py` 的 `event_eval` / `backtest`,得到每个模型真实的
**命中率 / 判别力 / 规避回撤 / 领先时间 / vs 买入持有**,写入
`research/backtest_results.json`,并把关键指标回填进 `docs/data.json`。

════════════════════════════════════════════════════════════════════
无前视(no look-ahead)—— 本文件的头等纪律:
  · 所有「分位 / 排名」一律用**扩张窗口**(仅用截至当日的历史)或**滚动窗口**,
    绝不用全样本分位(那会把未来信息漏进过去)。
  · 信号在**信号日**取值,`backtest.backtest` 内再按 `lag=1` 滞后执行,
    `event_eval` 亦只看信号日**之后**的前瞻收益 —— 双重防前视。
  · 自检 `--self-test`:对同一段合成价,用 prices[:k] 与 prices[:k+m] 各算一次序列,
    断言前 k 个值**逐一相等**(未来数据不得改变过去的信号)。

数据只在有网(GitHub Actions)时可得;本机沙箱封 Yahoo/FRED,故:
  · 有网:  `python research/backtest_models.py`            → 拉真实数据、算、写 JSON
  · 无网:  `python research/backtest_models.py --self-test` → 合成数据验证无前视与序列构造

阈值全部**从各模型模块 import**(不复制常量,避免与线上漂移)。不构成投资建议。
"""
import argparse
import io
import json
import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent            # research/
REPO_DIR = BASE_DIR.parent                            # repo 根
sys.path.insert(0, str(REPO_DIR))

from research.backtest import event_eval, backtest, perf_stats   # noqa: E402
# 阈值来源:直接引用各模型模块的常量,保证与线上口径一致
import macro_gate as MG            # noqa: E402
import fragility_gate as FG        # noqa: E402
import dalio_bubble as DB          # noqa: E402
import market_breadth as MB        # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

RESULTS_FILE = BASE_DIR / "backtest_results.json"
DATA_FILE = REPO_DIR / "docs" / "data.json"


# ════════════════════════════════════════════════════════════════════
# 数据抓取(与线上模块同源:yfinance + FRED)
# ════════════════════════════════════════════════════════════════════
def _yf_close(ticker: str, period: str = "max") -> pd.Series:
    import yfinance as yf
    try:
        d = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    except Exception as e:
        log.warning(f"  yfinance {ticker} 失败: {str(e)[:60]}")
        return pd.Series(dtype=float)
    if d is None or len(d) == 0:
        return pd.Series(dtype=float)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return d["Close"].dropna() if "Close" in d.columns else pd.Series(dtype=float)


def _yf_many(tickers, period: str = "max") -> pd.DataFrame:
    import yfinance as yf
    try:
        d = yf.download(tickers, period=period, auto_adjust=True, progress=False)
    except Exception as e:
        log.warning(f"  yfinance 批量失败: {str(e)[:60]}")
        return pd.DataFrame()
    if d is None or len(d) == 0:
        return pd.DataFrame()
    if isinstance(d.columns, pd.MultiIndex):
        d = d["Close"]
    else:
        d = d[["Close"]]
        d.columns = [tickers if isinstance(tickers, str) else tickers[0]]
    return d.dropna(how="all")


def _fred(series_id: str, retries: int = 3) -> pd.Series:
    import requests
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = ["date", "val"]
            df["date"] = pd.to_datetime(df["date"])
            df = df[df["val"] != "."]
            df["val"] = df["val"].astype(float)
            return df.set_index("date")["val"]
        except Exception as e:
            log.warning(f"  FRED {series_id} 第 {attempt}/{retries} 次失败: {str(e)[:60]}")
            if attempt < retries:
                time.sleep(3 * attempt)
    return pd.Series(dtype=float)


# ════════════════════════════════════════════════════════════════════
# 无前视工具:扩张 / 滚动分位
# ════════════════════════════════════════════════════════════════════
def expanding_pctile(s: pd.Series, min_periods: int = 12) -> pd.Series:
    """每个点 = 当前值在**截至当日(含)历史**中的分位(<当前值的比例),0–1。
    仅用过去→现在的数据,天然无前视。空窗口(< min_periods)→ NaN。"""
    s = s.astype(float)
    out = np.full(len(s), np.nan)
    vals = s.values
    for i in range(len(vals)):
        if i + 1 < min_periods or np.isnan(vals[i]):
            continue
        hist = vals[: i + 1]
        hist = hist[~np.isnan(hist)]
        if len(hist) >= min_periods:
            out[i] = float((hist[:-1] < vals[i]).mean()) if len(hist) > 1 else 0.5
    return pd.Series(out, index=s.index)


def rolling_pctile(s: pd.Series, window: int, min_count: int = 30) -> pd.Series:
    """每个点 = 当前值在**最近 window 个观测(含当日)**中的分位,0–1。滚动=无前视。"""
    s = s.astype(float)

    def _rank(x):
        x = x[~np.isnan(x)]
        if len(x) < min_count:
            return np.nan
        return float((x[:-1] < x[-1]).mean()) if len(x) > 1 else 0.5

    return s.rolling(window, min_periods=min_count).apply(_rank, raw=True)


def _align(s, grid, ffill: bool = True) -> pd.Series:
    """把序列对齐到 grid;**空/None → grid 上的全 NaN 序列**(而非崩溃)。
    某数据源抓取失败时,让相关因子降级为「缺输入」(→ n_valid 少一项),不拖垮整块。"""
    if s is None or len(s) == 0:
        return pd.Series(np.nan, index=grid)
    return s.reindex(grid, method="ffill" if ffill else None)


def _pub_lag(s, months: int):
    """把 FRED 观测序列按**发布滞后**前移 months 个月:FRED 观测日在期初,而数据要到
    期末后若干周才发布——不前移就会「用到尚未发布的值」(前视)。前移后 reindx+ffill 只在
    (近似)真实可得日之后才看到该值。**注意:修订值仍取最新一版 = 非 ALFRED vintage**,
    历史修订未回滚,列为待办(见 note)。空/None 原样返回。"""
    if s is None or len(s) == 0:
        return s
    return pd.Series(s.values, index=s.index + pd.DateOffset(months=months))


def _rsi_series(s: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI 全序列(每点只用截至当日的数据)。"""
    delta = s.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    dn = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.where(dn != 0, other=up.gt(0).map({True: 100.0, False: 50.0}))
    return rsi


# ════════════════════════════════════════════════════════════════════
# 四模型历史信号序列(逐日/逐月,无前视)——阈值来自各模块常量
# ════════════════════════════════════════════════════════════════════
def macro_gate_series(ndx, vix, curve, baa, unrate, cfnai) -> pd.DataFrame:
    """复刻 macro_gate 的 6 因子 → daily votes + 持续性闸门(与 macro_gate.py 完全同口径)。"""
    grid = ndx.index
    vix = _align(vix, grid)
    curve = _align(curve, grid)
    baa = _align(baa, grid)
    if unrate is not None and len(unrate):
        u3 = unrate.rolling(3, min_periods=1).mean()
        sahm = _align(u3 - u3.rolling(12, min_periods=3).min(), grid)
    else:
        sahm = pd.Series(np.nan, index=grid)
    cfnai3 = _align(cfnai.rolling(3, min_periods=1).mean(), grid) if (cfnai is not None and len(cfnai)) \
        else pd.Series(np.nan, index=grid)

    ma200 = ndx.rolling(200).mean()
    slope_dn = ma200 < ma200.shift(65)
    baa_z = (baa - baa.rolling(756, min_periods=252).mean()) / baa.rolling(756, min_periods=252).std()

    g_vol = (vix > MG.VIX_TH).fillna(False)
    g_curve = (curve < 0).fillna(False)
    g_credit = (baa_z > MG.CREDIT_Z).fillna(False)
    g_sahm = (sahm >= MG.SAHM_TH).fillna(False)
    g_cfnai = (cfnai3 < MG.CFNAI_TH).fillna(False)
    g_trend = ((ndx < ma200) & slope_dn).fillna(False)
    votes = (g_vol.astype(int) + g_curve.astype(int) + g_credit.astype(int)
             + g_sahm.astype(int) + g_cfnai.astype(int) + g_trend.astype(int))

    raw = (votes >= MG.K).to_numpy()
    consec = 0
    gate = np.zeros(len(raw), dtype=bool)
    for i in range(len(raw)):
        consec = consec + 1 if raw[i] else 0
        gate[i] = consec >= MG.PERSIST
    return pd.DataFrame({"votes": votes, "risk_off": pd.Series(gate, index=grid)}, index=grid)


def fragility_series(ndx, vix, vix3m, basket: pd.DataFrame) -> pd.DataFrame:
    """复刻 fragility 5 因子 → daily frag_score(0–5)。分位用**滚动 1 年**(无前视)。"""
    grid = ndx.index
    vix = _align(vix, grid)
    vix3m = _align(vix3m, grid)
    contango = vix3m / vix - 1.0

    rvol = ndx.pct_change().rolling(20).std() * np.sqrt(252)
    rvol_pct = rolling_pctile(rvol, 252, min_count=30)      # 近 1 年滚动分位
    ma200 = ndx.rolling(200).mean()
    stretch = ndx / ma200 - 1.0

    # Burry 篮子 RSI 中位数(逐日,每列各自 RSI 再取横截面中位)
    if basket is not None and not basket.empty:
        rsis = pd.DataFrame({c: _rsi_series(basket[c].reindex(grid).ffill()) for c in basket.columns})
        basket_rsi = rsis.median(axis=1)
    else:
        basket_rsi = pd.Series(np.nan, index=grid)

    f1 = (vix < FG.VIX_LOW).fillna(False)
    f2 = ((contango > FG.CONTANGO_TH) & (vix < FG.VIX_CALM_CAP)).fillna(False)
    f3 = (rvol_pct < FG.RVOL_PCTL).fillna(False)
    f4 = (stretch > FG.STRETCH_TH).fillna(False)
    f5 = (basket_rsi > FG.BASKET_RSI).fillna(False)
    score = (f1.astype(int) + f2.astype(int) + f3.astype(int) + f4.astype(int) + f5.astype(int))
    # 逐因子「输入是否可得」掩码(缺输入 ≠ 不脆弱):供 crisis_windows 判「部分/不可用」,
    # 避免历史早期(如 ^VIX3M<2007 → 期限结构缺)把缺失当 False 拉低分数、却以 /5 呈现。
    n_valid = (vix.notna().astype(int) + contango.notna().astype(int) + rvol_pct.notna().astype(int)
               + stretch.notna().astype(int) + basket_rsi.notna().astype(int))
    return pd.DataFrame({"frag_score": score, "n_valid": n_valid, "n_total": 5,
                         "risk_off_hi": score >= 4,     # 高度脆弱
                         "risk_off_mod": score >= 2},   # 中度及以上
                        index=grid)


def dalio_series(mcap, gdp, ndx, ipo, vix, freq: str = "ME") -> pd.DataFrame:
    """复刻 dalio 泡沫读数(可用表分位取均值×100),**月频 + 扩张分位**(无前视)。
    表:①估值 市值/GDP ②涨势 纳指12m ③新买家 IPO 6m ④情绪 1−VIX ⑤杠杆 1−rvol。
    表6(远期建设)为人工档、无历史序列,历史回测里略去(honest:少一表)。"""
    # 统一到月末频率(泡沫是慢变量,月频既够用又让扩张分位可算)
    ndx_m = ndx.resample(freq).last()
    idx = ndx_m.index

    # ① 估值:市值/GDP(季度→ffill 到月)
    val_ratio = pd.Series(dtype=float)
    if mcap is not None and not mcap.empty and gdp is not None and not gdp.empty:
        gdp_d = gdp.reindex(mcap.index, method="ffill")
        ratio = (mcap / gdp_d).dropna()
        val_ratio = ratio.resample(freq).last().reindex(idx, method="ffill")
    g1 = expanding_pctile(val_ratio.reindex(idx)) if not val_ratio.empty else pd.Series(np.nan, index=idx)

    # ② 涨势:纳指近 12m 回报的扩张分位
    r12 = ndx_m.pct_change(12)
    g2 = expanding_pctile(r12)

    # ③ 新买家:IPO ETF 近 6m 回报的扩张分位
    if ipo is not None and not ipo.empty:
        ipo_m = ipo.resample(freq).last().reindex(idx, method="ffill")
        r6 = ipo_m.pct_change(6)
        g3 = expanding_pctile(r6)
    else:
        g3 = pd.Series(np.nan, index=idx)

    # ④ 情绪:VIX 低=自满 → 1 − 扩张分位
    if vix is not None and not vix.empty:
        vix_m = vix.resample(freq).last().reindex(idx, method="ffill")
        g4 = 1.0 - expanding_pctile(vix_m)
    else:
        g4 = pd.Series(np.nan, index=idx)

    # ⑤ 杠杆:实现波动低 → 1 − 扩张分位(月度实现波动=月内日收益std年化,用日频算再取月末)
    rvol_d = ndx.pct_change().rolling(20).std() * np.sqrt(252)
    rvol_m = rvol_d.resample(freq).last().reindex(idx, method="ffill")
    g5 = 1.0 - expanding_pctile(rvol_m)

    gauges = pd.DataFrame({"g1": g1, "g2": g2, "g3": g3, "g4": g4, "g5": g5}, index=idx)
    reading = (gauges.mean(axis=1, skipna=True) * 100).round()
    n_gauges = gauges.notna().sum(axis=1)
    return pd.DataFrame({"reading": reading, "n_gauges": n_gauges,
                         "risk_off_hi": reading >= DB.BAND_HIGH,    # ≥80 晚期泡沫
                         "risk_off_mid": reading >= DB.BAND_MID},   # ≥60 偏高
                        index=idx)


def monetary_pin_series(ffr, real10, idx, freq: str = "ME") -> pd.Series:
    """达利欧「货币针」历史序列(月频,无前视):联邦基金 6 月变化≥+0.25%
    或 10y 实际利率 3 月变化≥+0.25% → 收紧。DFII10(实际利率)约 2003 起。"""
    pin = pd.Series(False, index=idx)
    if ffr is not None and not ffr.empty:
        ffr_m = ffr.resample(freq).last().reindex(idx, method="ffill")
        ffr_chg = ffr_m - ffr_m.shift(6)                       # 近 6 月变化
        pin = pin | (ffr_chg >= DB.FFR_RISE_TH).fillna(False)
    if real10 is not None and not real10.empty:
        real_m = real10.resample(freq).last().reindex(idx, method="ffill")
        real_chg = real_m - real_m.shift(3)                    # 近 3 月变化
        pin = pin | (real_chg >= DB.REAL_RISE_TH).fillna(False)
    return pin


def breadth_series(spy, rsp, iwm, sectors: pd.DataFrame) -> pd.DataFrame:
    """复刻 market_breadth 3 信号 → daily narrow_score(0–3)。全部 point-in-time。"""
    grid = spy.index
    rsp = _align(rsp, grid)
    iwm = _align(iwm, grid)
    d = MB.TREND_DAYS
    rsp_spy = (rsp / spy)
    iwm_spy = (iwm / spy)
    rsp_chg = rsp_spy / rsp_spy.shift(d) - 1.0
    iwm_chg = iwm_spy / iwm_spy.shift(d) - 1.0
    s1 = rsp_chg < 0     # 等权/市值 3 月变化<0
    s2 = iwm_chg < 0     # 小盘/大盘 3 月变化<0

    # 板块广度:每日站上各自 200 日线的比例(仅在≥MIN_SECTORS 只有效时计)
    above = pd.DataFrame(index=grid)
    valid = pd.DataFrame(index=grid)
    for c in sectors.columns:
        col = _align(sectors[c], grid)
        ma200 = col.rolling(200).mean()
        above[c] = (col > ma200)
        valid[c] = col.notna() & ma200.notna()
    n_valid = valid.sum(axis=1)
    n_above = (above & valid).sum(axis=1)
    breadth = (n_above / n_valid).where(n_valid >= MB.MIN_SECTORS)
    s3 = breadth < MB.BREADTH_WEAK

    s1 = s1.reindex(grid).fillna(False)
    s2 = s2.reindex(grid).fillna(False)
    s3 = s3.reindex(grid).fillna(False)
    score = s1.astype(int) + s2.astype(int) + s3.astype(int)
    # 逐信号「输入是否可得」掩码(RSP≈2003、IWM≈2000、板块广度需≥MIN_SECTORS):
    # 缺输入 ≠ 广度健康,供 crisis_windows 判「部分/不可用」,避免以 /3 呈现被缺失拉低的分。
    n_valid = (rsp_chg.reindex(grid).notna().astype(int) + iwm_chg.reindex(grid).notna().astype(int)
               + breadth.reindex(grid).notna().astype(int))
    return pd.DataFrame({"narrow_score": score, "breadth": breadth, "n_valid": n_valid, "n_total": 3,
                         "risk_off": score >= 2}, index=grid)


# ════════════════════════════════════════════════════════════════════
# 回测:对每个模型的 risk_off 序列跑 event_eval + backtest(去风险=空仓)
# ════════════════════════════════════════════════════════════════════
def _evaluate(name, name_en, price: pd.Series, risk_off: pd.Series, fwd: int, band_note: str) -> dict:
    price = price.astype(float).dropna()
    ro = risk_off.reindex(price.index).ffill().fillna(False).astype(bool)
    ev = event_eval(price, ro, fwd=fwd)
    # 仓位型:示警→空仓(weight=0),否则满仓;对比买入持有,看规避回撤/超额
    weight = (~ro).astype(float)
    bt = backtest(price, weight, lag=1)
    return {
        "model": name, "model_en": name_en, "band": band_note,
        "fwd_days": fwd,
        "n_signal_days": ev["n_signals_days"], "n_episodes": ev["n_episodes"],
        "hit_rate": ev["hit_rate"],
        "discrimination_fwd": ev["discrimination_fwd"],
        "avg_fwd_dd_riskoff": ev["avg_fwd_dd_riskoff"],
        "avg_fwd_dd_riskon": ev["avg_fwd_dd_riskon"],
        "avg_lead_days_to_trough": ev["avg_lead_days_to_trough"],
        "drawdown_avoided_pp": bt["drawdown_avoided_pp"],
        "excess_cagr": bt["excess_cagr"],
        "exposure": bt["exposure"],
        "strat_maxdd": bt["strategy"]["maxdd"], "bh_maxdd": bt["buy_hold"]["maxdd"],
        "strat_sharpe": bt["strategy"]["sharpe"], "bh_sharpe": bt["buy_hold"]["sharpe"],
        "price_start": str(price.index[0].date()), "price_end": str(price.index[-1].date()),
    }


def fetch_all() -> dict:
    """一次性抓取四模型所需的全部原始序列(有网时用)。返回 dict,便于 backtest 与
    crisis_windows 共用同一批数据、同一口径。"""
    log.info("⬇️  抓取数据(yfinance + FRED)…")
    breadth_px = _yf_many(["SPY", "RSP", "IWM"] + MB.SECTORS, "max")
    return {
        "ndx": _yf_close("^NDX", "max"),        # QQQ 等价(macro_gate/fragility 目标)
        "spx": _yf_close("^GSPC", "max"),       # SPY 等价(dalio/breadth 广基)
        "vix": _yf_close("^VIX", "max"),
        "vix3m": _yf_close("^VIX3M", "max"),
        # 日频市场序列(当日可得、不修订)→ 不前移
        "curve": _fred("T10Y3M"), "baa": _fred("BAA10Y"), "real10": _fred("DFII10"),
        # 月度宏观(发布滞后~1月)→ 前移 1 月,避免用到尚未发布的读数
        "unrate": _pub_lag(_fred("UNRATE"), 1), "cfnai": _pub_lag(_fred("CFNAI"), 1),
        "ffr": _pub_lag(_fred("FEDFUNDS"), 1),
        "basket": _yf_many(FG.BURRY_SHORTS, "max"),
        # 季度序列:GDP 首估~季末+1 月(前移 4);Z.1 企业股权市值~季末+2.5 月(前移 5)
        "mcap": _pub_lag(_fred("NCBEILQ027S"), 5), "gdp": _pub_lag(_fred("GDP"), 4),
        "ipo": _yf_close("IPO", "max"),
        "breadth_px": breadth_px,
        "spy": breadth_px["SPY"].dropna() if "SPY" in getattr(breadth_px, "columns", []) else pd.Series(dtype=float),
    }


def build_series(d: dict) -> dict:
    """由 fetch_all() 的原始数据构建四模型的历史信号 DataFrame(供 backtest 与 crisis 复用)。
    绝不复制阈值——全部走各 *_series 构造器,构造器内部再引用各模型模块常量。"""
    out = {}
    if not d["ndx"].empty and not d["vix"].empty and not d["curve"].empty:
        out["macro"] = macro_gate_series(d["ndx"], d["vix"], d["curve"], d["baa"], d["unrate"], d["cfnai"])
    if not d["ndx"].empty and not d["vix"].empty:
        out["frag"] = fragility_series(d["ndx"], d["vix"], d["vix3m"], d["basket"])
    if not d["ndx"].empty:
        db = dalio_series(d["mcap"], d["gdp"], d["ndx"], d["ipo"], d["vix"])
        db["pin"] = monetary_pin_series(d["ffr"], d["real10"], db.index)
        db["risk_off_hi_pin"] = db["risk_off_hi"] & db["pin"]     # 达利欧完整判据:晚期泡沫 + 货币针
        out["dalio"] = db
    bpx = d["breadth_px"]
    if not d["spy"].empty and hasattr(bpx, "columns") and "RSP" in bpx.columns:
        sect = bpx[[c for c in MB.SECTORS if c in bpx.columns]]
        out["breadth"] = breadth_series(d["spy"], bpx["RSP"], bpx.get("IWM", pd.Series(dtype=float)), sect)
    return out


def run_live() -> dict:
    log.info("=" * 64)
    log.info("📊 Phase 3 续:四模型历史重算 + 回测(拉真实数据)")
    log.info("=" * 64)
    d = fetch_all()
    s = build_series(d)
    ndx, spx, spy = d["ndx"], d["spx"], d["spy"]
    results = []

    if "macro" in s:
        mg = s["macro"]
        results.append(_evaluate("macro_gate 六因子闸门", "macro_gate (6-factor)", ndx, mg["risk_off"],
                                 fwd=63, band_note="risk_off = 票数≥2 且连续≥10 交易日"))
        log.info(f"  ✅ macro_gate: 闸门 on {int(mg['risk_off'].sum())} 日 / {len(mg)} 日")

    if "frag" in s:
        fg = s["frag"]
        results.append(_evaluate("fragility 高度脆弱(≥4)", "fragility (score≥4)", ndx, fg["risk_off_hi"],
                                 fwd=63, band_note="risk_off = frag_score≥4"))
        results.append(_evaluate("fragility 中度+(≥2)", "fragility (score≥2)", ndx, fg["risk_off_mod"],
                                 fwd=63, band_note="risk_off = frag_score≥2"))
        log.info(f"  ✅ fragility: ≥4 共 {int(fg['risk_off_hi'].sum())} 日, ≥2 共 {int(fg['risk_off_mod'].sum())} 日")

    if "dalio" in s and not spx.empty:
        db = s["dalio"]
        results.append(_evaluate("dalio 泡沫≥60(偏高)", "dalio bubble≥60", spx, db["risk_off_mid"],
                                 fwd=126, band_note="risk_off = 读数≥60(月频扩张分位)"))
        results.append(_evaluate("dalio 泡沫≥80(晚期)", "dalio bubble≥80", spx, db["risk_off_hi"],
                                 fwd=126, band_note="risk_off = 读数≥80(月频扩张分位)"))
        # 校准实验:达利欧完整判据 = 晚期泡沫(≥80)且货币针 ON —— 测「针」是否补上择时价值
        results.append(_evaluate("dalio 泡沫≥80 且货币针(完整判据)", "dalio ≥80 & monetary pin", spx, db["risk_off_hi_pin"],
                                 fwd=126, band_note="risk_off = 读数≥80 且货币针 ON(达利欧完整判据)"))
        log.info(f"  ✅ dalio: ≥60 {int(db['risk_off_mid'].sum())} 月, ≥80 {int(db['risk_off_hi'].sum())} 月, "
                 f"≥80+针 {int(db['risk_off_hi_pin'].sum())} 月")

    if "breadth" in s:
        bd = s["breadth"]
        results.append(_evaluate("market_breadth 狭窄(≥2)", "breadth narrow≥2", spy, bd["risk_off"],
                                 fwd=63, band_note="risk_off = narrow_score≥2"))
        log.info(f"  ✅ breadth: 狭窄≥2 共 {int(bd['risk_off'].sum())} 日 / {len(bd)} 日")

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ"),
        "note": ("四模型历史信号(分位用扩张/滚动窗口,信号再经 lag=1)喂入 research/backtest.py。risk_off→空仓 vs 买入持有。"
                 "**无前视口径**:月度/季度宏观(UNRATE/CFNAI/FEDFUNDS/GDP/Z.1市值)已按发布滞后前移,不再用到尚未发布的读数;"
                 "**残留 caveat**:仍取最新修订值(非 ALFRED vintage,历史修订未回滚)——头条数字应据此打折看待。"
                 "dalio 略去表6(人工档);breadth 受 ETF 历史(RSP≈2003);fragility 期限结构受 ^VIX3M≈2007 限制。"
                 "判别力(discrimination)负=示警后收益更差=有效。不构成投资建议。"),
        "note_en": ("Historical model signals (expanding/rolling-window percentiles, signal lagged 1 day) fed into research/backtest.py. "
                    "risk_off→cash vs buy-hold. **No-look-ahead**: monthly/quarterly macro (UNRATE/CFNAI/FEDFUNDS/GDP/Z.1 mktcap) is shifted by "
                    "publication lag so no value is used before its release; **remaining caveat**: latest-revised values are still used (not ALFRED "
                    "vintage; historical revisions not rolled back) — headline figures should be read with that discount. dalio omits gauge 6 (manual); "
                    "breadth limited by ETF history (RSP≈2003); fragility term-structure limited by ^VIX3M≈2007. Negative discrimination = effective. Not advice."),
        "models": results,
    }
    return payload


def save_results(payload: dict):
    RESULTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"💾 写入 {RESULTS_FILE.relative_to(REPO_DIR)}({len(payload['models'])} 个模型结果)")
    # 回填一份精简版进 docs/data.json 供网页展示(不覆盖其它 key)
    data = {}
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["backtest_results"] = payload
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("💾 已回填 docs/data.json['backtest_results']")


# ════════════════════════════════════════════════════════════════════
# 自检:合成数据验证「无前视」与序列构造(沙箱无网时用)
# ════════════════════════════════════════════════════════════════════
def self_test():
    log.info("🧪 self-test:合成数据验证无前视 + 序列构造")
    rng = pd.date_range("2000-01-03", periods=1400, freq="B")
    # 合成一段「涨→崩→复」纳指
    up = np.linspace(1000, 4000, 700); crash = np.linspace(4000, 2200, 200); rec = np.linspace(2200, 5000, 500)
    ndx = pd.Series(np.concatenate([up, crash, rec]), index=rng).astype(float)

    # 1) expanding_pctile 无前视:前缀不变性
    full = expanding_pctile(ndx)
    k = 900
    pref = expanding_pctile(ndx.iloc[:k])
    assert np.allclose(full.iloc[:k].dropna().values,
                       pref.reindex(full.index[:k]).dropna().values, equal_nan=False), "expanding_pctile 前视!"
    log.info("  ✅ expanding_pctile 前缀不变(未来数据不改变过去分位)")

    # 2) rolling_pctile 无前视:同理
    fr = rolling_pctile(ndx, 252)
    pr = rolling_pctile(ndx.iloc[:k], 252)
    assert np.allclose(fr.iloc[:k].dropna().tail(50).values,
                       pr.dropna().tail(50).values, equal_nan=False), "rolling_pctile 前视!"
    log.info("  ✅ rolling_pctile 前缀不变")

    # 3) breadth 序列前缀不变(整条信号管线的无前视回归)
    spy = ndx / 10.0
    rsp = spy * (1 + np.linspace(0, -0.1, len(spy)))     # 等权相对走弱
    iwm = spy * (1 + np.linspace(0, -0.15, len(spy)))
    sect = pd.DataFrame({f"XL{c}": spy * (1 + np.linspace(0, v, len(spy)))
                         for c, v in zip("KFEVIYPUBRC", np.linspace(-0.2, 0.2, 11))}, index=spy.index)
    full_b = breadth_series(spy, rsp, iwm, sect)["narrow_score"]
    pref_b = breadth_series(spy.iloc[:k], rsp.iloc[:k], iwm.iloc[:k], sect.iloc[:k])["narrow_score"]
    assert (full_b.iloc[:k].values == pref_b.values).all(), "breadth 序列前视!"
    log.info("  ✅ breadth 序列前缀不变")

    # 4) 端到端:把一个「价<200线」信号喂 _evaluate,应得规避回撤>0
    ma = ndx.rolling(200).mean()
    ro = (ndx < ma)
    res = _evaluate("synthetic", "synthetic", ndx, ro, fwd=63, band_note="test")
    assert res["drawdown_avoided_pp"] is not None
    assert res["discrimination_fwd"] is not None and res["discrimination_fwd"] < 0, res
    log.info(f"  ✅ 端到端 _evaluate:判别力 {res['discrimination_fwd']}(负=有效)· "
             f"规避回撤 {res['drawdown_avoided_pp']}")

    log.info("🎉 self-test 全过")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="四模型历史重算 + 回测(Phase 3 续)")
    ap.add_argument("--self-test", action="store_true", help="合成数据验证无前视(无网时用)")
    ap.add_argument("--dry-run", action="store_true", help="拉数算但不写文件")
    args = ap.parse_args()
    if args.self_test:
        self_test()
    else:
        payload = run_live()
        for m in payload["models"]:
            log.info(f"  · {m['model']}: 命中率={m['hit_rate']} 判别力={m['discrimination_fwd']} "
                     f"规避回撤={m['drawdown_avoided_pp']} 领先={m['avg_lead_days_to_trough']}日 "
                     f"敞口={m['exposure']} [{m['price_start']}→{m['price_end']}]")
        if not args.dry_run:
            save_results(payload)
