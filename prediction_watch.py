#!/usr/bin/env python3
"""
Prediction / 轮动观察 — 每周快照与表格生成
=================================================

- 每周（每周五收盘，或之前最近交易日）记录一组 ETF 的 Adjusted Close 快照，
  持久化到 prediction_snapshots.jsonl（每行 {date, ticker, adj_close}）。
- 以 2025-12-31 收盘价作为基准，计算：
    (a) 自基准日的累计涨幅 cum_return
    (b) 相对 QQQ 的超额 = cum_return - QQQ 的 cum_return
    (c) 环比上一周快照的"本周涨幅"
- 输出 markdown 表格（行=ticker，QQQ 置顶作基准；超额为正的行在数字后加 ✓）。
  表格显示基准 + 最近 DISPLAY_WEEKS 周（完整历史仍存 jsonl）。
- 页面顶部原样嵌入 docs/prediction_views.md（观点整理表，前端常驻显示）。

依赖：Python 标准库 + yfinance（yfinance 自带 pandas，用于读取其返回的行情表）。

用法：
  python prediction_watch.py --backfill   # 全量回填基准 + 每周快照，打印表格（不推送）
  python prediction_watch.py --dry-run     # 生成本周快照并打印，不写网页、不推送
  python prediction_watch.py               # 本周快照 + 写入网页 data.json + 推送微信
"""

import argparse
import json
import logging
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import yfinance as yf

# ─── 配置 ──────────────────────────────────────────────────
TICKERS = ["QQQ", "SPY", "IGV", "IJR", "MDY", "MAGS", "RSP", "XBI", "XMMO",
           "XLF", "XLE", "SMH", "BDRY", "BWET", "UTES"]
BASELINE_DATE = "2025-12-31"          # 基准，用当日 Adjusted Close
BASELINE_LABEL = "基准"
# 每周监测：以每周五收盘为锚点。回填从 2026 年首个周五起，使曲线从年初就完整。
WEEKLY_START = "2026-01-02"           # 2026 首个周五
DISPLAY_WEEKS = 12                    # 表格显示：基准 + 最近 N 周（完整历史仍存 jsonl）

BASE_DIR   = Path(__file__).parent
SNAP_FILE  = BASE_DIR / "prediction_snapshots.jsonl"
# 放在 docs/ 下，让 GitHub Pages 能直接托管、前端可 fetch，观点内容始终可见
# （不依赖月度 job 是否已生成 data.json）。
VIEWS_FILE = BASE_DIR / "docs" / "prediction_views.md"

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


def _recent_friday(d: date) -> date:
    """返回 d（含）或之前最近的周五。"""
    return d - timedelta(days=(d.weekday() - 4) % 7)


def _weekly_anchors() -> list:
    """从 WEEKLY_START 起到最近一个周五（含）的所有周五日期字符串。"""
    start = datetime.strptime(WEEKLY_START, "%Y-%m-%d").date()
    end = _recent_friday(_now_et().date())
    out, cur = [], start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=7)
    return out


def _col_label(date_str: str) -> str:
    """快照日期 → 列标签。基准显示为 '基准'，每周快照显示为 'M/D'。"""
    if date_str == BASELINE_DATE:
        return BASELINE_LABEL
    _, m, d = date_str.split("-")
    return f"{int(m)}/{int(d)}"


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
    log.info(f"💾 已写入 {SNAP_FILE.name}（{len(lines)} 行，{len(snaps)} 个周度快照）")


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

    def wow(t):
        p = snaps[prev].get(t)
        v = snaps[latest].get(t)
        return (v / p - 1) if (p and v) else None

    qqq_cum = cum("QQQ")

    def excess(t):
        c = cum(t)
        return (c - qqq_cum) if (c is not None and qqq_cum is not None) else None

    ordered = ["QQQ"] + [t for t in TICKERS if t != "QQQ"]

    # 只显示：基准 + 最近 DISPLAY_WEEKS 周（完整历史仍存 jsonl；累计涨幅仍从基准算起）
    weekly_dates = [d for d in dates if d != BASELINE_DATE]
    shown_weeks  = weekly_dates[-DISPLAY_WEEKS:]
    display_dates = [BASELINE_DATE] + shown_weeks

    # 表头：Ticker | 基准 + 各周价格… | 累计涨幅 | vs QQQ超额 | 本周涨幅
    price_cols = [_col_label(d) for d in display_dates]
    header = ["Ticker"] + price_cols + ["累计涨幅", "vs QQQ超额", "本周涨幅"]
    sep = ["---"] * len(header)

    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join(sep) + " |"]

    for t in ordered:
        row = [f"**{t}**" if t == "QQQ" else t]
        row += [_fmt_price(snaps[d].get(t)) for d in display_dates]
        row.append(_fmt_pct(cum(t)))
        # QQQ 自身超额恒为 0，不打 ✓
        row.append(_fmt_pct(excess(t), tick=(t != "QQQ")))
        row.append(_fmt_pct(wow(t)))
        lines.append("| " + " | ".join(row) + " |")

    note = (f"\n> 基准（{BASELINE_DATE} 收盘）· 最新 {_col_label(latest)}"
            f"（{latest}）· 本周涨幅 = 最新 vs 上一周（{_col_label(prev)}）· ✓ = 跑赢 QQQ"
            f" · 表格显示基准 + 最近 {DISPLAY_WEEKS} 周，累计涨幅按全程计算")
    return "\n".join(lines) + "\n" + note


