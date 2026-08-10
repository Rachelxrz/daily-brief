#!/usr/bin/env python3
"""
predict.py — 自我校准层:Rachel 本人判断的预测日志 + 合理化检测(三组件·第三层)

> 按《三组件系统宪法》与《工作计划书》的接口在仓库内实现(纯 stdlib,事件驱动)。
> 若本地/InvestOS 已有历史版本,以本文件 schema 为准迁移合并(data/predictions.jsonl 只追加)。

三个动作:
  记录   python predict.py add "SPX 年底前回撤>10%" --basis "采纳 Burry 脆弱性论据,拒绝 Tom Lee 7700" \
             --falsifiable-by 2026-12-31 --confidence 60 [--rationalized "看到上周下跌后才想记录"]
  复盘   python predict.py resolve <id> --outcome hit|miss|partial --note "实际:回撤12%"
  查看   python predict.py list [--open|--due|--rationalized] / python predict.py stats

合理化检测(--rationalized)——宪法的核心纪律:
  · 记录判断时,若「结论先于论据」「看到结果附近的信息后才补记」「只是想让过去的观点显得对」,
    必须带 --rationalized <一句话诱因>。该预测计入档案但**单独统计**,不进净命中率。
  · stats 输出把 clean 与 rationalized 分开:防止「事后觉得自己早就知道」污染自我校准。

与其他两层对账:
  · basis 字段写明「采纳/拒绝了哪些分析师论据」→ 复盘时与 reviews.jsonl 的 my_action 互查。
  · 数据:data/predictions.jsonl(只追加,更正新行+supersedes;schema 由 scripts/validate.py 强制,CI 拦截)。
不构成投资建议。
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent
FILE = REPO / "data" / "predictions.jsonl"
DUE_SOON_DAYS = 7


def _load() -> list:
    if not FILE.exists():
        return []
    out = []
    for n, line in enumerate(FILE.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.exit(f"data/predictions.jsonl:{n} 非法 JSON:{e}")
    return out


def _append(rec: dict):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    with FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _new_id(recs: list, today: str) -> str:
    base = today.replace("-", "")
    n = sum(1 for r in recs if r.get("id", "").startswith(base)) + 1
    return f"{base}-me-{n:02d}"


def cmd_add(args):
    recs = _load()
    today = date.today().isoformat()
    try:
        datetime.strptime(args.falsifiable_by, "%Y-%m-%d")
    except ValueError:
        sys.exit("--falsifiable-by 须为 YYYY-MM-DD")
    rec = {
        "id": _new_id(recs, today),
        "date": today,
        "statement": args.statement,
        "basis": args.basis or "",
        "confidence": args.confidence,
        "falsifiable_by": args.falsifiable_by,
        "rationalized": bool(args.rationalized),
        "rationalized_note": args.rationalized or "",
        "status": "open",
    }
    if args.supersedes:
        prev = next((r for r in recs if r.get("id") == args.supersedes), None)
        if prev is None:
            sys.exit(f"supersedes={args.supersedes} 不存在")
        # 合理化标记沿链继承(OR):一旦某条链被标 rationalized,其更正行不得洗白回 clean——
        # 否则「补记后再改一笔」就能混进净命中率,恰是该纪律要防的
        if prev.get("rationalized") and not rec["rationalized"]:
            rec["rationalized"] = True
            rec["rationalized_note"] = f"继承自 {args.supersedes}: {prev.get('rationalized_note', '')}".strip()
        rec["supersedes"] = args.supersedes
    _append(rec)
    tag = " ⚠️rationalized(不进净命中率)" if rec["rationalized"] else ""
    print(f"✅ 已记录 {rec['id']}{tag}: {rec['statement']}  [验证期限 {rec['falsifiable_by']}]")


def cmd_resolve(args):
    recs = _load()
    target = next((r for r in recs if r.get("id") == args.id), None)
    if target is None:
        sys.exit(f"未找到 id={args.id}")
    if target.get("status") != "open":
        sys.exit(f"{args.id} 已复盘过(只追加:不可改写历史)")
    # 被任何后继行(无论 open 还是已复盘)supersedes 的预测不可再复盘——
    # 否则「A 被 B 修正后仍 resolve A」会让 _latest_view 同时保留 A 的复盘与 B,双计一条判断
    successor = next((r for r in recs if r.get("supersedes") == args.id), None)
    if successor is not None:
        sys.exit(f"{args.id} 已被 {successor.get('id')} 修正(supersedes),请复盘链上最新的那条")
    rec = {
        "id": f"{args.id}r",
        "date": date.today().isoformat(),
        "statement": target["statement"],
        "basis": target.get("basis", ""),
        "confidence": target.get("confidence"),
        "falsifiable_by": target["falsifiable_by"],
        "rationalized": target.get("rationalized", False),
        "rationalized_note": target.get("rationalized_note", ""),
        "status": args.outcome,
        "outcome_note": args.note or "",
        "supersedes": args.id,
    }
    _append(rec)
    print(f"✅ 复盘 {args.id} → {args.outcome}: {args.note or ''}")


def _latest_view(recs: list) -> list:
    """supersedes 折叠:每条链取最后一行(展示用;档案本身只追加)。"""
    superseded = {r["supersedes"] for r in recs if r.get("supersedes")}
    return [r for r in recs if r.get("id") not in superseded]


def cmd_list(args):
    recs = _latest_view(_load())
    today = date.today()
    soon = today + timedelta(days=DUE_SOON_DAYS)
    rows = []
    for r in recs:
        due = datetime.strptime(r["falsifiable_by"], "%Y-%m-%d").date()
        if args.open and r["status"] != "open":
            continue
        if args.due and not (r["status"] == "open" and due <= soon):
            continue
        if args.rationalized and not r.get("rationalized"):
            continue
        flag = "⏰" if (r["status"] == "open" and due <= soon) else ""
        rat = "⚠️R" if r.get("rationalized") else "  "
        rows.append(f"  [{r['status']:>7}]{rat} {r['id']}  {r['falsifiable_by']}{flag}  "
                    f"conf={r.get('confidence')}  {r['statement']}"
                    + (f"\n            basis: {r['basis']}" if r.get("basis") else ""))
    print("\n".join(rows) if rows else "  (无记录)")


def cmd_stats(_args):
    recs = _latest_view(_load())
    done = [r for r in recs if r["status"] in ("hit", "miss", "partial")]
    clean = [r for r in done if not r.get("rationalized")]
    rat = [r for r in done if r.get("rationalized")]

    def rate(rs):
        if not rs:
            return "—"
        h = sum(1 for r in rs if r["status"] == "hit") + 0.5 * sum(1 for r in rs if r["status"] == "partial")
        return f"{h / len(rs) * 100:.0f}% ({len(rs)}条)"

    n_open = sum(1 for r in recs if r["status"] == "open")
    print(f"  自我校准 · 净命中率(clean): {rate(clean)}   ⚠️rationalized 单独统计: {rate(rat)}   未决: {n_open}")
    if clean and rat and len(rat) >= 3:
        print("  提示:rationalized 命中率若显著高于 clean,即合理化污染信号——回看 rationalized_note。")


def main():
    ap = argparse.ArgumentParser(description="自我校准层:预测日志 + 合理化检测")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="记录一条本人判断")
    a.add_argument("statement")
    a.add_argument("--basis", help="采纳/拒绝了哪些分析师论据(与 reviews.my_action 对账)")
    a.add_argument("--confidence", type=int, help="主观置信度 0-100")
    a.add_argument("--falsifiable-by", required=True, dest="falsifiable_by")
    a.add_argument("--rationalized", metavar="诱因", help="合理化标记:结论先于论据/看到结果后补记(单独统计)")
    a.add_argument("--supersedes", help="修正既有预测的 id")
    a.set_defaults(func=cmd_add)
    r = sub.add_parser("resolve", help="到期复盘(追加新行,不改写)")
    r.add_argument("id")
    r.add_argument("--outcome", required=True, choices=["hit", "miss", "partial"])
    r.add_argument("--note", help="实际结果数字")
    r.set_defaults(func=cmd_resolve)
    ls = sub.add_parser("list", help="查看")
    ls.add_argument("--open", action="store_true")
    ls.add_argument("--due", action="store_true", help=f"仅 {DUE_SOON_DAYS} 天内到期/已到期")
    ls.add_argument("--rationalized", action="store_true")
    ls.set_defaults(func=cmd_list)
    st = sub.add_parser("stats", help="净命中率(clean 与 rationalized 分开)")
    st.set_defaults(func=cmd_stats)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
