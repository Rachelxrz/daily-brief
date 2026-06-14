#!/usr/bin/env python3
"""
merge_data.py — 将本次 job 写入的 data.json 合并到最新的 remote data.json，
保留其他 job 已写入的 key，不覆盖。

GitHub Actions commit 步骤用法:
  cp docs/data.json /tmp/new_data.json
  git fetch origin main && git reset --hard origin/main
  python merge_data.py /tmp/new_data.json docs/data.json
  git add docs/data.json && git diff --staged --quiet || git commit ...
"""
import json
import sys
from pathlib import Path

if len(sys.argv) != 3:
    print("用法: python merge_data.py <new_data.json> <target_data.json>")
    sys.exit(1)

new_file = Path(sys.argv[1])
target   = Path(sys.argv[2])

with open(new_file, encoding="utf-8") as f:
    new_data = json.load(f)

current = {}
if target.exists():
    try:
        with open(target, encoding="utf-8") as f:
            current = json.load(f)
    except Exception:
        pass

# 对每个日期，逐 key 合并（只新增/更新，不删除其他 job 的 key）
for date, day in new_data.items():
    if date not in current:
        current[date] = {}
    for key, val in day.items():
        current[date][key] = val

with open(target, "w", encoding="utf-8") as f:
    json.dump(current, f, ensure_ascii=False, indent=2)

print(f"merge_data: {new_file.name} → {target.name} 合并完成")