def _read_views() -> str:
    if VIEWS_FILE.exists():
        txt = VIEWS_FILE.read_text(encoding="utf-8").strip()
        if txt:
            return txt
    return "> 📝 观点整理表尚未填写（编辑 `prediction_views.md` 后本区域将原样显示）。"


def _subtitle(snaps: dict) -> str:
    dates = sorted(snaps)
    latest = dates[-1] if dates else _recent_friday(_now_et().date()).isoformat()
    return f"截至 {latest}（每周更新）"


def build_page(snaps: dict) -> str:
    """完整页面 markdown：标题 + 观点整理（原样）+ 分隔线 + 表格。
    用于微信推送（一条消息包含观点与数据）。"""
    return (
        f"# 📈 Prediction | 轮动观察\n"
        f"### {_subtitle(snaps)}\n\n"
        f"{_read_views()}\n\n"
        f"---\n\n"
        f"{build_table(snaps)}\n"
    )


def build_web(snaps: dict) -> str:
    """网页数据表 markdown（仅副标题 + 表格，不含观点）。
    观点由前端直接读取 docs/prediction_views.md 常驻显示，避免重复。"""
    return f"### {_subtitle(snaps)}\n\n{build_table(snaps)}\n"


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
    title = f"📈 轮动观察 · 截至 {_recent_friday(_now_et().date()).isoformat()}"
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
    anchors = _weekly_anchors()
    prices = fetch_snapshot_prices([BASELINE_DATE] + anchors)
    for d in [BASELINE_DATE] + anchors:
        upsert_snapshot(snaps, d, prices.get(d, {}))
    return snaps


def run(backfill: bool = False, dry_run: bool = False) -> int:
    if backfill:
        # 全量重建为每周序列（丢弃旧的月度点），保证曲线干净
        log.info("🔁 回填基准 + 每周快照（每周五）…")
        snaps = {}
        do_backfill(snaps)
        save_snapshots(snaps)
    else:
        snaps = load_snapshots()
        target = _recent_friday(_now_et().date()).isoformat()
        # 首次运行（无基准）：自动回填历史，保证曲线完整
        if BASELINE_DATE not in snaps:
            log.info("🔁 首次运行，自动回填历史快照…")
            do_backfill(snaps)
        # 本周快照（同一周五幂等覆盖）
        prices = fetch_snapshot_prices([target])
        upsert_snapshot(snaps, target, prices.get(target, {}))
        save_snapshots(snaps)

    if BASELINE_DATE not in snaps:
        log.error("❌ 基准日快照缺失（可能是行情抓取失败），终止。")
        return 1

    push_md = build_page(snaps)   # 微信：观点 + 数据表
    web_md  = build_web(snaps)    # 网页：仅数据表（观点由前端常驻显示）
    print("\n" + push_md)

    if not dry_run and not backfill:
        save_to_web(web_md)
        push(push_md)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prediction / 轮动观察 每周快照")
    parser.add_argument("--backfill", action="store_true", help="全量回填基准+每周快照，只写快照与打印")
    parser.add_argument("--dry-run",  action="store_true", help="生成并打印，不写网页、不推送")
    args = parser.parse_args()
    sys.exit(run(backfill=args.backfill, dry_run=args.dry_run))
