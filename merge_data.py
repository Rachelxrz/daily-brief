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


def has_content(val) -> bool:
    """返回 True 表示该 dict 值里有实质数据（至少一个非空 list）。
    用于判断 congress / wheel 等模块数据是否为空壳（被其他 job 携带进来的旧快照）。
    """
    if not isinstance(val, dict):
        return True          # 非 dict（字符串/数字等）直接视为有内容
    lists = [v for v in val.values() if isinstance(v, list)]
    if not lists:
        return True          # 没有 list 字段，视为有内容（如 news dict）
    return any(len(lst) > 0 for lst in lists)


# 对每个日期，逐 key 合并
for date, day in new_data.items():
    if date not in current:
        current[date] = {}
    for key, val in day.items():
        cur_val = current[date].get(key)
        # 如果 current 已有此 key 且内容更丰富，而 new 是空壳 → 保留 current
        if cur_val is not None and not has_content(val) and has_content(cur_val):
            continue
        current[date][key] = val

with open(target, "w", encoding="utf-8") as f:
    json.dump(current, f, ensure_ascii=False, indent=2)

print(f"merge_data: {new_file.name} → {target.name} 合并完成")
