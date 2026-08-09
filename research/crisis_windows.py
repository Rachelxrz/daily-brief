#!/usr/bin/env python3
"""
research/crisis_windows.py — 危机前 30 天:四模型的「连续 / 数值」轨迹(Phase 3 续)

问题:过去 ~30 年历次危机,**从危机发生前 30 个交易日到危机当天**,我们这四个模型
(含宏观 macro_gate)当时到底显示什么?数值多少?连续亮了几天?——即「事后看,
我们的仪表盘在崩盘前有没有、以及提前多久报警」。

做法(复用 backtest_models 的同一批数据与同一信号构造器,绝不另立口径):
  · macro_gate:逐日**票数(0–6)** + 闸门是否 on + **连续 risk-off(票≥2)天数** + 闸门首次 on 在 onset 前第几日
  · fragility :逐日**脆弱分(0–5)** + 窗口内峰值
  · dalio     :onset 当月**泡沫读数(0–100)** + 货币针是否 ON(月频)
  · breadth   :逐日**狭窄计分(0–3)** + 窗口内峰值
每个模型另存「窗口内每 ~3 交易日采样的路径」用于网页画趋势。数据不可得(ETF/指标历史不够早)→ 标 available=false。

无前视:信号序列本身即 point-in-time(见 backtest_models);此处只是**按日期切片**,不引入未来信息。
沙箱封数据源 → `--self-test` 用合成数据验证切片逻辑。输出:research/crisis_windows.json。不构成投资建议。
"""
import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent
import sys
sys.path.insert(0, str(REPO_DIR))
import research.backtest_models as bm     # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

RESULTS_FILE = BASE_DIR / "crisis_windows.json"
DATA_FILE = REPO_DIR / "docs" / "data.json"

WIN = 30          # 危机前的交易日数(≈6 周)
SAMPLE = 3        # 路径采样步长(每 3 交易日取一点)
FWD = 63          # onset 之后的前瞻窗口(算这次崩得多深,作为「危机严重度」上下文)

# 过去 ~30 年历次危机的「起点」(市场见顶 / 崩盘触发日;非交易日会自动向前对齐)
CRISES = [
    ("2000 互联网泡沫见顶", "2000 dot-com peak", "2000-03-10"),
    ("2001 9·11", "2001 9/11", "2001-09-10"),
    ("2007 金融危机见顶", "2007 GFC market peak", "2007-10-09"),
    ("2008 雷曼", "2008 Lehman", "2008-09-12"),
    ("2010 闪崩", "2010 Flash Crash", "2010-05-06"),
    ("2011 美债降级", "2011 US downgrade", "2011-07-22"),
    ("2015 人民币贬值闪崩", "2015 China deval", "2015-08-17"),
    ("2018 Q4 抛售", "2018 Q4 selloff", "2018-10-03"),
    ("2020 新冠", "2020 COVID peak", "2020-02-19"),
    ("2022 加息熊", "2022 rate-hike bear", "2022-01-03"),
]


def _snap(idx: pd.DatetimeIndex, date: str):
    """把 onset 对齐到 ≤date 的最近一个可用交易日;窗口不够(数据太早)→ None。"""
    ts = pd.Timestamp(date)
    prior = idx[idx <= ts]
    if len(prior) == 0:
        return None, None
    pos = idx.get_loc(prior[-1])
    if pos < WIN:
        return None, None
    return pos, idx[pos]


def _consec_true_at(s: pd.Series, pos: int) -> int:
    """从 pos 往前数,连续为 True 的天数(含 pos 当日)。"""
    arr = s.to_numpy()
    c = 0
    i = pos
    while i >= 0 and bool(arr[i]):
        c += 1
        i -= 1
    return c


def _path(s: pd.Series, pos: int) -> list:
    """窗口 [pos-WIN, pos] 内每 SAMPLE 交易日采一点 → [[rel_day, value], ...](rel_day≤0)。"""
    out = []
    for j in range(-WIN, 1, SAMPLE):
        i = pos + j
        if 0 <= i < len(s):
            v = s.iloc[i]
            out.append([j, None if (isinstance(v, float) and np.isnan(v)) else
                        (int(v) if float(v).is_integer() else round(float(v), 2))])
    return out


def _fwd_drawdown(price: pd.Series, pos: int, fwd: int) -> float:
    """onset 之后 fwd 交易日内的真·峰谷回撤(相对滚动峰值)。"""
    seg = price.iloc[pos: pos + fwd + 1].to_numpy(dtype=float)
    if len(seg) < 2:
        return float("nan")
    peak = np.maximum.accumulate(seg)
    return float((seg / peak - 1.0).min())


