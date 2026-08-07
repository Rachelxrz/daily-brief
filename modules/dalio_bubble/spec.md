# 达利欧泡沫指标 + 货币收紧扳机 — 功能规格 (spec.md)

**模块文件**: `dalio_bubble.py` · **配置**: `dalio_config.json`
**创建日期**: 2026-08-07
**状态**: 已实现 v1.0（见 status.md）
**背景/分析**: `notes/1987型崩盘_vs_六因子闸门.md`（第 6 节 Burry vs 达利欧框架对比）

---

## 模块目标

操作化 Ray Dalio 的两条招牌框架，回答两个问题：**泡沫「有多大」**、以及**「何时会被戳破」**。与另外两个体制模块**正交、互不混票**：

| 模块 | 监测 |
|------|------|
| `macro_gate` | 衰退 / 信用体制（基本面熊市） |
| `fragility_gate` | 健康经济里的仓位机械闪崩（Burry / 1987 型） |
| **`dalio_bubble`** | **泡沫幅度 + 货币收紧扳机（达利欧 / 债务周期型）** |

达利欧核心论断：**「泡沫在被货币政策收紧戳破之前，不会真正破裂」**——所以本模块把「泡沫读数」和「货币扳机」分开输出，两者组合才给出判读。

---

## 功能一：泡沫指标（6 表，各 0–1，均值 ×100 = 泡沫读数 %）

| # | 表 | 计算 | 数据源 |
|---|----|------|--------|
| 1 | 估值 | 巴菲特指标 Wilshire5000/GDP，历史分位 | FRED `WILL5000INDFC` / `GDP` |
| 2 | 涨势不可持续 | 纳指 `^NDX` 近 12 月回报的历史分位 | yfinance |
| 3 | 新买家 / 发行热 | IPO ETF（`IPO`，退化用 `ARKK`）近 6 月回报的历史分位 | yfinance |
| 4 | 看多情绪 | VIX 低位 = 自满 → 1 − VIX 分位 | yfinance |
| 5 | 杠杆买入 | 实现波动极低 → 系统/vol-target 加杠杆：1 − 波动分位（**代理**，FINRA 保证金无免费源） | yfinance·代理 |
| 6 | 远期建设 | AI 资本开支超前变现，无免费数据 → `dalio_config.json` 人工档 | config·人工 |

**分档**：≥80% = 晚期泡沫（类 1929/2000）；60–80% = 偏高；<60% = 中性/低。
可用表不足时按可得表求均值，并记 `gauges_used/gauges_total`。

## 功能二：货币收紧「扳机（pin）」

- 联邦基金利率 `FEDFUNDS` 近 6 月变化 ≥ +0.25% → 收紧
- 10 年期实际利率 `DFII10` 近 3 月变化 ≥ +0.25% → 收紧
- 任一成立 → `pin.on = True`

## 判读（达利欧式，区别于择时）

| 条件 | 判读 | 颜色 |
|------|------|------|
| 泡沫 ≥60% 且 **无** pin | 🫧 先融涨（melt-up）：分散 + 5–15% 黄金，勿裸空 | amber |
| 泡沫 ≥60% 且 **有** pin | 📌 戳破泡沫的针已现，破裂/去杠杆风险上升 | red |
| 泡沫 <60% | 🟢 读数不高 | green |

---

## 输出

写入 `docs/data.json` 的 `[today]["dalio_bubble"]`：`bubble_pct / band / band_color / gauges[] / pin{} / verdict / verdict_color / gauges_used / note`。
网页 `docs/index.html` 「结构监控」页 `renderDalioBubble()`，位于脆弱性侧栏下方，中英双语。**不推送微信**。

## 运行时机

`daily_brief.yml`（盘后）与 `macro_gate.yml`（盘中每小时）中，排在 `fragility_gate.py` 之后运行。均 `continue-on-error: true`。

## 边界

- 巴菲特指标/利率来自 FRED，涨势/情绪/杠杆来自 yfinance，**远期建设为人工档**（季度校准 `dalio_config.json`）。
- 杠杆为**代理**（低波动→系统加杠杆），非 FINRA 真实保证金余额。
- 数据缺失优雅降级：缺失表不计入均值。**不构成投资建议**。
