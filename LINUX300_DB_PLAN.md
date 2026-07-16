# Linux300 数据库计划 — 讨论记录 (2026-07-16)

> **状态**：仅为设计记录，**尚未实施**。Rachel 换到 Linux300 之后再开始动手。
> **触发方式**：Rachel 在 Linux300 上说一声，即按第 6 节动手。

---

## 1. 背景 / 起因

`docs/data.json` 已长到 **5.1 MB / 61 天 / 947 条新闻卡片**，并且还在持续增长。

原因（已查证，非 bug）：
- `save_to_web.py` 的 `MAX_DAYS = 30` **只裁剪本地文件**；
- `merge_data.py` 只做「新增/覆盖」，**从不删除**远端已有日期；
- 因此本地裁剪后的结果合并回远端时，历史被完整保留 → **新闻实际上是无限期保留的，没有丢失任何数据**。

2026-07-16 Rachel 选择 **方案 A：先不动**（不裁剪、不分片、不改动现有流水线），并提出未来方向：

> 「未来我希望在我本地 Linux300 上建立数据库，把这些数据放进去，跟 Investment_OS 使用同一数据库」

---

## 2. 结论（已拍板的方向）

| 项 | 决定 |
|----|------|
| 建库位置 | 本地 **Linux300** |
| 数据流向 | **拉取式**：Linux300 定时 `git pull` daily-brief → 读 json/jsonl → 入库 |
| 与 Investment_OS 的关系 | **先各自独立，不合库** |
| Source of truth | **git 仓库**（数据库只是派生的分析层，库挂了重跑入库脚本即可） |
| 现有 GitHub Actions | **一行都不改** |
| 何时动手 | Rachel 换到 Linux300 之后 |

### 数据流

```
GitHub Actions（云端，照常跑）
    ↓ 提交 新闻 / 价格快照 / 分析师观点 到 daily-brief 仓库
Linux300 定时 cron → git pull → 读 json / jsonl → 幂等 upsert 入库
    ↓
daily-brief 专用数据库（先独立存在）
    ↓（将来）
Investment_OS 用【只读账号】接进来读
```

---

## 3. 关键认知：「共用数据」≠「必须合库」

这是本次讨论最重要的一点。

将来 Investment_OS 要用这些数据时，**最干净的做法是给它开一个只读账号，让它来读 daily-brief 这个库**，而不是把两个库合并。这样：

- 数据只有一份、不重复抓取 ✅（Rachel 想要的「共用」效果达成）
- 私有持仓数据**永远留在 Investment_OS 自己那边，不进这个库** ✅
- 边界**天然单向**，靠**数据库权限**强制，不靠人自觉 ✅

**推论**：现在「先独立建库」这一步，本身就已经是最终形态 —— 将来不需要合并，只要开只读账号接进来即可。反而是「真合成一个库」才需要额外的 schema 隔离设计。

---

## 4. 为什么是「拉取式」而不是别的

| 方案 | 结论 |
|------|------|
| **Linux300 定时 git pull 入库** | ✅ **采用**。零入站暴露、不改现有流水线、git 仍是 source of truth |
| GitHub Actions 直接写 Linux300 | ❌ Actions 根本连不到 Linux300（家宽/内网） |
| self-hosted runner | ❌ **危险**：daily-brief 是公开仓库，任何人提 PR 都可能在 Linux300 上执行代码 |
| 内网穿透 / 反向隧道 | ❌ 把数据库暴露到公网，得不偿失 |

---

## 5. 公私边界（必须守住的红线）

- **daily-brief 是公开仓库 + 公开站点**（GitHub Pages）。
- **Investment_OS 有 public-only egress 边界**，并有 `verify_part2_privacy_boundary.py` 做校验。
- 因此：**这个库里只放公开安全的数据**（新闻、ETF 价格快照、分析师公开言论）。
  **持仓、仓位、私有策略参数一律不进这个库。**
- 方向永远是 **daily-brief → 库 → Investment_OS 读**，**不允许反向回流**。

---

## 6. 动手时的落地清单（待执行）

Claude 负责在 **daily-brief 这边**准备（investment_OS 归 Codex 提交，Claude 不碰）：

1. **建表 DDL**
2. **入库脚本**：纯读现有文件，幂等 upsert，可重复执行

现有数据文件 → 表的天然映射：

| 源文件 | 目标表 | 说明 |
|--------|--------|------|
| `prediction_snapshots.jsonl` | `prices` | 已是「每周 × 15 标的」的时序结构，直接就是行 |
| `analyst_history.jsonl` | `analyst_calls` | 含 `stated_at` / `ticker` / `check_date`，命中率评分变成一句 SQL |
| `docs/data.json` → `news_cards` | `news` | 按 ET 日期 key 展开 |

**数据库选型**：
- 推荐 **PostgreSQL**（JSONB + 时序都好用，将来开只读账号给 Investment_OS 也自然）
- 若只做本地分析、不打算给别的系统连 → DuckDB 也够

---

## 7. 附带收益

数据进库后，原本要写脚本的事变成一句 SQL：
- 分析师**命中率统计**（`analyst_calls` join `prices`，按 `check_date` 判对错）
- 轮动**长周期回看**（不再受网页只显示 12 周的限制）
- 新闻**主题/来源趋势**（61 天以上的全量历史本来就在）

---

## 8. 讨论中确认过的事实（备查）

- 新闻**没有丢**：61 天 / 947 卡片 / 5.1 MB 全在远端 `docs/data.json` 里。
- `MAX_DAYS=30` 是**本地裁剪**，不影响远端累积。
- 跨天去重（`filter_recent_duplicates(days=3)`）已生效：7/15→7/16 条数由 43 降到 25。
- **BWET 显示 +955.5%**（19.27 → 203.35）疑似拆股/复权异常，**尚未处理**，Rachel 未选择（保留+标注 / 深查 / 剔除）。