def _macro_block(macro: pd.DataFrame, onset_ts) -> dict:
    if macro is None or onset_ts not in macro.index:
        return {"available": False}
    pos = macro.index.get_loc(onset_ts)
    votes = macro["votes"]
    gate = macro["risk_off"].astype(bool)
    raw_off = (votes >= bm.MG.K)
    consec_gate = _consec_true_at(gate, pos)                # 连续闸门on天数(截至 onset)
    # 闸门在 onset 前第几日就已 on:即当前 on-streak 的起点相对日(可早于 30 天窗口)。
    # gate 在 onset 未 on → None。负值越大 = 越早报警。
    first_gate_rel = -(consec_gate - 1) if bool(gate.iloc[pos]) else None
    win_votes = votes.iloc[max(0, pos - WIN): pos + 1]
    return {
        "available": True,
        "votes_at_onset": int(votes.iloc[pos]),
        "votes_max": int(win_votes.max()),
        "gate_on_at_onset": bool(gate.iloc[pos]),
        "consec_votes_ge2_at_onset": _consec_true_at(raw_off, pos),   # 连续≥2票天数
        "consec_gate_on_at_onset": consec_gate,                       # 连续闸门on天数
        "first_gate_on_rel_day": first_gate_rel,   # 闸门首次 on 相对 onset 的交易日(负=之前)
        "path": _path(votes, pos),
    }


def _score_block(df: pd.DataFrame, col: str, onset_ts, at_key: str) -> dict:
    if df is None or onset_ts not in df.index:
        return {"available": False}
    pos = df.index.get_loc(onset_ts)
    s = df[col]
    win = s.iloc[max(0, pos - WIN): pos + 1]
    return {"available": True, at_key: int(s.iloc[pos]), f"{at_key}_max": int(win.max()),
            "path": _path(s, pos)}


def _dalio_block(dalio: pd.DataFrame, onset_ts) -> dict:
    if dalio is None or dalio.empty:
        return {"available": False}
    # 月频:取 ≤onset 的最近月末读数 + 前两个月,画慢变量轨迹
    prior = dalio.index[dalio.index <= onset_ts]
    if len(prior) == 0 or pd.isna(dalio.loc[prior[-1], "reading"]):
        return {"available": False}
    mpos = dalio.index.get_loc(prior[-1])
    path = []
    for k in range(-3, 1):
        i = mpos + k
        if 0 <= i < len(dalio):
            r = dalio["reading"].iloc[i]
            path.append([k, None if pd.isna(r) else int(r)])
    r_now = dalio["reading"].iloc[mpos]
    return {
        "available": True,
        "reading_at_onset": None if pd.isna(r_now) else int(r_now),
        "pin_at_onset": bool(dalio["pin"].iloc[mpos]) if "pin" in dalio else None,
        "n_gauges": int(dalio["n_gauges"].iloc[mpos]) if "n_gauges" in dalio else None,
        "month_path": path,     # [rel_month, reading]
    }


def run_live() -> dict:
    log.info("=" * 64)
    log.info("🧭 危机前 30 天:四模型轨迹")
    log.info("=" * 64)
    d = bm.fetch_all()
    s = bm.build_series(d)
    macro = s.get("macro"); frag = s.get("frag"); dalio = s.get("dalio"); breadth = s.get("breadth")
    spx = d["spx"] if not d["spx"].empty else d["ndx"]      # 危机严重度用广基;缺则退 ^NDX

    events = []
    for name, name_en, date in CRISES:
        # onset 对齐到有 macro 序列的交易日网格(macro 覆盖最广、最长)
        grid = macro.index if macro is not None else (spx.index if not spx.empty else None)
        if grid is None:
            continue
        pos, onset_ts = _snap(grid, date)
        if onset_ts is None:
            events.append({"name": name, "name_en": name_en, "onset": date, "available": False,
                           "reason": "数据早于该危机(no data this early)"})
            continue
        # 危机严重度:onset 后 FWD 日的峰谷回撤(广基)
        fwd_dd = float("nan")
        if not spx.empty:
            spx_prior = spx.index[spx.index <= onset_ts]
            if len(spx_prior):
                fwd_dd = _fwd_drawdown(spx, spx.index.get_loc(spx_prior[-1]), FWD)
        events.append({
            "name": name, "name_en": name_en, "onset": str(onset_ts.date()),
            "available": True,
            "fwd_drawdown_pct": None if np.isnan(fwd_dd) else round(fwd_dd * 100, 1),
            "fwd_days": FWD,
            "macro_gate": _macro_block(macro, onset_ts),
            "fragility": _score_block(frag, "frag_score", onset_ts, "score_at_onset"),
            "dalio": _dalio_block(dalio, onset_ts),
            "breadth": _score_block(breadth, "narrow_score", onset_ts, "narrow_at_onset"),
        })
        m = events[-1]["macro_gate"]
        log.info(f"  · {name} [{events[-1]['onset']}]: 崩{events[-1]['fwd_drawdown_pct']}% · "
                 f"macro 票 {m.get('votes_at_onset')}(峰{m.get('votes_max')})· 闸门{'on' if m.get('gate_on_at_onset') else 'off'}"
                 f"·连续≥2票 {m.get('consec_votes_ge2_at_onset')}日·首次on 相对日 {m.get('first_gate_on_rel_day')}")

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ"),
        "window_trading_days": WIN, "fwd_days": FWD,
        "note": ("历次危机前 30 交易日,四模型逐日数值/连续天数(信号 point-in-time,无前视,仅按日期切片)。"
                 "macro_gate 票数/连续/闸门首次 on 相对日;fragility 脆弱分;dalio 月频读数+货币针;breadth 狭窄计分。"
                 "数据早于某危机则标 unavailable(VIX≈1990、RSP≈2003、^VIX3M≈2007)。severity=onset 后 63 日峰谷回撤。不构成投资建议。"),
        "note_en": ("For each crisis, the four models' daily values / consecutive counts over the 30 trading days into the onset "
                    "(signals are point-in-time, no look-ahead; this only slices by date). macro_gate votes/persistence/first-gate-on; "
                    "fragility score; dalio monthly reading + monetary pin; breadth narrow score. Marked unavailable where data predates "
                    "the crisis (VIX≈1990, RSP≈2003, ^VIX3M≈2007). severity = peak-to-trough drawdown over 63d after onset. Not advice."),
        "crises": events,
    }


