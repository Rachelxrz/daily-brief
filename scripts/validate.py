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
  python scripts/validate.py                              # 校验 data/ 下全部(含未注册文件→报错)
  python scripts/validate.py --file data/analysts.jsonl
  python scripts/validate.py --append-only-base origin/main   # 另查只追加:相对 base,旧行必须原样保留
退出码:0=全部通过;1=有错误(CI 拦截)。
"""
import argparse
import json
import re
import subprocess
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
        "identity": "id",
    },
    "context_snapshots.jsonl": {
        "required": {"snapshot_id": str, "date": str, "narrative": str},
        "optional": {"macro": dict, "markets": dict, "geopolitics": list,
                     "available_at": str, "supersedes": str},
        "dates": ["date"],
        "enums": {},
        "identity": "snapshot_id",
    },
    "reviews.jsonl": {
        # 复盘七字段全部必填(工作计划书/宪法·复盘纪律)
        "required": {"claim_id": str, "review_date": str, "outcome": str, "error_type": str,
                     "timing": str, "missed_factors": str, "key_references": str,
                     "my_action": str, "lesson": str},
        "optional": {"supersedes": str},
        "dates": ["review_date"],
        "enums": {},
        "identity": "claim_id",
    },
    "registry.jsonl": {
        # experiment registry:每次尝试的变量/阈值/权重(含失败版本)
        "required": {"date": str, "experiment": str, "params": dict, "outcome": str},
        "optional": {"hash": str, "notes": str},
        "dates": ["date"],
        "enums": {},
        "identity": None,
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
        # supersedes 与身份字段:先查 supersedes(此时 ids 尚不含本行 → 自引用被拦),再登记本行身份
        id_field = schema.get("identity")
        cur_id = rec.get(id_field) if id_field else None
        sup = rec.get("supersedes")
        if sup:
            if id_field is None:
                errs.append(f"{loc}: 本文件 schema 无身份字段,不支持 supersedes")
            elif sup not in ids:
                errs.append(f"{loc}: supersedes={sup} 未指向本文件**前文**的 {id_field}"
                            f"(自引用/前向引用均非法;更正行须在原行之后追加)")
        if isinstance(cur_id, str) and cur_id:
            if cur_id in ids and not sup:
                errs.append(f"{loc}: {id_field} 重复 {cur_id}(重复身份仅允许于带 supersedes 的更正行)")
            ids.add(cur_id)
    return errs


def check_append_only(base_ref: str) -> list:
    """只追加检查:相对 base_ref,data/*.jsonl 的旧内容必须是新内容的**行前缀**
    (不得改写/删除/插队任何历史行;base 无此文件=新文件,放行)。"""
    errs = []
    for path in sorted(DATA.glob("*.jsonl")):
        rel = path.relative_to(REPO).as_posix()
        try:
            old = subprocess.run(["git", "show", f"{base_ref}:{rel}"], cwd=REPO,
                                 capture_output=True, text=True)
        except Exception as e:
            errs.append(f"{rel}: git show 失败 — {e}")
            continue
        if old.returncode != 0:
            continue                     # base 无此文件 → 新增,放行
        old_lines = old.stdout.splitlines()
        new_lines = path.read_text(encoding="utf-8").splitlines()
        if new_lines[: len(old_lines)] != old_lines:
            for i, (o, nnew) in enumerate(zip(old_lines, new_lines), 1):
                if o != nnew:
                    errs.append(f"{rel}:{i}: 历史行被改写(JSONL 只追加;更正用新行+supersedes)")
                    break
            else:
                errs.append(f"{rel}: 历史行被删除(旧 {len(old_lines)} 行 > 新 {len(new_lines)} 行)")
    return errs


def main():
    ap = argparse.ArgumentParser(description="data/*.jsonl schema 校验")
    ap.add_argument("--file", help="只校验指定文件(默认 data/ 下全部 *.jsonl,未注册者报错)")
    ap.add_argument("--append-only-base", metavar="REF",
                    help="另查只追加:相对该 git ref(如 origin/main),旧行必须原样保留")
    args = ap.parse_args()
    if args.file:
        targets = [Path(args.file)]
    else:
        # 实际存在的 data/*.jsonl ∪ 已注册名:新增未注册文件会进 validate_file 的「无对应 schema」错;
        # 已注册但被删的文件也会被点名(0 行不报错,文件消失由 append-only/git 兜底)
        targets = sorted({*(DATA.glob("*.jsonl")), *(DATA / n for n in SCHEMAS)})
    all_errs = []
    for p in targets:
        errs = validate_file(p)
        n = len(p.read_text(encoding='utf-8').splitlines()) if p.exists() else 0
        print(f"  {'✅' if not errs else '❌'} {p.name}: {n} 行, {len(errs)} 错")
        all_errs += errs
    if args.append_only_base:
        ao = check_append_only(args.append_only_base)
        print(f"  {'✅' if not ao else '❌'} append-only vs {args.append_only_base}: {len(ao)} 错")
        all_errs += ao
    for e in all_errs:
        print("   ·", e)
    sys.exit(1 if all_errs else 0)


if __name__ == "__main__":
    main()
