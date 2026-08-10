#!/usr/bin/env python3
"""
scripts/panel_alerts.py — 提示行引擎(C8):三类规则,服务端权威版

规则(与 review.html 客户端展示同口径,此处为写入 data.json 的权威计算):
  1. 临近验证期限:open 论断距 falsifiable_by ≤ 7 天,或已到期未复盘(reviews 无对应 claim_id)
  2. 分析师改口  :出现带 supersedes 的修正行 → 提示判 timing(leading/lagging)
  3. 层间新矛盾  :面板 open 论断中带 stance 字段者「bull 占比 ≥ 70%(样本≥3)」
                  且 机制层(tail_fragility ≥4 或 dalio ≥80)→ 提示人工研判
                  (stance 为 analysts.jsonl 可选字段;未标 stance 的论断不参与本规则)

输出 docs/data.json["panel_alerts"];纯 stdlib、确定性(--date 可复现)。
自检:--self-test 构造三类合成数据,断言各自触发(工作计划书 C8 验收)。
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DUE_SOON_DAYS = 7
BULL_SHARE_TH = 0.70
BULL_MIN_N = 3


def _jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def compute(claims: list, reviews: list, day_data: dict, today: date) -> list:
    alerts = []
    soon = today + timedelta(days=DUE_SOON_DAYS)
    reviewed = {r.get("claim_id") for r in reviews}
    superseded = {c["supersedes"] for c in claims if c.get("supersedes")}

    # 1) 到期/临近(只看链末端的 open 论断)
    for c in claims:
        if c.get("status") != "open" or c.get("id") in superseded:
            continue
        try:
            due = datetime.strptime(c.get("falsifiable_by", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        if due <= today and c.get("id") not in reviewed:
            alerts.append({"type": "overdue", "severity": "high",
                           "text": f"{c.get('analyst')}: {c.get('claim')}",
                           "due": c.get("falsifiable_by"), "claim_id": c.get("id"),
                           "action": "待复盘(reviews 七字段)"})
        elif today < due <= soon:
            alerts.append({"type": "due_soon", "severity": "medium",
                           "text": f"{c.get('analyst')}: {c.get('claim')}",
                           "due": c.get("falsifiable_by"), "claim_id": c.get("id"),
                           "action": "准备验证材料"})

    # 2) 改口
    for c in claims:
        if c.get("supersedes"):
            alerts.append({"type": "revision", "severity": "medium",
                           "text": f"{c.get('analyst')} 修正 {c['supersedes']} → {c.get('claim')}",
                           "due": c.get("date"), "claim_id": c.get("id"),
                           "action": "记录修正前后值,判 timing(leading/lagging)"})

    # 3) 层间矛盾(需 stance 字段;样本不足不触发)
    open_st = [c.get("stance") for c in claims
               if c.get("status") == "open" and c.get("id") not in superseded and c.get("stance")]
    if len(open_st) >= BULL_MIN_N:
        bull = sum(1 for s in open_st if s == "bull") / len(open_st)
        frag = (day_data.get("fragility_gate") or {}).get("frag_score")
        dal = (day_data.get("dalio_bubble") or {}).get("bubble_pct")
        mech_hot = (isinstance(frag, int) and frag >= 4) or (isinstance(dal, (int, float)) and dal >= 80)
        if bull >= BULL_SHARE_TH and mech_hot:
            alerts.append({"type": "cross_layer", "severity": "high",
                           "text": f"面板 bull 占比 {bull*100:.0f}%({len(open_st)}条) 而机制层高热"
                                   f"(fragility={frag}, dalio={dal})",
                           "due": today.isoformat(), "claim_id": None,
                           "action": "层间矛盾:人工研判(观点层乐观 vs 体系脆弱)"})
    return alerts


def self_test():
    today = date(2026, 8, 10)
    claims = [
        {"id": "a1", "analyst": "X", "claim": "已到期未复盘", "status": "open",
         "falsifiable_by": "2026-08-01"},
        {"id": "a2", "analyst": "Y", "claim": "三天后到期", "status": "open",
         "falsifiable_by": "2026-08-13"},
        {"id": "a3", "analyst": "Z", "claim": "改口新论断", "status": "open",
         "falsifiable_by": "2026-12-31", "supersedes": "a1"},
        {"id": "b1", "analyst": "P", "claim": "看多1", "status": "open", "stance": "bull", "falsifiable_by": "2027-01-01"},
        {"id": "b2", "analyst": "Q", "claim": "看多2", "status": "open", "stance": "bull", "falsifiable_by": "2027-01-01"},
        {"id": "b3", "analyst": "R", "claim": "看多3", "status": "open", "stance": "bull", "falsifiable_by": "2027-01-01"},
    ]
    day = {"fragility_gate": {"frag_score": 4}, "dalio_bubble": {"bubble_pct": 72}}
    al = compute(claims, [], day, today)
    types = {a["type"] for a in al}
    # a1 被 a3 supersedes → 不再当 overdue;a2 due_soon;a3 revision;b* + 机制热 → cross_layer
    assert "due_soon" in types, types
    assert "revision" in types, types
    assert "cross_layer" in types, types
    assert not any(a["type"] == "overdue" and a["claim_id"] == "a1" for a in al), "被修正的 a1 不应再报 overdue"
    # overdue 触发:未被修正的过期条
    al2 = compute([{"id": "c1", "analyst": "W", "claim": "过期", "status": "open",
                    "falsifiable_by": "2026-08-01"}], [], {}, today)
    assert al2 and al2[0]["type"] == "overdue", al2
    # 已复盘的过期条不再报
    al3 = compute([{"id": "c1", "analyst": "W", "claim": "过期", "status": "open",
                    "falsifiable_by": "2026-08-01"}], [{"claim_id": "c1"}], {}, today)
    assert not al3, al3
    # 机制层不热 → 无 cross_layer
    al4 = compute(claims, [], {"fragility_gate": {"frag_score": 1}, "dalio_bubble": {"bubble_pct": 50}}, today)
    assert "cross_layer" not in {a["type"] for a in al4}
    print("🎉 panel_alerts self-test 全过(三类规则 + 反例均正确)")


def main():
    ap = argparse.ArgumentParser(description="提示行引擎(C8)")
    ap.add_argument("--date", help="YYYY-MM-DD(默认今天)")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    today = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    claims = _jsonl(REPO / "data" / "analysts.jsonl")
    reviews = _jsonl(REPO / "data" / "reviews.jsonl")
    data_file = REPO / "docs" / "data.json"
    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    dates = sorted(k for k in data if k[:2] == "20")
    day_data = data.get(dates[-1], {}) if dates else {}
    alerts = compute(claims, reviews, day_data, today)
    print(f"🔔 {today} 提示 {len(alerts)} 条:")
    for a in alerts:
        print(f"  [{a['severity']:>6}|{a['type']}] {a['text']}  → {a['action']}")
    if args.dry_run:
        return
    data["panel_alerts"] = {"date": today.isoformat(), "alerts": alerts}
    data_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("💾 已写入 docs/data.json['panel_alerts']")


if __name__ == "__main__":
    main()
