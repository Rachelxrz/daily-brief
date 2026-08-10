#!/usr/bin/env python3
"""
scripts/collection_calendar.py — 采集日历(C5):今天该采集哪些分析师更新

按 analyst-panel 项目计划的采集日历规则,判定给定日期应触发的采集任务,
写入 docs/data.json["collection_due"](供 panel.html 展示),不推微信。
纯 stdlib、确定性(--date 可复现);采集原则:只记「新论断或修正」。

规则(美东日历近似;FOMC 用官方 2026 日程静态表,变动改 FOMC_2026):
  · 宏观   : CPI(每月 10-15 日提示)· 非农(每月首个周五)· FOMC 会前1日+会后1日
  · 策略   : 每周一(Wilson 周报/Kostin)· 11-12 月年度展望季 · 5-6 月中期修正季
  · 能源   : EIA 周度库存(周三)· OPEC 月报(每月 12-16 日提示)· EIA STEO(每月 6-10 日)
  · AI基建 : 财报季月(1/4/7/10)· TSMC 月度营收(每月 8-12 日)· SIA 月度(月初 1-5 日)
  · 货币黄金: WGC 央行购金季度报告(1/4/7/10 月末周)

用法: python scripts/collection_calendar.py [--date 2026-09-16] [--dry-run]
"""
import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA_FILE = REPO / "docs" / "data.json"

# 2026 FOMC 官方日程(第二日为决议日;如官方调整,改此表)
FOMC_2026 = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
             "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"]


def _first_friday(d: date) -> date:
    x = d.replace(day=1)
    return x + timedelta(days=(4 - x.weekday()) % 7)


def tasks_for(d: date) -> list:
    out = []
    wd = d.weekday()  # 0=Mon
    # 宏观
    if d == _first_friday(d):
        out.append({"layer": "macro", "task": "非农当日快评(Feroli/Gapen/Porcelli)", "why": "首个周五"})
    if 10 <= d.day <= 15:
        out.append({"layer": "macro", "task": "CPI 窗口:当日快评盯发布", "why": "月中 CPI"})
    for f in FOMC_2026:
        fd = datetime.strptime(f, "%Y-%m-%d").date()
        if d == fd - timedelta(days=1):
            out.append({"layer": "macro", "task": f"FOMC 会前预览必采(决议日 {f})", "why": "FOMC-1"})
        if d == fd + timedelta(days=1):
            out.append({"layer": "macro", "task": "FOMC 会后 24h 点评必采", "why": "FOMC+1"})
    # 策略
    if wd == 0:
        out.append({"layer": "strategy", "task": "Wilson 周报 / Kostin 更新", "why": "周一"})
    if d.month in (11, 12) and d.day <= 7 and wd == 0:
        out.append({"layer": "strategy", "task": "年度展望季:目标价与前提入库", "why": "11-12月"})
    if d.month in (5, 6) and d.day <= 7 and wd == 0:
        out.append({"layer": "strategy", "task": "中期修正季:核对年初前提", "why": "5-6月"})
    # 能源
    if wd == 2:
        out.append({"layer": "energy", "task": "EIA 周度库存(对照 GS Struyven 平衡表)", "why": "周三"})
    if 12 <= d.day <= 16:
        out.append({"layer": "energy", "task": "OPEC 月报窗口", "why": "月中"})
    if 6 <= d.day <= 10:
        out.append({"layer": "energy", "task": "EIA STEO 窗口", "why": "月初"})
    # AI 与基建
    if d.month in (1, 4, 7, 10) and 15 <= d.day <= 31 and wd == 0:
        out.append({"layer": "ai-infra", "task": "财报季:云厂商 capex 指引 + NVDA/TSMC(硬数据锚)", "why": "财报季"})
    if 8 <= d.day <= 12:
        out.append({"layer": "ai-infra", "task": "TSMC 月度营收(硬数据)", "why": "每月10日前后"})
    if d.day <= 5:
        out.append({"layer": "ai-infra", "task": "SIA 半导体月度销售", "why": "月初"})
    # 货币与黄金
    if d.month in (1, 4, 7, 10) and d.day >= 24:
        out.append({"layer": "fx-gold", "task": "WGC 央行购金季度报告 + 各行金价预测修正", "why": "季末周"})
    return out


def main():
    ap = argparse.ArgumentParser(description="采集日历(C5)")
    ap.add_argument("--date", help="YYYY-MM-DD(默认今天)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    d = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    tasks = tasks_for(d)
    print(f"📅 {d} 应采集 {len(tasks)} 项:")
    for t in tasks:
        print(f"  [{t['layer']:>8}] {t['task']}  ({t['why']})")
    if args.dry_run:
        return
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data["collection_due"] = {"date": d.isoformat(), "tasks": tasks,
                              "note": "采集原则:只记新论断或修正;修正必须含修正前后值"}
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("💾 已写入 docs/data.json['collection_due']")


if __name__ == "__main__":
    main()
