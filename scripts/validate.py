#!/usr/bin/env python3
"""
scripts/validate.py — data/*.jsonl schema 校验(三组件系统 · C2)

纯 stdlib。校验 analysts / context_snapshots / reviews / registry 四个 JSONL:
  · 每行必须是合法 JSON 对象
  · 必填字段齐全、类型正确
  · analysts.falsifiable_by / date 为 YYYY-MM-DD
  · reviews 七字段全部必填(outcome/error_type/timing/missed_factors/key_references/my_action/lesson)
  · 更正行须带 supersedes(指向既有 id),不允许改写历史行(由 git diff 保证,此处只查引用存在)

用法:
  python scripts/validate.py            # 校验 data/ 下全部
  python scripts/validate.py --file data/analysts.jsonl
退出码:0=全部通过;1=有错误(CI 拦截)。
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SCHEMAS = {
    "analysts.jsonl": {
        "required": {"id": str, "analyst": str, "firm": str, "layer": str, "date": str,
                     "claim": str, "falsifiable_by": str, "status": str},
        "optional": {"snapshot_id": str, "premise": str, "tags": list, "source_url": str,
                     "drive_file_id": str, "drive_path": str, "supersedes": str,
                     "fidelity": str, "model_ref": str},
        "dates": ["date", "falsifiable_by"],
        "enums": {"layer": {"macro", "strategy", "energy", "ai-infra", "fx-gold"},
                  "status": {"open", "hit", "miss", "partial", "superseded", "withdrawn"}},
    },
    "context_snapshots.jsonl": {
        "required": {"snapshot_id": str, "date": str, "narrative": str},
        "optional": {"macro": dict, "markets": dict, "geopolitics": list,
                     "available_at": str, "supersedes": str},
        "dates": ["date"],
        "enums": {},
    },
    "reviews.jsonl": {
        # 复盘七字段全部必填(工作计划书/宪法·复盘纪律)
        "required": {"claim_id": str, "review_date": str, "outcome": str, "error_type": str,
                     "timing": str, "missed_factors": str, "key_references": str,
                     "my_action": str, "lesson": str},
        "optional": {"supersedes": str},
        "dates": ["review_date"],
        "enums": {},
    },
    "registry.jsonl": {
        # experiment registry:每次尝试的变量/阈值/权重(含失败版本)
        "required": {"date": str, "experiment": str, "params": dict, "outcome": str},
        "optional": {"hash": str, "notes": str},
        "dates": ["date"],
        "enums": {},
    },
}


def validate_file(path: Path) -> list:
    errs = []
    schema = SCHEMAS.get(path.name)
    if schema is None:
        return [f"{path.name}: 无对应 schema(新文件须先在 validate.py 注册)"]
    known = set(schema["required"]) | set(schema["optional"])
    ids = set()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        loc = f"{path.name}:{n}"
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            errs.append(f"{loc}: 非法 JSON — {e}")
            continue
        if not isinstance(rec, dict):
            errs.append(f"{loc}: 每行必须是 JSON 对象")
            continue
        for field, typ in schema["required"].items():
            if field not in rec:
                errs.append(f"{loc}: 缺必填字段 {field}")
            elif not isinstance(rec[field], typ):
                errs.append(f"{loc}: {field} 应为 {typ.__name__}")
            elif typ is str and not rec[field].strip() and field != "premise":
                errs.append(f"{loc}: 必填字段 {field} 不得为空串")
        for field, typ in schema["optional"].items():
            if field in rec and rec[field] is not None and not isinstance(rec[field], typ):
                errs.append(f"{loc}: {field} 应为 {typ.__name__}")
        for field in schema["dates"]:
            v = rec.get(field)
            if isinstance(v, str) and v and not DATE_RE.match(v):
                errs.append(f"{loc}: {field}='{v}' 须为 YYYY-MM-DD")
        for field, allowed in schema["enums"].items():
            v = rec.get(field)
            if isinstance(v, str) and v not in allowed:
                errs.append(f"{loc}: {field}='{v}' 不在 {sorted(allowed)}")
        unknown = set(rec) - known
        if unknown:
            errs.append(f"{loc}: 未注册字段 {sorted(unknown)}(schema 先行:先改 validate.py)")
        if "id" in rec:
            if rec["id"] in ids:
                errs.append(f"{loc}: id 重复 {rec['id']}")
            ids.add(rec["id"])
        if rec.get("supersedes") and "id" in schema["required"] and rec["supersedes"] not in ids:
            errs.append(f"{loc}: supersedes={rec['supersedes']} 指向的 id 不在本文件前文(更正行须在原行之后追加)")
    return errs


def main():
    ap = argparse.ArgumentParser(description="data/*.jsonl schema 校验")
    ap.add_argument("--file", help="只校验指定文件(默认 data/ 下全部已注册文件)")
    args = ap.parse_args()
    targets = [Path(args.file)] if args.file else [DATA / n for n in SCHEMAS]
    all_errs = []
    for p in targets:
        errs = validate_file(p)
        n = len(p.read_text(encoding='utf-8').splitlines()) if p.exists() else 0
        print(f"  {'✅' if not errs else '❌'} {p.name}: {n} 行, {len(errs)} 错")
        all_errs += errs
    for e in all_errs:
        print("   ·", e)
    sys.exit(1 if all_errs else 0)


if __name__ == "__main__":
    main()