def save_results(payload: dict):
    RESULTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"💾 写入 {RESULTS_FILE.relative_to(REPO_DIR)}({len(payload['crises'])} 次危机)")
    data = {}
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["crisis_windows"] = payload
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("💾 已回填 docs/data.json['crisis_windows']")


def self_test():
    log.info("🧪 self-test:合成数据验证危机切片")
    rng = pd.date_range("1998-01-02", periods=1200, freq="B")
    # 合成 macro 序列:后半段票数抬升、闸门 on
    votes = pd.Series(np.concatenate([np.zeros(600), np.ones(600) * 3]).astype(int), index=rng)
    gate = pd.Series(np.concatenate([np.zeros(650), np.ones(550)]).astype(bool), index=rng)
    macro = pd.DataFrame({"votes": votes, "risk_off": gate}, index=rng)

    onset_ts = rng[900]
    blk = _macro_block(macro, onset_ts)
    assert blk["available"] and blk["votes_at_onset"] == 3, blk
    assert blk["gate_on_at_onset"] is True and blk["consec_votes_ge2_at_onset"] == 900 - 600 + 1, blk
    # 闸门 index 650 起 on,onset=900 → 连续 251 日,首次 on 相对日 = -250(早于 30 日窗口,正是我们要能捕捉的)
    assert blk["consec_gate_on_at_onset"] == 900 - 650 + 1, blk
    assert blk["first_gate_on_rel_day"] == -(900 - 650), blk
    assert blk["path"][0][0] == -WIN and blk["path"][-1][0] == 0, blk["path"]
    log.info(f"  ✅ macro 切片:onset 票={blk['votes_at_onset']} 连续≥2={blk['consec_votes_ge2_at_onset']} "
             f"首次on相对日={blk['first_gate_on_rel_day']} 路径点={len(blk['path'])}")

    # 数据太早 → _snap 返回 None
    pos, ts = _snap(rng, "1990-01-01")
    assert ts is None, "早于数据应 unavailable"
    log.info("  ✅ 早于数据的危机正确标记 unavailable")

    # 切片无前视:onset 处的 block 不依赖 onset 之后的数据
    macro_trunc = macro.iloc[:901]      # 只到 onset 当日
    blk2 = _macro_block(macro_trunc, onset_ts)
    assert blk2["votes_at_onset"] == blk["votes_at_onset"] and \
           blk2["consec_votes_ge2_at_onset"] == blk["consec_votes_ge2_at_onset"], "切片受未来影响!"
    log.info("  ✅ onset 切片不依赖未来数据(截断到 onset 当日结果不变)")
    log.info("🎉 self-test 全过")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="危机前 30 天四模型轨迹(Phase 3 续)")
    ap.add_argument("--self-test", action="store_true", help="合成数据验证切片(无网时用)")
    ap.add_argument("--dry-run", action="store_true", help="拉数算但不写文件")
    args = ap.parse_args()
    if args.self_test:
        self_test()
    else:
        payload = run_live()
        if not args.dry_run:
            save_results(payload)
