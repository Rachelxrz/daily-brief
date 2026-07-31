#!/usr/bin/env python3
"""
macro_gate.py — QQQ 六因子宏观/金融体制闸门 + 波动率目标 (2026-07-30)

因子(每条 = 1 张 risk-off 票):
  1. 波动    VIX > 28
  2. 收益率曲线 10年-3月 (FRED T10Y3M) 倒挂 < 0
  3. 信用    Baa-10年利差 (FRED BAA10Y) 3年 z 分 > 1
  4. 宏观-劳动 Sahm 衰退规则 (FRED UNRATE) >= 0.5
  5. 宏观-增长 CFNAI 3月均 (FRED CFNAI) < -0.7
  6. 趋势    QQQ(^NDX) 收盘 < 200日线 且 200日线较~1季度前更低

闸门:票数 >= 2 且【连续 >= 10 个交易日(约2周)】→ 崩盘体制 → 卖出/清仓 QQQ;
      票数 < 2 → 买回。仅作用于 QQQ 这类指数 ETF(个股由 ma_cross_signal / 策略1 负责)。
仓位:闸门 on → 0;否则 min(100%, 目标波动20% / QQQ 20日已实现年化波动)。不加杠杆。

回测口径(1990→今,^NDX):CAGR 12.6% · MaxDD -26.5% · Sharpe 0.81(见 stock_Ai 回测)。
输出:docs/data.json 的 [today]["macro_gate"](供网页「📌 结构监控」页顶部面板)。
不推送微信(遵循「微信只推新闻」规则)。
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

BASE_DIR  = Path(__file__).parent
DATA_FILE = BASE_DIR / "docs" / "data.json"

K = 2                 # 崩盘票数阈值
PERSIST = 10          # 连续约2周(交易日)
TVOL = 0.20           # 目标年化波动
VIX_TH = 28.0
CREDIT_Z = 1.0
SAHM_TH = 0.5
CFNAI_TH = -0.7


def _today_et() -> str:
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")


def _now_cst() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M CST")


def fred(series_id: str, retries: int = 3) -> pd.Series:
    """FRED CSV(requests,无需额外依赖)→ 日期索引的浮点序列。
    带重试 + 60s 超时,容忍 FRED 偶发的读超时/抖动(否则任一序列失败会拖垮整块闸门)。"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    last = None
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
            last = e
            log.warning(f"  FRED {series_id} 第 {attempt}/{retries} 次失败: {str(e)[:60]}")
            if attempt < retries:
                time.sleep(3 * attempt)
    raise last


def _yf_close(ticker: str, period: str = "2y") -> pd.Series:
    d = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return d["Close"].dropna()


