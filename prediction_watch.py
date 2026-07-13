#!/usr/bin/env python3
"""
Prediction / 轮动观察 — 月度快照与表格生成
=================================================

- 每月 1 号（或之前最近交易日）记录一组 ETF 的 Adjusted Close 快照，
  持久化到 prediction_snapshots.jsonl（每行 {date, ticker, adj_close}）。
- 以 2025-12-31 收盘价作为 "Jan 1" 基准，计算：
    (a) 自基准日的累计涨幅 cum_return
    (b) 相对 QQQ 的超额 = cum_return - QQQ 的 cum_return
    (c) 环比上月快照的"当月涨幅"
- 输出 markdown 表格（行=ticker，QQQ 置顶作基准；超额为正的行在数字后加 ✓）。
- 页面顶部原样嵌入 prediction_views.md（观点整理表，用户提供）。

依赖：Python 标准库 + yfinance（yfinance 自带 pandas，用于读取其返回的行情表）。

用法：
  python prediction_watch.py --backfill   # 回填基准 + 2026 各月度快照，打印表格（不推送）
  python prediction_watch.py --dry-run     # 生成当月快照并打印，不写网页、不推送
  python prediction_watch.py               # 当月快照 + 写入网页 data.json + 推送微信
"""

import argparse
import json
import logging
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import yfinance as yf

# ─── 配置 ──────────────────────────────────────────────────
TICKERS = ["QQQ", "SPY", "IGV", "IJR", "MDY", "MAGS", "RSP", "XBI", "XMMO", "XLF", "XLE"]
BASELINE_DATE = "2025-12-31"          # 作为 "Jan 1" 基准，用当日 Adjusted Close
BASELINE_LABEL = "Jan 1"
# 首次运行回填的月度快照目标日（2026 上半年），使曲线从第一天起就完整
BACKFILL_DATES = [
    "2026-02-01", "2026-03-01", "2026-04-01",
    "2026-05-01", "2026-06-01", "2026-07-01",
]

MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

BASE_DIR   = Path(__file__).parent
SNAP_FILE  = BASE_DIR / "prediction_snapshots.jsonl"
VIEWS_FILE = BASE_DIR / "prediction_views.md"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("prediction_watch")


# ─── 时间 ──────────────────────────────────────────────────
def _now_et() -> datetime:
    """美东时间（与站内其他模块保持一致，避免跨日）。"""
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))


def _month_label(date_str: str) -> str:
    """快照日期 → 列标签。基准日显示为 'Jan 1'，月度快照显示为 '<Mon> 1'。"""
    if date_str == BASELINE_DATE:
        return BASELINE_LABEL
    _, m, _ = date_str.split("-")
    return f"{MONTH_ABBR[int(m)]} 1"


