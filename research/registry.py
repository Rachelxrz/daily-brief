#!/usr/bin/env python3
"""
research/registry.py — 分析师/机构档案库的加载与查询(专项研究课题 Phase 1)。

档案 research/registry.jsonl:一人一档,把「判断 → 框架 → 监测方法 → 我们可算的代理
→ 可证伪检查点 → 对应模型」结构化。字段见 research/README.md。

用法:
  python research/registry.py                 # 打印汇总(按框架/模型分组)
  python research/registry.py --framework A   # 只看某框架(A/B/C/bull)
  python research/registry.py --model dalio_bubble
  from research.registry import load, by_framework, by_model, checks_due
"""
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

REGISTRY_FILE = Path(__file__).parent / "registry.jsonl"
REGISTRY_CHECKS_FILE = Path(__file__).parent / "registry_checks.jsonl"
HISTORY_FILE = Path(__file__).parent.parent / "analyst_history.jsonl"

FRAMEWORK_LABEL = {
    "A": "估值/泡沫 Valuation", "B": "仓位/尾部 Positioning",
    "C": "债务/货币 Debt/Monetary", "bull": "看多制衡 Bull",
}


def load() -> list:
    """读取 registry.jsonl → list[dict]。文件缺失返回空列表。"""
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


def by_framework(fw: str, recs=None) -> list:
    recs = recs if recs is not None else load()
    return [r for r in recs if fw in r.get("framework", []) or r.get("primary_framework") == fw]


def by_model(model: str, recs=None) -> list:
    recs = recs if recs is not None else load()
    return [r for r in recs if r.get("maps_to_model") == model]


def by_stance(stance: str, recs=None) -> list:
    recs = recs if recs is not None else load()
    return [r for r in recs if r.get("stance") == stance]


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def checks_due(today: str = None, recs=None) -> list:
    """返回检查点已到期(check_date <= today)的记录,并关联 registry 框架。
    合并两个来源:①analyst_history.jsonl 的策展/自动记录 ②registry_checks.jsonl 的
    registry 物化台账(sync_checks.py 生成)。按 (analyst, check_date, ticker) 去重。
    today 缺省用美东当日(YYYY-MM-DD)。"""
    if today is None:
        today = datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")
    reg = {r["name"]: r for r in (recs if recs is not None else load())}
    seen, out = set(), []
    for src, h in ([("history", x) for x in _iter_jsonl(HISTORY_FILE)]
                   + [("registry", x) for x in _iter_jsonl(REGISTRY_CHECKS_FILE)]):
        cd = h.get("check_date")
        if not (cd and cd <= today):
            continue
        analyst = h.get("analyst")
        ticker = h.get("ticker")
        key = (analyst, cd, ticker)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "analyst": analyst, "check_date": cd, "ticker": ticker,
            "check": h.get("check") or h.get("check_cn"),
            "framework": h.get("framework") or reg.get(analyst, {}).get("primary_framework"),
            "source": src,
        })
    out.sort(key=lambda x: x["check_date"])
    return out


def summary(recs=None) -> dict:
    recs = recs if recs is not None else load()
    fw, mdl, st, tracked = {}, {}, {}, 0
    for r in recs:
        fw[r["primary_framework"]] = fw.get(r["primary_framework"], 0) + 1
        mdl[r["maps_to_model"]] = mdl.get(r["maps_to_model"], 0) + 1
        st[r["stance"]] = st.get(r["stance"], 0) + 1
        tracked += 1 if r.get("tracked") else 0
    return {"total": len(recs), "by_framework": fw, "by_model": mdl,
            "by_stance": st, "tracked": tracked}


def _print(recs):
    order = ["A", "B", "C", "bull"]
    for fw in order:
        group = [r for r in recs if r.get("primary_framework") == fw]
        if not group:
            continue
        print(f"\n=== {FRAMEWORK_LABEL.get(fw, fw)} ({len(group)}) ===")
        for r in group:
            tag = "📡" if r.get("tracked") else "  "
            c = r.get("check", {})
            print(f"  {tag} {r['name']} · {r['firm']} [{r['stance']}] → {r['maps_to_model']}")
            print(f"       方法 {r['method_cn'][:46]}")
            print(f"       检查 {c.get('ticker','')}: {c.get('check_cn','')} ({c.get('horizon','')})")


def main():
    ap = argparse.ArgumentParser(description="分析师档案库查询")
    ap.add_argument("--framework", choices=["A", "B", "C", "bull"], help="按框架过滤")
    ap.add_argument("--model", help="按对应模型过滤(dalio_bubble/fragility_gate/macro_gate/counterweight)")
    ap.add_argument("--stance", choices=["bear", "cautious", "bull"], help="按立场过滤")
    ap.add_argument("--due", action="store_true", help="列出已到期的检查点(读 analyst_history.jsonl)")
    args = ap.parse_args()
    recs = load()
    if not recs:
        print("registry.jsonl 为空或缺失"); return
    if args.due:
        due = checks_due(recs=recs)
        print(f"已到期检查点:{len(due)} 条")
        for d in due:
            print(f"  ⏰ {d['check_date']} · {d['analyst']} [{d.get('framework') or '—'}] {d.get('ticker','')}: {d.get('check','')}")
        return
    if args.framework:
        recs = by_framework(args.framework, recs)
    if args.model:
        recs = by_model(args.model, recs)
    if args.stance:
        recs = by_stance(args.stance, recs)
    s = summary(recs)
    print(f"档案库:{s['total']} 人 · 已自动追踪 {s['tracked']} · 框架 {s['by_framework']} · 模型 {s['by_model']} · 立场 {s['by_stance']}")
    _print(recs)


if __name__ == "__main__":
    main()
