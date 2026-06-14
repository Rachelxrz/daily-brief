#!/usr/bin/env python3
"""
update_status.py — 自动刷新 PROJECT_STATUS.md 的 AUTO 区块。

只重写 <!-- AUTO:START --> 与 <!-- AUTO:END --> 之间的内容；
其余部分（已知问题、下一步优先级等人工判断）原样保留，绝不覆盖。

数据来源（零侵入，不需要改任何现有模块）：
  - docs/data.json   → 今日各模块是否产出（news / monitor / congress / wheel ...）
  - git log          → 自上次刷新以来的开发 commit（自动过滤每日数据提交）

用法：
  python update_status.py            # 刷新 AUTO 区块并写回文件
  python update_status.py --dry-run  # 只打印将要写入的内容，不改文件
"""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT        = Path(__file__).parent
STATUS_FILE = ROOT / "PROJECT_STATUS.md"
DATA_FILE   = ROOT / "docs" / "data.json"
CST         = timezone(timedelta(hours=8))

AUTO_START = "<!-- AUTO:START — 程序生成，请勿手改 -->"
AUTO_END   = "<!-- AUTO:END -->"

# data.json 里 data[today] 的 key → 人类可读模块名
# 以后 congress/wheel 模块只要往 data[today] 写自己的 key，这里加一行即可
MODULE_KEYS = {
    "news":     "每日简报 (main.py)",
    "monitor":  "市场结构监控 (market_monitor.py)",
    "congress": "国会交易信号 (congress_tracker.py)",
    "wheel":    "Wheel Strategy (wheel_strategy.py)",
}

# 每日例行/自动提交，不算"开发工作"，从变更日志里过滤掉
ROUTINE_COMMIT_PREFIXES = (
    "Daily news brief",
    "Market monitor",
    "Update PROJECT_STATUS",
)


def now_cst() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M CST")


def today_cst() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


def module_status() -> tuple[list[str], str]:
    """从 data.json 读出今日各模块是否产出。返回 (状态行列表, data.json更新时间)。"""
    data = {}
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    day = data.get(today_cst(), {})
    lines = []
    for key, label in MODULE_KEYS.items():
        produced = bool(day.get(key))
        lines.append(f"- {label}：{'✅ 今日已产出' if produced else '⚪ 今日无产出'}")
    return lines, day.get("updated", "—")


def git_changes(max_commits: int = 15) -> list[str]:
    """自上次刷新 PROJECT_STATUS.md 以来的开发 commit（过滤掉例行提交）。"""
    try:
        last = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", "PROJECT_STATUS.md"],
            capture_output=True, text=True, cwd=ROOT,
        ).stdout.strip()

        if last:
            args = ["git", "log", f"{last}..HEAD", "--format=%h|%ad|%s", "--date=short"]
        else:  # 文件还没被提交过：退回最近 N 条
            args = ["git", "log", f"-{max_commits}", "--format=%h|%ad|%s", "--date=short"]

        raw = subprocess.run(args, capture_output=True, text=True, cwd=ROOT).stdout.strip()
        if not raw:
            return ["- （自上次刷新以来无新 commit）"]

        kept = []
        for line in raw.splitlines():
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            short, date, subject = parts
            if any(subject.startswith(p) for p in ROUTINE_COMMIT_PREFIXES):
                continue
            kept.append(f"- `{short}` {date} — {subject}")

        if not kept:
            return ["- （自上次刷新以来仅有自动数据提交，无开发 commit）"]
        return kept[:max_commits]

    except Exception as e:
        return [f"- （读取 git 历史失败：{e}）"]


def build_auto_block() -> str:
    mod_lines, updated = module_status()
    block = [
        AUTO_START,
        "",
        f"**自动刷新时间**：{now_cst()}",
        f"**data.json 今日更新**：{updated}",
        "",
        "**今日各模块产出状态**（依据 `docs/data.json`）：",
        *mod_lines,
        "",
        "**自上次刷新以来的开发变更**（git commit，已过滤每日数据提交）：",
        *git_changes(),
        "",
        AUTO_END,
    ]
    return "\n".join(block)


def splice(content: str, new_block: str) -> str:
    """只替换 marker 之间的内容；没有 marker 就追加到文件末尾。"""
    if AUTO_START in content and AUTO_END in content:
        pre  = content.split(AUTO_START)[0]
        post = content.split(AUTO_END, 1)[1]
        return pre + new_block + post
    return content.rstrip() + "\n\n" + new_block + "\n"


def main() -> None:
    block = build_auto_block()

    if "--dry-run" in sys.argv:
        print(block)
        return

    content = (
        STATUS_FILE.read_text(encoding="utf-8")
        if STATUS_FILE.exists()
        else "# Daily Brief — 项目状态总览 (PROJECT_STATUS.md)\n"
    )
    STATUS_FILE.write_text(splice(content, block), encoding="utf-8")
    print(f"✅ 已刷新 {STATUS_FILE} 的 AUTO 区块")


if __name__ == "__main__":
    main()
