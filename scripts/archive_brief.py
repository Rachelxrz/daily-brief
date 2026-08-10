#!/usr/bin/env python3
"""
scripts/archive_brief.py — 每日简报归档 briefs/YYYY/MM/YYYY-MM-DD.md(C1 后半)

从 docs/data.json 取指定/最新一天的 news(cn+en),写成一份双语 Markdown 存入
briefs/,随 daily_brief workflow 的既有 commit 步骤一并入库(永不删除)。

纪律:
  · **只追加**:目标文件已存在则跳过(不覆盖当日已归档版本;需要更正另存 -r1 后缀由人工处理)
  · 幂等、纯 stdlib、失败不抛(exit 0 + 提示),不拖垮既有简报管线(continue-on-error 双保险)

用法:
  python scripts/archive_brief.py            # 归档 data.json 里最新一天
  python scripts/archive_brief.py --date 2026-08-09
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "docs" / "data.json"
BRIEFS = REPO / "briefs"


def main():
    ap = argparse.ArgumentParser(description="每日简报归档到 briefs/YYYY/MM/")
    ap.add_argument("--date", help="YYYY-MM-DD(默认取 data.json 最新一天)")
    args = ap.parse_args()

    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ 读取 data.json 失败,跳过归档:{e}")
        return 0

    dates = sorted(k for k in data if re.match(r"^\d{4}-\d{2}-\d{2}$", k))
    day = args.date or (dates[-1] if dates else None)
    if not day or day not in data:
        print(f"⚠️ 无可归档日期(day={day}),跳过")
        return 0
    news = data[day].get("news") or {}
    cn, en = news.get("cn") or "", news.get("en") or ""
    if not cn.strip() and not en.strip():
        print(f"⚠️ {day} 无 news 内容,跳过")
        return 0

    out = BRIEFS / day[:4] / day[5:7] / f"{day}.md"
    if out.exists():
        print(f"· {out.relative_to(REPO)} 已存在,跳过(briefs 只追加,不覆盖)")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    parts = [f"# Daily Brief {day}", ""]
    if news.get("scraped_at"):
        parts += [f"> scraped_at: {news['scraped_at']}", ""]
    if cn.strip():
        parts += ["## 中文", "", cn.strip(), ""]
    if en.strip():
        parts += ["## English", "", en.strip(), ""]
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"✅ 已归档 {out.relative_to(REPO)}({len(cn)}+{len(en)} 字符)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
