#!/usr/bin/env python3
"""
scripts/weekly_snapshot.py — 周度环境快照(C7):data/context_snapshots.jsonl 追加一行

原则(point-in-time):
  · 快照在**当下实时写入**,available_at = 写入时刻 → 「当时可见」天然成立,无未来值泄漏
    (ALFRED vintage 只在**回填历史**快照时才需要;实时快照记录的就是当时可见值,docstring 如实说明)
  · 幂等:本周 snapshot_id 已存在则跳过(JSONL 只追加,绝不改写)
  · narrative 当时写:自本周 briefs/*.md 标题行蒸馏 + 机制层读数一句话(数字事后能查,情绪查不回来)

数据来源:
  · markets:yfinance(^GSPC/BZ=F/GC=F/DX-Y.NYB/^TNX)——沙箱无网时置 null(不伪造)
  · macro.fed_rate:FRED FEDFUNDS 最新(同样无网置 null)
  · 机制层读数 + 简报标题:本仓库文件,离线可得

用法: python scripts/weekly_snapshot.py [--week 2026-W33] [--dry-run]
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SNAP_FILE = REPO / "data" / "context_snapshots.jsonl"
DATA_FILE = REPO / "docs" / "data.json"
BRIEFS = REPO / "briefs"


def _week_id(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _fetch_markets():
    """有网(Actions)取实时市场值;失败/无网 → null,绝不伪造。"""
    out = {"spx": None, "brent": None, "gold": None, "dxy": None, "us10y": None}
    fed = None
    try:
        import yfinance as yf
        tick = {"spx": "^GSPC", "brent": "BZ=F", "gold": "GC=F", "dxy": "DX-Y.NYB", "us10y": "^TNX"}
        for k, t in tick.items():
            try:
                d = yf.download(t, period="5d", auto_adjust=True, progress=False)
                if d is not None and len(d):
                    col = d["Close"] if "Close" in d else d.iloc[:, 0]
                    v = float(col.iloc[-1].iloc[0] if hasattr(col.iloc[-1], "iloc") else col.iloc[-1])
                    out[k] = round(v / 10, 3) if k == "us10y" else round(v, 2)   # ^TNX 为收益率×10
            except Exception:
                pass
    except Exception:
        pass
    try:
        import io
        import requests
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS", timeout=30)
        r.raise_for_status()
        lines = [x for x in r.text.splitlines() if x.strip()]
        fed = lines[-1].split(",")[-1]
    except Exception:
        pass
    return out, fed


def _week_brief_titles(week_dates: list) -> list:
    titles = []
    for d in week_dates:
        p = BRIEFS / d[:4] / d[5:7] / f"{d}.md"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if re.match(r"^##\s+[^#]", line) and "中文" not in line and "English" not in line:
                    t = line.lstrip("# ").strip()
                    if t and t not in titles:
                        titles.append(t)
    return titles[:8]


def build(week: str, today: date) -> dict:
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    dates = sorted(k for k in data if re.match(r"^\d{4}-\d{2}-\d{2}$", k))

    def latest(key):
        """按键回退:最新一天可能只有 news,逐日往前找最近有该模型数据的一天(与主站同逻辑)。"""
        for d in reversed(dates):
            v = (data.get(d) or {}).get(key)
            if v:
                return v
        return {}

    g = latest("macro_gate")
    f = latest("fragility_gate")
    b = latest("dalio_bubble")
    m = latest("market_breadth")

    week_dates = [d for d in dates if _week_id(datetime.strptime(d, "%Y-%m-%d").date()) == week]
    titles = _week_brief_titles(week_dates)
    markets, fed = _fetch_markets()

    mech = (f"机制层:衰退闸门 {g.get('votes', '?')}/6"
            f"{'(ON)' if g.get('gate_on') else ''} · 脆弱 {f.get('frag_score', '?')}/5 · "
            f"泡沫 {b.get('bubble_pct', '?')}%"
            f"{'(针ON)' if (b.get('pin') or {}).get('on') else ''} · 狭窄 {m.get('narrow_score', '?')}/3")
    narr = mech + ("。本周简报主题:" + " / ".join(titles) if titles else "。本周暂无归档简报(briefs/ 自动入库刚启用)")

    return {
        "snapshot_id": week,
        "date": today.isoformat(),
        "available_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "macro": {"fed_rate": fed, "core_pce": None, "cpi_yoy": None},
        "markets": markets,
        "geopolitics": [],
        "narrative": narr,
    }


def main():
    ap = argparse.ArgumentParser(description="周度环境快照(C7)")
    ap.add_argument("--week", help="ISO 周 id,如 2026-W33(默认本周)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    today = date.today()
    week = args.week or _week_id(today)

    existing = []
    if SNAP_FILE.exists():
        for line in SNAP_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if any(s.get("snapshot_id") == week for s in existing):
        print(f"· 快照 {week} 已存在,跳过(只追加,不改写)")
        return

    snap = build(week, today)
    print(json.dumps(snap, ensure_ascii=False, indent=2))
    if args.dry_run:
        return
    SNAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SNAP_FILE.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(snap, ensure_ascii=False) + "\n")
    print(f"💾 已追加快照 {week} → data/context_snapshots.jsonl")


if __name__ == "__main__":
    sys.exit(main())
