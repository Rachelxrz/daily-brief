#!/usr/bin/env python3
"""
dalio_bubble.py — 达利欧「泡沫指标」预测模型 + 货币收紧扳机 (2026-08-07)

> 操作化 Ray Dalio 的两条招牌框架,和 macro_gate(衰退闸门)、fragility_gate(1987 仓位脆弱)
> 三者互补、互不混票:
>   · macro_gate     → 衰退 / 信用体制(基本面熊市)
>   · fragility_gate → 健康经济里的仓位机械闪崩(Burry / 1987 型)
>   · dalio_bubble   → 泡沫「有多大」+「何时会被戳破」(达利欧 / 债务周期型)
> 详见 notes/1987型崩盘_vs_六因子闸门.md 第 6 节(Burry vs 达利欧框架对比)。

════════════════════════════════════════════════════════════
A) 泡沫指标(达利欧 6 表,各 0–1,均值×100 = 泡沫读数 %)
   1. 估值        巴菲特指标 Wilshire5000/GDP,历史分位            [FRED]
   2. 涨势不可持续 纳指(^NDX)近12月回报,历史分位                  [yfinance]
   3. 新买家/发行热 IPO ETF 近6月回报,历史分位(投机/打新胃口代理)   [yfinance]
   4. 看多情绪     VIX 低位 = 自满 → 1 − VIX 分位                  [yfinance]
   5. 杠杆买入     实现波动极低 → 系统/vol-target 加杠杆代理:1−波动分位 [yfinance]
   6. 远期建设     AI 资本开支超前变现(无免费数据)→ dalio_config.json 人工档 [config]
   达利欧口径:≥80% ≈ 1929/2000 晚期泡沫;60–80% 偏高;<60% 中性/低。

B) 货币收紧「扳机(pin)」—— 达利欧核心:『泡沫在货币收紧前不会真正破裂』
   · 联邦基金利率 FEDFUNDS 近6月变化 ≥ +0.25% → 收紧                [FRED]
   · 10年期实际利率 DFII10 近3月变化 ≥ +0.25% → 收紧                [FRED]
   任一成立 → pin=ON。

判读(达利欧式,区别于择时):
   · 泡沫高 且 无 pin  → 🫧 先融涨(melt-up):分散 + 5–15% 黄金,勿裸空
   · 泡沫高 且 有 pin  → 📌 破裂催化剂已现,风险上升
   · 泡沫不高          → 🟢 读数不高

输出:docs/data.json 的 [today]["dalio_bubble"](网页「结构监控」页)。不推送微信。
不构成投资建议。
"""
import io
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).parent
DATA_FILE   = BASE_DIR / "docs" / "data.json"
CONFIG_FILE = BASE_DIR / "dalio_config.json"

# 泡沫读数分档
BAND_HIGH = 80      # ≥ 晚期泡沫(1929/2000)
BAND_MID  = 60      # ≥ 偏高
# 货币收紧扳机阈值
FFR_RISE_TH  = 0.25     # 联邦基金 6 月上行(个百分点)
REAL_RISE_TH = 0.25     # 10y 实际利率 3 月上行(个百分点)
ISSUANCE_PIN_PCTL = 0.85  # IPO/发行热分位阈值(达利欧 2026「供给针」代理)


def _today_et() -> str:
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")


def _now_cst() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M CST")


def fred(series_id: str, retries: int = 3) -> pd.Series:
    """FRED CSV → 日期索引浮点序列(带重试,容忍读超时)。失败返回空序列。"""
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


def _yf_close(ticker: str, period: str = "max") -> pd.Series:
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


def _pctile(series: pd.Series, value: float) -> float:
    """value 在 series 历史中的分位(0–1)。空/NaN → nan。"""
    s = series.dropna()
    if len(s) < 12 or value is None or (isinstance(value, float) and np.isnan(value)):
        return float("nan")
    return float((s < value).mean())


def _last(s: pd.Series) -> float:
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else float("nan")