# ─── 行情抓取（yfinance，Adjusted Close，取目标日或之前最近交易日）──────
def _download_adj_close(targets: list):
    """下载覆盖所有目标日期的行情，返回 Adjusted Close 表（列=ticker）。失败返回 None。"""
    start = (datetime.strptime(min(targets), "%Y-%m-%d") - timedelta(days=12)).strftime("%Y-%m-%d")
    end   = (datetime.strptime(max(targets), "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
    log.info(f"📡 yfinance 下载 {len(TICKERS)} 只 ETF: {start} → {end}")
    df = yf.download(TICKERS, start=start, end=end, auto_adjust=False, progress=False)
    if df is None or len(df) == 0:
        log.error("❌ yfinance 未返回任何数据")
        return None
    # 选取 Adjusted Close（若无则退回 Close）
    try:
        fields = set(df.columns.get_level_values(0))
    except Exception:
        fields = set(df.columns)
    field = "Adj Close" if "Adj Close" in fields else "Close"
    try:
        adj = df[field]
    except Exception:
        adj = df
    return adj


def _price_on_or_before(adj, ticker: str, target: str):
    """取 ticker 在 target（含）或之前最近交易日的收盘价。无数据返回 None。"""
    try:
        series = adj[ticker]
    except Exception:
        return None
    try:
        s = series.loc[:target].dropna()
    except Exception:
        return None
    if len(s) == 0:
        return None
    return round(float(s.iloc[-1]), 4)


def fetch_snapshot_prices(targets: list) -> dict:
    """返回 {date_str: {ticker: adj_close}}，date_str 为传入的目标日期字符串。"""
    adj = _download_adj_close(targets)
    if adj is None:
        return {}
    out = {}
    for tgt in targets:
        day = {}
        for t in TICKERS:
            v = _price_on_or_before(adj, t, tgt)
            if v is not None:
                day[t] = v
        out[tgt] = day
        got = ", ".join(f"{t}={day[t]}" for t in TICKERS if t in day)
        log.info(f"   {tgt}: {got if got else '（无数据）'}")
    return out


# ─── 快照持久化（jsonl，按月幂等）──────────────────────────
def load_snapshots() -> dict:
    """读取 {date: {ticker: adj_close}}。"""
    snaps: dict = {}
    if SNAP_FILE.exists():
        for line in SNAP_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                snaps.setdefault(rec["date"], {})[rec["ticker"]] = rec["adj_close"]
            except Exception:
                continue
    return snaps


def save_snapshots(snaps: dict) -> None:
    """按日期、ticker 顺序重写整个 jsonl（幂等：同月覆盖而非重复追加）。"""
    lines = []
    for d in sorted(snaps):
        for t in TICKERS:
            if t in snaps[d]:
                lines.append(json.dumps(
                    {"date": d, "ticker": t, "adj_close": snaps[d][t]},
                    ensure_ascii=False))
    SNAP_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info(f"💾 已写入 {SNAP_FILE.name}（{len(lines)} 行，{len(snaps)} 个月度快照）")


def upsert_snapshot(snaps: dict, date_str: str, day_prices: dict) -> None:
    """覆盖某一快照日期的记录（同月幂等，重复运行不重复追加）。"""
    if day_prices:
        snaps[date_str] = dict(day_prices)


# ─── 计算 + markdown 表格 ──────────────────────────────────
def _fmt_price(v):
    return f"{v:,.2f}" if v is not None else "—"


def _fmt_pct(x, tick=False):
    if x is None:
        return "—"
    s = f"{x * 100:+.1f}%"
    if tick and x > 0:
        s += " ✓"
    return s


def build_table(snaps: dict) -> str:
    """生成 markdown 表格。"""
    dates = sorted(snaps)  # 基准日 2025-12-31 排在最前
    if BASELINE_DATE not in snaps:
        return "> ⚠️ 缺少基准日快照，无法生成表格。"
    latest = dates[-1]
    prev   = dates[-2] if len(dates) >= 2 else BASELINE_DATE

    def cum(t):
        b = snaps[BASELINE_DATE].get(t)
        v = snaps[latest].get(t)
        return (v / b - 1) if (b and v) else None

    def mom(t):
        p = snaps[prev].get(t)
        v = snaps[latest].get(t)
        return (v / p - 1) if (p and v) else None

    qqq_cum = cum("QQQ")

    def excess(t):
        c = cum(t)
        return (c - qqq_cum) if (c is not None and qqq_cum is not None) else None

    ordered = ["QQQ"] + [t for t in TICKERS if t != "QQQ"]

    # 表头：Ticker | 各快照日价格… | 累计涨幅 | vs QQQ超额 | 当月涨幅
    price_cols = [_month_label(d) for d in dates]
    header = ["Ticker"] + price_cols + ["累计涨幅", "vs QQQ超额", "当月涨幅"]
    sep = ["---"] * len(header)

    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join(sep) + " |"]

    for t in ordered:
        row = [f"**{t}**" if t == "QQQ" else t]
        row += [_fmt_price(snaps[d].get(t)) for d in dates]
        row.append(_fmt_pct(cum(t)))
        # QQQ 自身超额恒为 0，不打 ✓
        row.append(_fmt_pct(excess(t), tick=(t != "QQQ")))
        row.append(_fmt_pct(mom(t)))
        lines.append("| " + " | ".join(row) + " |")

    note = (f"\n> 基准 {BASELINE_LABEL}（{BASELINE_DATE} 收盘）· 最新 {_month_label(latest)}"
            f"（{latest}）· 当月涨幅 = 最新 vs {_month_label(prev)} · ✓ = 跑赢 QQQ")
    return "\n".join(lines) + "\n" + note


def _read_views() -> str:
    if VIEWS_FILE.exists():
        txt = VIEWS_FILE.read_text(encoding="utf-8").strip()
        if txt:
            return txt
    return "> 📝 观点整理表尚未填写（编辑 `prediction_views.md` 后本区域将原样显示）。"


def build_page(snaps: dict) -> str:
    """完整页面 markdown：标题 + 观点整理（原样）+ 分隔线 + 表格。"""
    ym = _now_et().strftime("%Y年%m月")
    return (
        f"# 📈 Prediction | 轮动观察\n"
        f"### {ym}\n\n"
        f"{_read_views()}\n\n"
        f"---\n\n"
        f"{build_table(snaps)}\n"
    )


# ─── 写入网页 + 推送 ───────────────────────────────────────
def save_to_web(page: str) -> None:
    """把页面写入 docs/data.json 的 prediction 键（复用 save_to_web 的读写与日期约定）。"""
    try:
        from save_to_web import load_data, save_data, _today_et
    except Exception as e:
        log.warning(f"⚠️ 无法导入 save_to_web，跳过网页写入: {e}")
        return
    today = _today_et()
    data = load_data()
    data.setdefault(today, {})
    data[today]["updated"] = _now_et().strftime("%Y-%m-%d %H:%M ET")
    data[today]["prediction"] = {"md": page}
    save_data(data)
    log.info(f"🌐 轮动观察已写入网页: {today}")


def push(page: str) -> None:
    """复用 WxPusher / ServerChan 推送通道。"""
    ym = _now_et().strftime("%Y年%m月")
    title = f"📈 轮动观察 · {ym}"
    try:
        from config import Config
        from market_monitor import push_serverchan, push_wxpusher
    except Exception as e:
        log.warning(f"⚠️ 无法导入推送模块，跳过推送: {e}")
        return
    sent = False
    if getattr(Config, "SERVERCHAN_SENDKEY", ""):
        push_serverchan(title, page); sent = True
    if getattr(Config, "WXPUSHER_APP_TOKEN", ""):
        push_wxpusher(title, page); sent = True
    if not sent:
        log.warning("⚠️ 未配置 WxPusher / ServerChan，跳过推送")


# ─── 主流程 ────────────────────────────────────────────────
def do_backfill(snaps: dict) -> dict:
    prices = fetch_snapshot_prices([BASELINE_DATE] + BACKFILL_DATES)
    for d in [BASELINE_DATE] + BACKFILL_DATES:
        upsert_snapshot(snaps, d, prices.get(d, {}))
    return snaps


def run(backfill: bool = False, dry_run: bool = False) -> int:
    snaps = load_snapshots()

    if backfill:
        log.info("🔁 回填基准 + 2026 月度快照…")
        do_backfill(snaps)
        save_snapshots(snaps)
    else:
        now = _now_et()
        target = date(now.year, now.month, 1).isoformat()
        # 首次运行（无基准）：自动回填历史，保证曲线完整
        if BASELINE_DATE not in snaps:
            log.info("🔁 首次运行，自动回填历史快照…")
            do_backfill(snaps)
        # 当月快照（同月幂等覆盖）
        prices = fetch_snapshot_prices([target])
        upsert_snapshot(snaps, target, prices.get(target, {}))
        save_snapshots(snaps)

    if BASELINE_DATE not in snaps:
        log.error("❌ 基准日快照缺失（可能是行情抓取失败），终止。")
        return 1

    page = build_page(snaps)
    print("\n" + page)

    if not dry_run and not backfill:
        save_to_web(page)
        push(page)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prediction / 轮动观察 月度快照")
    parser.add_argument("--backfill", action="store_true", help="回填基准+2026月度快照，只写快照与打印")
    parser.add_argument("--dry-run",  action="store_true", help="生成并打印，不写网页、不推送")
    args = parser.parse_args()
    sys.exit(run(backfill=args.backfill, dry_run=args.dry_run))