def compute() -> dict:
    ndx = _yf_close("^NDX")
    grid = ndx.index
    vix = _yf_close("^VIX").reindex(grid, method="ffill")

    curve = fred("T10Y3M").reindex(grid, method="ffill")
    baa = fred("BAA10Y").reindex(grid, method="ffill")
    # 用最新已发布值(live 读数无需滞后);min_periods 容忍数据缺月(如 2025 停摆造成的空档)
    unrate = fred("UNRATE").dropna()
    u3 = unrate.rolling(3, min_periods=1).mean()
    sahm = (u3 - u3.rolling(12, min_periods=3).min()).reindex(grid, method="ffill")
    cfnai3 = fred("CFNAI").dropna().rolling(3, min_periods=1).mean().reindex(grid, method="ffill")

    ma200 = ndx.rolling(200).mean()
    slope_dn = ma200 < ma200.shift(65)
    baa_z = (baa - baa.rolling(756, min_periods=252).mean()) / baa.rolling(756, min_periods=252).std()
    rvol = ndx.pct_change().rolling(20).std() * np.sqrt(252)

    g_vol    = (vix > VIX_TH).fillna(False)
    g_curve  = (curve < 0).fillna(False)
    g_credit = (baa_z > CREDIT_Z).fillna(False)
    g_sahm   = (sahm >= SAHM_TH).fillna(False)
    g_cfnai  = (cfnai3 < CFNAI_TH).fillna(False)
    g_trend  = ((ndx < ma200) & slope_dn).fillna(False)
    votes = (g_vol.astype(int) + g_curve.astype(int) + g_credit.astype(int)
             + g_sahm.astype(int) + g_cfnai.astype(int) + g_trend.astype(int))

    # 2周持续性闸门(consec)
    raw = (votes >= K).to_numpy()
    consec = 0
    gate_series = np.zeros(len(raw), dtype=bool)
    for i in range(len(raw)):
        consec = consec + 1 if raw[i] else 0
        gate_series[i] = consec >= PERSIST
    gate_on = bool(gate_series[-1])

    rv = float(rvol.iloc[-1])
    weight = 0.0 if gate_on else min(1.0, TVOL / max(rv, 1e-6))

    def f(name, val_str, on, detail):
        return {"name": name, "value": val_str, "risk_off": bool(on), "detail": detail}

    factors = [
        f("波动 VIX", f"{float(vix.iloc[-1]):.1f}", g_vol.iloc[-1], f">{VIX_TH:.0f} 亮红"),
        f("收益率曲线 10Y-3M", f"{float(curve.iloc[-1]):+.2f}%", g_curve.iloc[-1], "倒挂<0 亮红"),
        f("信用 Baa-10Y", f"{float(baa.iloc[-1]):.2f}% · z={float(baa_z.iloc[-1]):+.1f}", g_credit.iloc[-1], "z>1 亮红"),
        f("宏观·Sahm 衰退", f"{float(sahm.iloc[-1]):+.2f}", g_sahm.iloc[-1], ">=0.5 亮红"),
        f("宏观·CFNAI 增长", f"{float(cfnai3.iloc[-1]):+.2f}", g_cfnai.iloc[-1], "<-0.7 亮红"),
        f("趋势 QQQ vs 200日线", ("下方" if bool(g_trend.iloc[-1]) else "上方"), g_trend.iloc[-1],
          "破200日线且斜率向下 亮红"),
    ]
    nvotes = int(votes.iloc[-1])

    if gate_on:
        rec, action, color = "SELL", "🔴 卖出 / 清仓 QQQ(转现金)", "red"
    elif weight >= 0.95:
        rec, action, color = "BUY", "🟢 买入 / 满仓持有 QQQ", "green"
    else:
        rec, action, color = "HOLD", f"🟡 持有,波动偏高 → 减仓至约 {round(weight*100)}%", "amber"

    return {
        "date": _today_et(),
        "updated": _now_cst(),
        "gate_on": gate_on,
        "votes": nvotes,
        "vote_threshold": K,
        "persist_days": PERSIST,
        "recommendation": rec,
        "action_cn": action,
        "color": color,
        "weight_pct": round(weight * 100),
        "target_vol_pct": round(TVOL * 100),
        "realized_vol_pct": round(rv * 100, 1),
        "factors": factors,
        "note": "六因子体制闸门 + 20%波动率目标 · 仅作用于 QQQ/指数ETF(个股由策略1负责) · 回测1990→今 CAGR12.6%/MaxDD-26.5%/Sharpe0.81 · 不构成投资建议",
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
    data[today]["macro_gate"] = payload
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"💾 macro_gate 已写入 data.json：{today}  票数={payload['votes']}/6 "
             f"闸门={'ON' if payload['gate_on'] else 'off'} 建议仓位={payload['weight_pct']}%")


def run(dry_run: bool = False):
    log.info("=" * 60)
    log.info("📌 QQQ 六因子宏观闸门 + 波动率目标")
    log.info("=" * 60)
    payload = compute()
    log.info(f"  票数 {payload['votes']}/6 · 闸门 {'ON→清仓' if payload['gate_on'] else 'off'} · "
             f"建议 {payload['action_cn']} · 实现波动 {payload['realized_vol_pct']}%")
    for f in payload["factors"]:
        log.info(f"    {'🔴' if f['risk_off'] else '🟢'} {f['name']}: {f['value']}  ({f['detail']})")
    if dry_run:
        log.info("🧪 dry-run：不写文件")
        return payload
    save(payload)
    log.info("✅ 完成")
    return payload


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="QQQ 六因子宏观闸门 + 波动率目标")
    p.add_argument("--dry-run", action="store_true", help="不写文件,仅打印")
    args = p.parse_args()
    run(args.dry_run)