def _ret_over(s: pd.Series, days: int) -> float:
    """约 days 个自然日前 → 现在的回报(用最近可得点)。"""
    s = s.dropna()
    if len(s) < 2:
        return float("nan")
    cutoff = s.index[-1] - pd.Timedelta(days=days)
    past = s[s.index <= cutoff]
    base = past.iloc[-1] if len(past) else s.iloc[0]
    return float(s.iloc[-1] / base - 1.0)


def _change_over(s: pd.Series, days: int) -> float:
    """水平序列(利率)约 days 天的变化(个百分点)。"""
    s = s.dropna()
    if len(s) < 2:
        return float("nan")
    cutoff = s.index[-1] - pd.Timedelta(days=days)
    past = s[s.index <= cutoff]
    base = past.iloc[-1] if len(past) else s.iloc[0]
    return float(s.iloc[-1] - base)


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute() -> dict:
    cfg = _load_config()

    # ── 数据 ──
    # 估值用「市值序列」而非价格指数:NCBEILQ027S = 非金融企业股权市值(Z.1,季度,$百万),
    # 与名义 GDP 同为美元口径,构成正当的巴菲特式比率(避免用价格指数除以 GDP 的量纲不匹配)。
    mcap = fred("NCBEILQ027S")         # 非金融企业股权市值($百万)
    gdp = fred("GDP")                  # 名义 GDP(季度,$十亿)
    ffr = fred("FEDFUNDS")             # 联邦基金有效利率(月)
    real10 = fred("DFII10")            # 10 年期 TIPS 实际利率(日)
    ndx = _yf_close("^NDX", "max")
    vix = _yf_close("^VIX", "5y")
    ipo = _yf_close("IPO", "max")      # Renaissance IPO ETF
    if ipo.dropna().empty:
        ipo = _yf_close("ARKK", "max") # 退化代理:投机成长

    # ── 6 表(双语)──
    def g(name, name_en, val_str, score, detail, detail_en, src):
        return {"name": name, "name_en": name_en, "value": val_str,
                "score": None if (score is None or np.isnan(score)) else round(float(score), 2),
                "detail": detail, "detail_en": detail_en, "src": src}

    gauges = []

    # 1) 估值:市值/GDP(非金融企业股权市值 / 名义 GDP),历史分位
    buf_pct = float("nan")
    if not mcap.empty and not gdp.empty:
        gdp_d = gdp.reindex(mcap.index, method="ffill")
        ratio = (mcap / gdp_d).dropna()
        buf_pct = _pctile(ratio, _last(ratio))
    gauges.append(g("估值 · 市值/GDP(非金融企业股权)", "Valuation · Mktcap/GDP (nonfin. equities)",
                    f"{buf_pct*100:.0f}%ile" if not np.isnan(buf_pct) else "—",
                    buf_pct, "股权市值占 GDP 的历史分位,越高越贵",
                    "Equity mktcap-to-GDP historical percentile; higher = richer", "FRED"))

    # 2) 涨势不可持续:纳指近12月回报的历史分位
    r12 = _ret_over(ndx, 365)
    r12_hist = ndx.pct_change(252).dropna() if len(ndx) > 300 else pd.Series(dtype=float)
    ext_pct = _pctile(r12_hist, r12)
    gauges.append(g("涨势 · 纳指近12月回报分位", "Momentum · Nasdaq 12m-return percentile",
                    f"{r12*100:+.0f}%·{ext_pct*100:.0f}%ile" if not np.isnan(ext_pct) else "—",
                    ext_pct, "近一年涨幅在自身历史中的分位,越高越像加速赶顶",
                    "1-yr gain's percentile in its own history; higher = more of a blow-off", "yfinance"))

    # 3) 新买家/发行热:IPO ETF 近6月回报的历史分位
    ipo_r6 = _ret_over(ipo, 182)
    ipo_hist = ipo.pct_change(126).dropna() if len(ipo) > 180 else pd.Series(dtype=float)
    ipo_pct = _pctile(ipo_hist, ipo_r6)
    gauges.append(g("新买家 · 打新/投机胃口(IPO ETF 近6月)", "New buyers · IPO appetite (IPO ETF 6m)",
                    f"{ipo_r6*100:+.0f}%·{ipo_pct*100:.0f}%ile" if not np.isnan(ipo_pct) else "—",
                    ipo_pct, "新发行/投机资产表现的历史分位(新买家入场代理)",
                    "percentile of new-issue/speculative performance (new-buyer proxy)", "yfinance"))

    # 4) 看多情绪:VIX 低 = 自满 → 1 − 分位
    vix_now = _last(vix)
    vix_pct = _pctile(vix, vix_now)
    sent = (1 - vix_pct) if not np.isnan(vix_pct) else float("nan")
    gauges.append(g("情绪 · VIX 自满度(1−VIX分位)", "Sentiment · VIX complacency (1−VIX pct)",
                    f"VIX {vix_now:.0f}·{sent*100:.0f}%" if not np.isnan(sent) else "—",
                    sent, "VIX 越低越自满,情绪越亢奋",
                    "lower VIX = more complacent/euphoric", "yfinance"))

    # 5) 杠杆买入:实现波动极低 → 系统/vol-target 加杠杆(1 − 波动分位)
    lev = float("nan"); rvol_now = float("nan")
    if len(ndx) > 60:
        rvol = ndx.pct_change().rolling(20).std() * np.sqrt(252)
        rvol_now = _last(rvol)
        rvol_pct = _pctile(rvol.tail(756) if len(rvol) > 756 else rvol, rvol_now)
        lev = (1 - rvol_pct) if not np.isnan(rvol_pct) else float("nan")
    gauges.append(g("杠杆 · 低波动加杠杆代理(1−实现波动分位)", "Leverage · low-vol leverage proxy (1−realized-vol pct)",
                    f"{rvol_now*100:.0f}%·{lev*100:.0f}%" if not np.isnan(lev) else "—",
                    lev, "实现波动越低,系统/vol-target 越加杠杆(FINRA保证金无免费源,此为代理)",
                    "lower realized vol → more systematic/vol-target leverage (proxy; no free FINRA margin)", "yfinance·代理"))

    # 6) 远期建设:人工档(AI 资本开支超前)
    fb = cfg.get("forward_buildout", None)
    fb = float(fb) if isinstance(fb, (int, float)) else float("nan")
    gauges.append(g("远期建设 · AI 资本开支超前(人工档)", "Forward buildout · AI capex ahead (manual)",
                    f"{fb*100:.0f}%" if not np.isnan(fb) else "—",
                    fb, "超前建产能/远期购买;无免费数据,dalio_config.json 人工季度校准",
                    "capacity/forward buying ahead of demand; no free data, manual in dalio_config.json", "config·人工"))

    scores = [x["score"] for x in gauges if x["score"] is not None]
    bubble_pct = round(float(np.mean(scores)) * 100) if scores else None
    n_used = len(scores)

    if bubble_pct is None:
        band, band_en, band_color = "数据不足", "Insufficient data", "muted"
    elif bubble_pct >= BAND_HIGH:
        band, band_en, band_color = "晚期泡沫（≥80,1929/2000≈100）", "Late-stage bubble (≥80, 1929/2000≈100)", "red"
    elif bubble_pct >= BAND_MID:
        band, band_en, band_color = "偏高（≥60,2021≈77）", "Elevated (≥60, 2021≈77)", "amber"
    else:
        band, band_en, band_color = "中性 / 低（2024≈52）", "Neutral / low (2024≈52)", "green"

    # 达利欧「领先对」：新买家(表3)+看多情绪(表4) —— 2021 年这两表先于综合读数亮起
    g_newbuyers = gauges[2]["score"]
    g_sentiment = gauges[3]["score"]
    early_warning = bool(g_newbuyers is not None and g_sentiment is not None
                         and g_newbuyers >= 0.75 and g_sentiment >= 0.75)

    # ── 戳破扳机(pin):货币针 + 供给针 ──
    ffr_chg = _change_over(ffr, 182)
    real_chg = _change_over(real10, 92)
    # 货币「已知」当且仅当至少一个利率变化可得;若两者皆缺,货币针状态为「未知」而非「off」
    monetary_known = (not np.isnan(ffr_chg)) or (not np.isnan(real_chg))
    ffr_rising = (not np.isnan(ffr_chg)) and ffr_chg >= FFR_RISE_TH
    real_rising = (not np.isnan(real_chg)) and real_chg >= REAL_RISE_TH
    monetary_on = bool(ffr_rising or real_rising)
    # 达利欧 2026 新增的第二根「针」:发行/IPO 供给潮吸走流动性(用 IPO ETF 6月分位≥85 作代理)
    issuance_hot = (not np.isnan(ipo_pct)) and ipo_pct >= ISSUANCE_PIN_PCTL
    pin_on = bool(monetary_on or issuance_hot)
    pin = {
        "on": pin_on,
        "monetary_on": monetary_on,
        "monetary_known": monetary_known,
        "issuance_on": issuance_hot,
        "ffr_now": None if np.isnan(_last(ffr)) else round(_last(ffr), 2),
        "ffr_chg_6m": None if np.isnan(ffr_chg) else round(ffr_chg, 2),
        "real10_now": None if np.isnan(_last(real10)) else round(_last(real10), 2),
        "real10_chg_3m": None if np.isnan(real_chg) else round(real_chg, 2),
        "ipo_pctile": None if np.isnan(ipo_pct) else round(ipo_pct * 100),
        "detail": "货币针:联邦基金6月≥+0.25% 或 10y实际利率3月≥+0.25%;供给针:IPO/发行热≥85分位(达利欧2026新增)",
    }

    # ── 判读(双语)──
    high = (bubble_pct is not None) and bubble_pct >= BAND_MID
    if not high:
        if early_warning:
            verdict = ("🟡 综合读数尚未到偏高,但『领先对』(新买家+看多情绪)已亮 → 达利欧 2021 式早期预警,"
                       "这两表历史上先于综合读数亮起,值得盯。")
            verdict_en = ("🟡 Composite not yet elevated, but the leading pair (new buyers + sentiment) is lit → "
                          "a Dalio-2021-style early warning; these two led the composite in 2021, worth watching.")
            vcolor = "amber"
        else:
            verdict = "🟢 泡沫读数不高——按达利欧框架,尚无晚期泡沫特征。"
            verdict_en = "🟢 Bubble reading is low — no late-stage bubble features under Dalio's framework."
            vcolor = "green"
    elif not pin_on and not monetary_known:
        # 关键:货币针数据缺失时,不得把「未评估」误报为 melt-up
        verdict = ("🟡 泡沫偏高,但货币针数据缺失(FRED 利率未取到),无法评估是否收紧 → "
                   "暂不给 melt-up 结论,待利率数据恢复后再判。")
        verdict_en = ("🟡 Bubble elevated, but monetary-pin data is missing (FRED rates unavailable), so tightening "
                      "could not be evaluated → withholding the melt-up verdict until rate data returns.")
        vcolor = "amber"
    elif not pin_on:
        verdict = ("🫧 泡沫偏高但货币尚未收紧 → 达利欧:『泡沫在被货币收紧戳破前不会真正破裂』,"
                   "预期先融涨(melt-up)、再回调;应对是分散配置 + 5–15% 黄金,而非裸空。")
        verdict_en = ("🫧 Elevated but money not yet tightening → Dalio: bubbles don't truly pop until pricked by "
                      "tightening; expect a melt-up first, then a correction; response is diversify + 5–15% gold, not naked shorts.")
        vcolor = "amber"
    else:
        pins_cn = "+".join([p for p, on in [("货币针", monetary_on), ("供给针", issuance_hot)] if on])
        pins_en = "+".join([p for p, on in [("monetary", monetary_on), ("issuance", issuance_hot)] if on])
        verdict = (f"📌 泡沫偏高 且 {pins_cn}已现 → 达利欧所述『戳破泡沫的针』出现,"
                   "破裂/去杠杆风险显著上升;分散、降杠杆、重视黄金/硬资产对冲。")
        verdict_en = (f"📌 Elevated and the {pins_en} pin has fired → Dalio's pricking pin is present; "
                      "pop/deleveraging risk rises materially; diversify, cut leverage, favor gold/hard-asset hedges.")
        vcolor = "red"

    note_cn = ("达利欧『泡沫指标』6 表(均值,**近似**其多指标百分位合成)+ 货币针/供给针 · "
               "锚点:1929/2000≈100、2021≈77、2024≈52 分位 · 表3新买家+表4情绪为达利欧「领先对」 · "
               "与衰退闸门/脆弱性侧栏正交 · 市值/GDP、利率来自 FRED,涨势/情绪/杠杆/发行来自 yfinance,远期建设为人工档 · "
               "详见 notes/1987型崩盘_vs_六因子闸门.md · 不构成投资建议")
    note_en = ("Dalio's 6-gauge bubble indicator (mean — an **approximation** of his multi-stat percentile blend) + "
               "monetary/issuance pins · anchors: 1929/2000≈100, 2021≈77, 2024≈52 · gauges 3+4 are Dalio's leading pair · "
               "orthogonal to the recession gate / fragility sidebar · mktcap/GDP & rates from FRED, momentum/sentiment/leverage/issuance from yfinance, forward-buildout is manual · "
               "see notes/1987型崩盘_vs_六因子闸门.md · not investment advice")

    return {
        "date": _today_et(),
        "module": "dalio_inspired_bubble", "fidelity": "mechanism_approximation",
        "updated": _now_cst(),
        "bubble_pct": bubble_pct,
        "gauges_used": n_used,
        "gauges_total": len(gauges),
        "band": band,
        "band_en": band_en,
        "band_color": band_color,
        "gauges": gauges,
        "early_warning": early_warning,
        "pin": pin,
        "verdict": verdict,
        "verdict_en": verdict_en,
        "verdict_color": vcolor,
        "note": note_cn,
        "note_en": note_en,
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
    data[today]["dalio_bubble"] = payload
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"💾 dalio_bubble 已写入 data.json：{today}  泡沫={payload['bubble_pct']}%"
             f"({payload['gauges_used']}/{payload['gauges_total']}表) 扳机={'ON' if payload['pin']['on'] else 'off'} · {payload['band']}")


def run(dry_run: bool = False):
    log.info("=" * 60)
    log.info("🫧 达利欧泡沫指标 + 货币收紧扳机")
    log.info("=" * 60)
    payload = compute()
    log.info(f"  泡沫读数 {payload['bubble_pct']}% · {payload['band']} "
             f"({payload['gauges_used']}/{payload['gauges_total']} 表可用)")
    for x in payload["gauges"]:
        sc = "—" if x["score"] is None else f"{x['score']:.2f}"
        log.info(f"    [{sc}] {x['name']}: {x['value']}")
    p = payload["pin"]
    log.info(f"  货币扳机 {'ON→戳破风险' if p['on'] else 'off'} · FFR6m {p['ffr_chg_6m']} · 实际利率3m {p['real10_chg_3m']}")
    log.info(f"  判读: {payload['verdict']}")
    if dry_run:
        log.info("🧪 dry-run：不写文件")
        return payload
    save(payload)
    log.info("✅ 完成")
    return payload


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="达利欧泡沫指标 + 货币收紧扳机")
    ap.add_argument("--dry-run", action="store_true", help="不写文件,仅打印")
    args = ap.parse_args()
    run(args.dry_run)
