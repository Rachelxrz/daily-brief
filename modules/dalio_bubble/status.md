# 达利欧泡沫指标 + 货币收紧扳机 — 进度追踪 (status.md)

**最后更新**: 2026-08-07
**当前版本**: v1.0（已实现并接入）
**负责角色**: Claude Code
**依赖**: FRED（WILL5000INDFC/GDP/FEDFUNDS/DFII10）+ yfinance（^NDX/^VIX/IPO）

---

## 已完成 v1.0

### 泡沫指标 6 表
- [x] 估值：巴菲特指标 Wilshire5000/GDP 历史分位
- [x] 涨势不可持续：纳指近 12 月回报分位
- [x] 新买家：IPO ETF 近 6 月回报分位（退化用 ARKK）
- [x] 看多情绪：1 − VIX 分位
- [x] 杠杆：1 − 实现波动分位（代理）
- [x] 远期建设：dalio_config.json 人工档
- [x] 均值 → 泡沫读数 % + 三档（≥80 晚期 / ≥60 偏高 / <60 中性），可用表不足时按可得表求均值

### 货币收紧扳机
- [x] FEDFUNDS 6 月变化 + DFII10 3 月变化 → pin.on

### 判读（达利欧式）
- [x] 泡沫高 + 无 pin → melt-up（amber）
- [x] 泡沫高 + pin → 破裂风险（red）
- [x] 泡沫低 → green

### 接入
- [x] 写入 `docs/data.json` 的 `dalio_bubble`
- [x] `docs/index.html` `renderDalioBubble()`（中英双语、null-safe、含 0–100% 表条与 60/80 门槛线）
- [x] 接入 `daily_brief.yml` + `macro_gate.yml`（排在 fragility_gate 之后）
- [x] 合成数据单元测试：3 种体制（melt-up / pop-risk / low）判读与 pin 逻辑 + 纯函数分位/变化

---

## 已知限制 / 待办

- [ ] 表 5「杠杆」为低波动代理，非 FINRA 真实保证金余额（无稳定免费源）；可后续接入月度保证金数据。
- [ ] 表 6「远期建设」为人工档，需季度校准 `dalio_config.json`。
- [ ] 表 1 用巴菲特指标近似达利欧的「估值 vs 传统度量」；未含 CAPE/远期 PE。
- [ ] 本地无法跑 FRED/yfinance 端到端（沙箱网络策略封 Yahoo 与 FRED）；线上 GitHub Actions 正常。

---

## 备注

- 与 `macro_gate`（衰退）、`fragility_gate`（1987 仓位）**三者正交、互不混票**。
- 达利欧 vs Burry 框架对比见 `notes/1987型崩盘_vs_六因子闸门.md` 第 6 节。
- 对应分析师板块记录：`analyst_history.jsonl` 中 Ray Dalio（GLD，检查点 2027-02-04）。
