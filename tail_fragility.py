#!/usr/bin/env python3
"""
fragility_gate.py — 「脆弱性 / 拥挤度」侧栏 + 崩盘性质诊断 (2026-08-07)

> 与 macro_gate.py(六因子衰退闸门)**正交**。macro_gate 测「衰退 / 信用体制」;
> 本模块测「健康经济里的仓位机制闪崩」风险——即 Burry / 1987-type 那类事件。
> 两块并列显示、**互不混票**。本模块**不发出买卖信号**,只量化「干柴多不多」。
> 详见 notes/1987型崩盘_vs_六因子闸门.md。

────────────────────────────────────────────────────────────
A) 脆弱性 / 拥挤度评分(盘前「干柴」计量,0–5,越高越脆)
   1. VIX 绝对低位        VIX < 14           → 波动卖方舒适、复杂性积累
   2. 期限结构极度平静    VIX3M/VIX-1 > 12% 且 VIX<16 → vol-target 加杠杆的温床
   3. 实现波动极低分位    QQQ 20日实现波动处于近1年最低 20% 分位
   4. 动量拉伸            QQQ 收盘高于 200日线 > 12%
   5. Burry 篮子拥挤      做空篮子 RSI(14) 中位数 > 65(拥挤在正好要出事的票上)
   注:高分 ≠ 卖出。它只说明「一旦有火星,火会烧多大」,不预测火星何时来。

B) 崩盘性质诊断(答「即便没预判到,崩的当天能否知道是什么性质?」= 能)
   当 SPY/QQQ 单日 <= -3% 触发;平日仅显示「当前盘面若今日崩会偏向哪种」。
   读同日盘面 6 个 tell,给「机械/仓位型(1987)」vs「基本面/衰退型」打分:
     · VIX 期限结构是否骤然 backwardation
     · 长债 TLT 是否避险上涨(涨=衰退避险 / 平或跌=被迫抛售=机械)
     · 高收益信用 HYG 是否超跌(超跌=信用走坏=衰退)
     · 黄金 GLD 是否跟跌(跟跌=流动性挤兑=机械)
     · 防御 vs 周期(XLP/XLU vs XLK)是否强分化(强分化=轮动=衰退)
     · 衰退闸门当日票数(0票=全绿里崩=机械 / ≥2=衰退语境)

输出:docs/data.json 的 [today]["fragility_gate"](网页「结构监控」页,紧贴体制闸门下方)。
不推送微信(遵循「微信只推新闻」规则)。
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

# ── A) 脆弱性阈值 ──────────────────────────────────────────
VIX_LOW      = 14.0      # 绝对低位
CONTANGO_TH  = 0.12      # (VIX3M/VIX-1) 深度 contango
VIX_CALM_CAP = 16.0      # 期限结构因子额外要求 VIX 够低
RVOL_PCTL    = 0.20      # 实现波动分位下限
STRETCH_TH   = 0.12      # QQQ 高于 200日线的拉伸
BASKET_RSI   = 65.0      # 做空篮子拥挤 RSI

# ── B) 崩盘诊断阈值 ────────────────────────────────────────
CRASH_TH     = -0.03     # SPY/QQQ 单日 <= -3% 触发正式诊断
HY_BETA      = 0.35      # HYG 对 SPY 的经验 beta(用于判断信用是否超跌)

# Burry 做空篮子(与本组合重叠敞口:NVDA 持仓 + 半导体/AI Watchlist)
BURRY_SHORTS = ["NVDA", "MU", "AVGO", "AMD", "PLTR", "TSLA", "CAT", "AMAT", "SOXX"]


def _today_et() -> str:
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")


def _now_cst() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M CST")


def _dl(tickers, period="2y") -> pd.DataFrame:
    """批量下载收盘价 → DataFrame(列=ticker)。容忍个别/整体失败(返回空 DataFrame)。"""
    try:
        d = yf.download(tickers, period=period, auto_adjust=True, progress=False)
    except Exception as e:
        log.warning(f"  下载失败({tickers if isinstance(tickers, str) else len(tickers)}只): {str(e)[:80]}")
        return pd.DataFrame()
    if d is None or len(d) == 0:
        return pd.DataFrame()
    if isinstance(d.columns, pd.MultiIndex):
        d = d["Close"]
    else:
        d = d[["Close"]]
        d.columns = [tickers if isinstance(tickers, str) else tickers[0]]
    return d.dropna(how="all")


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """安全取列:缺列/空表 → 空 Series(下游 _last/_ret1d 会返回 nan)。"""
    if isinstance(df, pd.DataFrame) and name in df.columns:
        return df[name]
    return pd.Series(dtype=float)


def _rsi(s: pd.Series, n: int = 14) -> float:
    delta = s.diff()
    up = float(delta.clip(lower=0).rolling(n).mean().iloc[-1])
    dn = float((-delta.clip(upper=0)).rolling(n).mean().iloc[-1])
    if np.isnan(up) or np.isnan(dn):
        return float("nan")                     # 窗口不足
    if dn == 0:                                 # 窗口内全涨/全平 → 不能除零
        return 100.0 if up > 0 else 50.0        # 全涨=极度超买=100;全平=50
    return 100 - 100 / (1 + up / dn)


def _last(s: pd.Series):
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else float("nan")


def _ret1d(s: pd.Series) -> float:
    s = s.dropna()
    return float(s.iloc[-1] / s.iloc[-2] - 1.0) if len(s) >= 2 else float("nan")


def compute() -> dict:
    # ── 一次性拉数据 ──
    idx = _dl(["^NDX", "^VIX", "^VIX3M", "SPY", "TLT", "HYG", "LQD", "GLD",
               "IWM", "XLK", "XLP", "XLU"], period="2y")
    basket = _dl(BURRY_SHORTS, period="1y")

    ndx = _col(idx, "^NDX").dropna()
    vix = _last(_col(idx, "^VIX"))
    vix3m = _last(_col(idx, "^VIX3M"))
    contango = (vix3m / vix - 1.0) if (vix and vix3m and not np.isnan(vix) and not np.isnan(vix3m)) else float("nan")

    # 实现波动(20日年化)与其近1年分位
    if len(ndx) >= 21:
        rvol = ndx.pct_change().rolling(20).std() * np.sqrt(252)
        rvol_now = _last(rvol)
        rvol_pct = float((rvol.tail(252) < rvol_now).mean()) if rvol.tail(252).notna().sum() > 30 else float("nan")
    else:
        rvol_now = rvol_pct = float("nan")

    # 动量拉伸(高于 200日线)
    if len(ndx) >= 200:
        ma200_last = float(ndx.rolling(200).mean().iloc[-1])
        stretch = float(ndx.iloc[-1] / ma200_last - 1.0) if not np.isnan(ma200_last) else float("nan")
    else:
        stretch = float("nan")

    # Burry 篮子 RSI 中位数
    rsis = []
    for t in BURRY_SHORTS:
        if t in basket.columns and basket[t].notna().sum() > 30:
            try:
                r = _rsi(basket[t].dropna())
                if np.isfinite(r):              # 排除非有限值,单只 NaN 不得毒化整篮中位数
                    rsis.append(r)
            except Exception:
                pass
    basket_rsi = float(np.median(rsis)) if rsis else float("nan")

    # ── A) 脆弱性因子(True = 更脆,双语) ──
    def frag(name, name_en, val_str, on, detail, detail_en):
        return {"name": name, "name_en": name_en, "value": val_str, "fragile": bool(on),
                "detail": detail, "detail_en": detail_en}

    f1 = (not np.isnan(vix)) and vix < VIX_LOW
    f2 = (not np.isnan(contango)) and contango > CONTANGO_TH and vix < VIX_CALM_CAP
    f3 = (not np.isnan(rvol_pct)) and rvol_pct < RVOL_PCTL
    f4 = (not np.isnan(stretch)) and stretch > STRETCH_TH
    f5 = (not np.isnan(basket_rsi)) and basket_rsi > BASKET_RSI

    factors = [
        frag("VIX 绝对低位", "VIX absolute low", f"{vix:.1f}" if not np.isnan(vix) else "—", f1,
             f"<{VIX_LOW:.0f} 偏脆", f"<{VIX_LOW:.0f} = fragile"),
        frag("期限结构 VIX3M/VIX", "Term structure VIX3M/VIX", f"{contango*100:+.0f}%" if not np.isnan(contango) else "—", f2,
             f"contango>{CONTANGO_TH*100:.0f}% 且 VIX<{VIX_CALM_CAP:.0f} 偏脆",
             f"contango>{CONTANGO_TH*100:.0f}% & VIX<{VIX_CALM_CAP:.0f} = fragile"),
        frag("实现波动分位(1y)", "Realized-vol %ile (1y)", f"{rvol_pct*100:.0f}%ile" if not np.isnan(rvol_pct) else "—", f3,
             f"<{RVOL_PCTL*100:.0f}分位 偏脆(vol-target 加杠杆)",
             f"<{RVOL_PCTL*100:.0f}th %ile = fragile (vol-target leverage)"),
        frag("QQQ 高于 200日线", "QQQ above 200-DMA", f"{stretch*100:+.0f}%" if not np.isnan(stretch) else "—", f4,
             f">{STRETCH_TH*100:.0f}% 偏脆(动量拉伸)", f">{STRETCH_TH*100:.0f}% = fragile (momentum stretch)"),
        frag("Burry 篮子 RSI 中位", "Burry-short basket median RSI", f"{basket_rsi:.0f}" if not np.isnan(basket_rsi) else "—", f5,
             f">{BASKET_RSI:.0f} 偏脆(拥挤)", f">{BASKET_RSI:.0f} = fragile (crowded)"),
    ]
    frag_score = sum(1 for f in factors if f["fragile"])
    if frag_score >= 4:
        frag_color, frag_label, frag_label_en = "red", "🔴 高度脆弱(干柴充足)", "🔴 Highly fragile (ample tinder)"
    elif frag_score >= 2:
        frag_color, frag_label, frag_label_en = "amber", "🟡 中度脆弱", "🟡 Moderately fragile"
    else:
        frag_color, frag_label, frag_label_en = "green", "🟢 低脆弱", "🟢 Low fragility"

    # ── B) 崩盘性质诊断 ──
    spy_r = _ret1d(_col(idx, "SPY"))
    ndx_r = _ret1d(_col(idx, "^NDX"))
    tlt_r = _ret1d(_col(idx, "TLT"))
    hyg_r = _ret1d(_col(idx, "HYG"))
    gld_r = _ret1d(_col(idx, "GLD"))
    xlk_r = _ret1d(_col(idx, "XLK"))
    _def_parts = [r for r in (_ret1d(_col(idx, "XLP")), _ret1d(_col(idx, "XLU"))) if not np.isnan(r)]
    defensive_r = float(np.mean(_def_parts)) if _def_parts else float("nan")
    _eq_parts = [r for r in (spy_r, ndx_r) if not np.isnan(r)]
    worst_eq = float(np.min(_eq_parts)) if _eq_parts else float("nan")

    # 只读「当日」衰退闸门票数(若 macro_gate 当日失败则留空,该 tell 直接省略,
    # 绝不回退到旧日票数——陈旧的 0 或 ≥2 会误导当日崩盘性质判定)
    gate_votes = None
    try:
        data0 = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        g = data0.get(_today_et(), {}).get("macro_gate")
        if g and "votes" in g:
            gate_votes = int(g["votes"])
    except Exception:
        pass

    # 每个 tell 给出倾向:"mech"(机械/仓位型) / "reco"(衰退/基本面型) / "neutral"(双语)
    tells = []

    def tell(name, name_en, val, lean, why, why_en, val_en=None):
        tells.append({"name": name, "name_en": name_en, "value": val, "value_en": val_en if val_en is not None else val,
                      "lean": lean, "why": why, "why_en": why_en})

    # 1) VIX 期限结构
    if not np.isnan(contango):
        if contango < -0.05:   # backwardation(前月高于3月)
            tell("VIX 期限结构", "VIX term structure", f"{contango*100:+.0f}% (倒挂)", "stress",
                 "骤然倒挂=急性恐慌,两型都有→看其余 tell 拆分",
                 "sudden backwardation = acute panic; both types show it → split by other tells",
                 val_en=f"{contango*100:+.0f}% (backwardation)")
        else:
            tell("VIX 期限结构", "VIX term structure", f"{contango*100:+.0f}%", "neutral",
                 "尚未倒挂,恐慌未极端", "not yet inverted; panic not extreme")

    # 2) 长债 TLT 反应
    if not np.isnan(tlt_r):
        if tlt_r >= 0.005:
            tell("长债 TLT", "Long bond TLT", f"{tlt_r*100:+.1f}%", "reco",
                 "避险买盘涌入长债=冲着经济/降息去的=衰退型",
                 "flight-to-safety into long bonds = pricing recession/cuts = recession-type")
        elif tlt_r <= -0.003:
            tell("长债 TLT", "Long bond TLT", f"{tlt_r*100:+.1f}%", "mech",
                 "股债黄金一起跌=为流动性无差别抛售=机械/仓位型",
                 "stocks+bonds+gold all down = indiscriminate liquidation for cash = mechanical")
        else:
            tell("长债 TLT", "Long bond TLT", f"{tlt_r*100:+.1f}%", "neutral",
                 "长债基本走平,无强避险", "long bonds ~flat; no strong flight-to-safety")

    # 3) 高收益信用 HYG(相对其 beta 是否超跌)
    if not np.isnan(hyg_r) and not np.isnan(spy_r):
        expected = HY_BETA * spy_r
        excess = hyg_r - expected           # 负 = 比该跌的还多 = 信用走坏
        if excess < -0.005:
            tell("高收益信用 HYG", "High-yield credit HYG", f"{hyg_r*100:+.1f}% (超beta {excess*100:+.1f}%)", "reco",
                 "信用比股票 beta 跌得更狠=违约/基本面担忧=衰退型",
                 "credit falls beyond its beta = default/fundamental fear = recession-type",
                 val_en=f"{hyg_r*100:+.1f}% (vs beta {excess*100:+.1f}%)")
        else:
            tell("高收益信用 HYG", "High-yield credit HYG", f"{hyg_r*100:+.1f}% (超beta {excess*100:+.1f}%)", "mech",
                 "信用未额外走坏=更像仓位去杠杆而非基本面",
                 "credit not extra-weak = more deleveraging than fundamentals",
                 val_en=f"{hyg_r*100:+.1f}% (vs beta {excess*100:+.1f}%)")

    # 4) 黄金 GLD
    if not np.isnan(gld_r):
        if gld_r <= -0.005:
            tell("黄金 GLD", "Gold GLD", f"{gld_r*100:+.1f}%", "mech",
                 "黄金跟跌=典型流动性挤兑(1987/2020-3 初期)=机械",
                 "gold falls too = classic liquidity squeeze (1987/Mar-2020 onset) = mechanical")
        elif gld_r >= 0.005:
            tell("黄金 GLD", "Gold GLD", f"{gld_r*100:+.1f}%", "reco",
                 "黄金上涨=有序避险", "gold up = orderly flight-to-safety")
        else:
            tell("黄金 GLD", "Gold GLD", f"{gld_r*100:+.1f}%", "neutral",
                 "黄金基本走平", "gold ~flat")

    # 5) 防御 vs 周期
    if not np.isnan(defensive_r) and not np.isnan(xlk_r):
        spread = defensive_r - xlk_r
        if spread > 0.02:
            tell("防御 vs 科技(XLP/XLU−XLK)", "Defensives vs tech (XLP/XLU−XLK)", f"{spread*100:+.1f}%", "reco",
                 "资金往防御板块轮动、科技独差=对经济定价=衰退型",
                 "rotation into defensives, tech worst = pricing the economy = recession-type")
        else:
            tell("防御 vs 科技(XLP/XLU−XLK)", "Defensives vs tech (XLP/XLU−XLK)", f"{spread*100:+.1f}%", "mech",
                 "各板块无差别同跌=去杠杆而非轮动=机械型",
                 "all sectors down alike = deleveraging not rotation = mechanical")

    # 6) 衰退闸门语境
    if gate_votes is not None:
        if gate_votes >= 2:
            tell("衰退闸门票数", "Recession-gate votes", f"{gate_votes}/6", "reco",
                 "宏观已亮红=崩在衰退语境里=衰退型",
                 "macro already red = crash in a recession context = recession-type")
        elif gate_votes == 0:
            tell("衰退闸门票数", "Recession-gate votes", f"{gate_votes}/6", "mech",
                 "宏观全绿里突然崩=正是 1987-type 特征=机械型",
                 "crash from all-green macro = the 1987-type signature = mechanical")
        else:
            tell("衰退闸门票数", "Recession-gate votes", f"{gate_votes}/6", "neutral",
                 "宏观有零星红灯,语境模糊", "a few macro reds; context ambiguous")

    mech = sum(1 for x in tells if x["lean"] == "mech")
    reco = sum(1 for x in tells if x["lean"] == "reco")

    triggered = (not np.isnan(worst_eq)) and worst_eq <= CRASH_TH
    if mech > reco:
        nature, nature_en, nat_color = "机械 / 仓位型(1987-type)", "Mechanical / positioning (1987-type)", "amber"
        nat_note = "历史上这类**不带衰退**,恢复最快(1987 约 2 年、当年往往还收正)。吓人但对不加杠杆的长期组合不致命。"
        nat_note_en = "Historically these carry **no recession** and recover fastest (~2 yrs for 1987, often positive that very year). Scary but not fatal to an unlevered long-term book."
    elif reco > mech:
        nature, nature_en, nat_color = "基本面 / 衰退型", "Fundamental / recession-type", "red"
        nat_note = "带衰退的熊市恢复最慢(2000 约7年、2008 约5.5年)——这才是会让组合多年翻不了身的一类。"
        nat_note_en = "Recession bears recover slowest (~7 yrs for 2000, ~5.5 yrs for 2008) — the kind that sinks a book for years."
    else:
        nature, nature_en, nat_color = "信号混合 / 待确认", "Mixed signals / unconfirmed", "muted"
        nat_note = "机械 vs 衰退 tell 打平,需再观察信用与长债后续几日走向。"
        nat_note_en = "mechanical vs recession tells are tied; watch credit and long bonds over the next few days."

    if triggered:
        headline = f"🚨 今日崩盘级波动(SPY {spy_r*100:+.1f}% / NDX {ndx_r*100:+.1f}%)→ 判定:{nature}"
        headline_en = f"🚨 Crash-scale move today (SPY {spy_r*100:+.1f}% / NDX {ndx_r*100:+.1f}%) → verdict: {nature_en}"
    else:
        headline = (f"平日无崩盘级波动(SPY {spy_r*100:+.1f}% / NDX {ndx_r*100:+.1f}%,阈值 {CRASH_TH*100:.0f}%)。"
                    f"下方为「若今日真崩,盘面当前偏向」的预演:{nature}")
        headline_en = (f"No crash-scale move (SPY {spy_r*100:+.1f}% / NDX {ndx_r*100:+.1f}%, threshold {CRASH_TH*100:.0f}%). "
                       f"Below is a preview of which way the tape leans if a crash hit today: {nature_en}")

    crash_diag = {
        "triggered": bool(triggered),
        "crash_threshold_pct": round(CRASH_TH * 100, 1),
        "spy_ret_pct": None if np.isnan(spy_r) else round(spy_r * 100, 2),
        "ndx_ret_pct": None if np.isnan(ndx_r) else round(ndx_r * 100, 2),
        "nature": nature,
        "nature_en": nature_en,
        "nature_color": nat_color,
        "nature_note": nat_note,
        "nature_note_en": nat_note_en,
        "mech_score": mech,
        "reco_score": reco,
        "headline": headline,
        "headline_en": headline_en,
        "tells": tells,
    }

    return {
        "date": _today_et(),
        "module": "tail_fragility", "fidelity": "project_specific",
        "updated": _now_cst(),
        # A) 脆弱性
        "frag_score": frag_score,
        "frag_max": len(factors),
        "frag_color": frag_color,
        "frag_label": frag_label,
        "frag_label_en": frag_label_en,
        "factors": factors,
        # B) 崩盘诊断
        "crash_diag": crash_diag,
        "note": "脆弱性侧栏与六因子衰退闸门正交,只量化「干柴」不发买卖信号;崩盘诊断读同日盘面判性质 · 详见 notes/1987型崩盘_vs_六因子闸门.md · 不构成投资建议",
        "note_en": "Fragility sidebar is orthogonal to the six-factor recession gate; it only gauges dry tinder and emits no buy/sell signal; the crash diagnostic reads the same-day tape to judge nature · see notes/1987型崩盘_vs_六因子闸门.md · not investment advice",
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
    data[today]["fragility_gate"] = payload
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    cd = payload["crash_diag"]
    log.info(f"💾 fragility_gate 已写入 data.json：{today}  脆弱={payload['frag_score']}/{payload['frag_max']} "
             f"崩盘诊断={'触发' if cd['triggered'] else '预演'}·{cd['nature']}(机械{cd['mech_score']}/衰退{cd['reco_score']})")


def run(dry_run: bool = False):
    log.info("=" * 60)
    log.info("🔥 脆弱性/拥挤度侧栏 + 崩盘性质诊断")
    log.info("=" * 60)
    payload = compute()
    log.info(f"  A) 脆弱性 {payload['frag_score']}/{payload['frag_max']} · {payload['frag_label']}")
    for f in payload["factors"]:
        log.info(f"    {'🔥' if f['fragile'] else '·'} {f['name']}: {f['value']}  ({f['detail']})")
    cd = payload["crash_diag"]
    log.info(f"  B) 崩盘诊断 [{'触发' if cd['triggered'] else '预演'}] {cd['nature']}  (机械{cd['mech_score']} vs 衰退{cd['reco_score']})")
    for x in cd["tells"]:
        log.info(f"    [{x['lean']:>7}] {x['name']}: {x['value']}")
    if dry_run:
        log.info("🧪 dry-run：不写文件")
        return payload
    save(payload)
    log.info("✅ 完成")
    return payload


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="脆弱性/拥挤度侧栏 + 崩盘性质诊断")
    p.add_argument("--dry-run", action="store_true", help="不写文件,仅打印")
    args = p.parse_args()
    run(args.dry_run)
