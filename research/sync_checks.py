#!/usr/bin/env python3
"""
research/sync_checks.py — 把 registry.jsonl 的可证伪 check 物化成「带绝对到期日」的检查点,
写入 research/registry_checks.jsonl(预测记账台账,供 Phase 3 回测 / Phase 4 打分)。

- 到期日 = 该人 registry 的 `latest`(YYYY-MM)+ `horizon` 换算的月数。
- horizon 解析:"3m"→3、"6-12m"→取上界12、"12-24m"→24、"long"/"open"→24(默认)。
- 确定性(不依赖当前时间),完全可复现;与 analyst_history 的策展记录分离,不污染网页分析师板。

用法:
  python research/sync_checks.py            # 生成/刷新 registry_checks.jsonl 并打印汇总
  python research/sync_checks.py --dry-run  # 仅打印,不写文件
"""
import argparse
import json
import re
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
REGISTRY_FILE = BASE / "registry.jsonl"
OUT_FILE = BASE / "registry_checks.jsonl"

DEFAULT_LONG_MONTHS = 24   # long/open 的默认到期跨度


def _load_registry() -> list:
    if not REGISTRY_FILE.exists():
        return []
    out = []
    for line in REGISTRY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _horizon_months(h: str) -> int:
    """把 horizon 文本换算成月数;区间取上界;long/open 用默认。"""
    if not h:
        return DEFAULT_LONG_MONTHS
    h = h.strip().lower()
    if h in ("long", "open"):
        return DEFAULT_LONG_MONTHS
    nums = [int(x) for x in re.findall(r"\d+", h)]
    if not nums:
        return DEFAULT_LONG_MONTHS
    return max(nums)          # 区间(如 6-12m / 12-24m)取上界


def _add_months(y: int, m: int, n: int) -> date:
    """YYYY-MM 的 15 号 + n 个月(月末安全,统一取 15 号避免跨月边界)。"""
    total = (y * 12 + (m - 1)) + n
    ny, nm = total // 12, total % 12 + 1
    return date(ny, nm, 15)


def _check_date(latest: str, horizon: str) -> str:
    """latest 'YYYY-MM' + horizon → 'YYYY-MM-DD'。latest 缺失/异常返回空串。"""
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", (latest or "").strip())
    if not m:
        return ""
    y, mo = int(m.group(1)), int(m.group(2))
    return _add_months(y, mo, _horizon_months(horizon)).isoformat()


def build() -> list:
    rows = []
    for r in _load_registry():
        c = r.get("check", {})
        cd = _check_date(r.get("latest", ""), c.get("horizon", ""))
        if not cd:
            continue
        rows.append({
            "analyst": r["name"], "firm": r.get("firm", ""),
            "framework": r.get("primary_framework"), "stance": r.get("stance"),
            "maps_to_model": r.get("maps_to_model"),
            "ticker": c.get("ticker", ""),
            "check_cn": c.get("check_cn", ""), "check_en": c.get("check_en", ""),
            "horizon": c.get("horizon", ""),
            "stated": r.get("latest", ""), "check_date": cd,
            "source": "registry",
        })
    rows.sort(key=lambda x: x["check_date"])
    return rows


def main():
    ap = argparse.ArgumentParser(description="物化 registry check → registry_checks.jsonl 台账")
    ap.add_argument("--dry-run", action="store_true", help="仅打印,不写文件")
    args = ap.parse_args()
    rows = build()
    if not rows:
        print("无可物化的检查点(registry.jsonl 缺失或无 latest/horizon)"); return
    if not args.dry_run:
        OUT_FILE.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        print(f"写入 {len(rows)} 条 → {OUT_FILE}")
    else:
        print(f"[dry-run] 将生成 {len(rows)} 条检查点")
    for r in rows:
        print(f"  {r['check_date']} · {r['analyst']} [{r['framework']}/{r['stance']}] "
              f"{r['ticker']}: {r['check_cn']} ({r['horizon']})")


if __name__ == "__main__":
    main()
