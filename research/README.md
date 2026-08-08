# 专项研究课题：市场判断 → 可用模型 · Research Project: Market Judgments → Usable Models

> 立项 Established: 2026-08-07 · 负责 Owner: Claude Code（编码）+ Claude（策略）· 状态 Status: 进行中 In progress
> 底稿 Companion docs: `research/analyst_frameworks_report.md`（分析师分框架报告）· `notes/1987型崩盘_vs_六因子闸门.md`（方法论）

---

## 1. 背景 · Background

我们已建成**三体制监测**（正交、互不混票）：
We have built a **three-regime monitor** (orthogonal, non-overlapping):

- 🚦 `macro_gate` — 衰退/信用体制 · recession/credit regime
- 🔥 `fragility_gate` — 仓位机械脆弱 + 崩盘性质诊断 · positioning fragility + crash-nature diagnostic
- 🫧 `dalio_bubble` — 泡沫幅度 + 货币/供给针 · bubble magnitude + monetary/issuance pins

并已把 20+ 位知名投资人/机构按框架分桶追踪（`analyst_watch.py` + `analyst_history.jsonl`）。本课题把这些零散工作**升级为一个持续、可回测、可预测的研究流程**。
We already track 20+ investors/institutions bucketed by framework. This project upgrades that into a **continuous, backtestable, forecast-producing pipeline**.

## 2. 目标 · Objectives

> 一句话：**持续收集各方对未来金融/证券/经济/货币走势的判断 → 提炼其判断依据 → 建成我们自己可用的模型 → 回测 + 预测。**
> In one line: **continuously collect market judgments → extract their basis → build our own usable models → backtest + forecast.**

1. **采集 Collect**：系统化收集分析师、基金经理、银行/机构（GS/JPM/MS/BofA/Apollo 等）对**金融、证券、经济、货币**走势的判断。
   Systematically collect judgments from analysts, fund managers, banks/institutions on finance, securities, economy, and currency trends.
2. **溯因 Extract basis**：找到每个判断背后的**框架与监测方法**（估值 / 仓位 / 债务货币 / 衰退 …），可证伪化。
   Identify the **framework and monitoring method** behind each judgment, made falsifiable.
3. **建模 Model**：把可计算的方法沉淀为**我们自己的模型**（扩展现有三体制 + 新增框架）。
   Distil computable methods into **our own models** (extend the three regimes + add frameworks).
4. **回测 Backtest**：用历史数据检验每个模型/信号的**命中率、领先时间、规避的回撤**。
   Test each model/signal on history for **hit-rate, lead time, drawdown avoided**.
5. **预测 Forecast**：产出**带检查点**的前瞻判断，事后打分，形成可追责的预测记录。
   Produce forward calls **with check-dates**, scored after the fact — an accountable forecast ledger.

## 3. 范围 · Scope

- **纳入 In**：公开发言可得、判断可证伪、方法可（近似）计算的观点；聚焦美股/AI、利率/信用、货币/黄金、宏观衰退。
  Public, falsifiable, (approximately) computable views; focus on US equities/AI, rates/credit, currency/gold, macro recession.
- **不纳入 Out**：不可证伪的口号、无法映射到数据的纯叙事、内幕/付费不可复核信息。
  Unfalsifiable slogans, pure narrative with no data mapping, non-verifiable paid/inside info.

## 4. 方法 · Methodology

1. **框架分桶 Bucketing**：A 估值/泡沫 · B 仓位/尾部 · C 债务/货币（+ 衰退闸门）。每位归主桶，多桶重叠=更强印证。
   Bucket A/B/C (+ recession). Primary bucket per person; multi-bucket = stronger corroboration.
2. **可证伪化 Falsifiability**：每个判断落成 `(标的 ticker, 可测条件 check, 检查点 check_date)` —— 复用 `analyst_watch` 现有机制。
   Turn each view into `(ticker, falsifiable check, check_date)`, reusing `analyst_watch`.
3. **方法计算化 Computability**：把监测方法映射到免费数据（yfinance/FRED）可算的代理指标。
   Map monitoring methods to proxies computable from free data (yfinance/FRED).
4. **回测 Backtesting**：为每个信号建独立回测（对齐日期、避免前视偏差、样本外检验）。
   Per-signal backtests (date-aligned, no look-ahead, out-of-sample).
5. **预测记账 Forecast ledger**：复用 `prediction_watch.py` / `prediction_snapshots.jsonl` 记录并打分。
   Reuse `prediction_watch.py` / `prediction_snapshots.jsonl` to log and score.

## 5. 实施计划（分阶段）· Implementation Plan (phased)

### Phase 0 — 已完成 · Done
- [x] 三体制模型（macro_gate / fragility_gate / dalio_bubble）
- [x] 20+ 分析师按框架分桶追踪；Dalio/Burry 策展记录 + 检查点
- [x] 分析师分框架报告（`research/analyst_frameworks_report.md`）
- [x] 网页模型总览 + 各家印证

### Phase 1 — 采集与结构化 · Collect & structure（进行中 In progress）
- [x] 建 `research/registry.jsonl`：一人一档,20 位,把「判断→框架→监测方法→**可算代理**→可证伪检查点→对应模型」结构化(双语)。
- [x] 结构化字段:`framework(A/B/C/bull)`、`primary_framework`、`stance`、`method`、`computable_proxy`、`action`、`maps_to_model`、`check{ticker,check,horizon}`、`tracked`。
- [x] 加载/查询器 `research/registry.py`（按框架/模型/立场过滤 + 汇总;`load()/by_framework()/by_model()`）。
- [x] 已覆盖机构研究:GS(Covello)、Apollo(Slok)、JPM(Dimon)、MS(Wilson)、GMO/红杉/Universa 等。
- [ ] 继续扩充 `analyst_watch` 至更多机构首席(BofA/花旗/大摩经济学家)并回填其 registry 档案。
- [ ] 把 registry 的 `check` 自动同步进 `analyst_history.jsonl` 的检查点机制。

### Phase 2 — 框架化建模 · Frameworks → models
- [ ] **A 估值表**：CAPE / 市值-GDP（巴菲特指标已在 dalio_bubble）/ AI 资本开支 ROI 子信号。
- [ ] **B 流动性错配**：Burry 成分股日成交额分布「薄名字」计数；内部结构广度；被动流反转。
- [ ] **C 债务/货币**：私人信贷压力、期限溢价、DXY/美债供需，补强货币针。

### Phase 3 — 回测 · Backtest
- [ ] 建**统一回测框架** `research/backtest.py`：输入信号序列 → 输出命中率/领先时间/规避回撤/Sharpe。
- [ ] 对每个模型跑样本内 + 样本外；记录并对比（含基准：买入持有 / 六因子闸门）。
- [ ] 校准阈值（如 dalio 分位锚点、fragility 触发线），避免过拟合（记录被丢弃的尝试）。

### Phase 4 — 预测与打分 · Forecast & score
- [ ] 每个模型产出**带检查点的前瞻判断**，写入 `prediction_snapshots.jsonl`。
- [ ] 检查点到期自动打分（对/错/部分），形成**分析师 & 模型双榜**命中率。
- [ ] 网页新增「预测记分卡」页（复用现有 prediction 视图）。

### Phase 5 — 集成 · Integrate
- [ ] **信念叠加 Conviction stacking**：多框架同时预警 → 提高综合风险读数。
- [ ] 综合仪表板：三体制 + 各家印证 + 命中率，一屏总览。

## 6. 交付物 · Deliverables

| # | 交付物 Deliverable | 位置 Location |
|---|---|---|
| D1 | 分析师分框架报告（滚动） | `research/analyst_frameworks_report.md` |
| D2 | 分析师/机构档案库 + 加载器 | `research/registry.jsonl` + `research/registry.py` ✅ Phase 1 |
| D3 | 新增框架模型 | 各 `*.py` + `modules/*/spec.md` |
| D4 | 统一回测框架 + 报告 | `research/backtest.py` + `research/backtests/` |
| D5 | 预测记分卡 | `prediction_snapshots.jsonl` + 网页 |

## 7. 成功指标 · Success Metrics

- **覆盖 Coverage**：≥ 30 位分析师/机构、3+ 框架、每位有可证伪检查点。
- **可回测 Backtestable**：每个模型有样本外回测、命中率与领先时间量化。
- **可追责 Accountable**：预测有检查点、事后自动打分、命中率公开。
- **有增量价值 Edge**：至少一个模型在回测中相对买入持有**降低回撤**或**提供领先预警**。

## 8. 数据源 · Data Sources

yfinance（价格/波动/ETF）· FRED（利率/信用/宏观/GDP/Wilshire）· Google News RSS（分析师表态）· Claude API（合成/结构化）。
> ⚠️ 沙箱网络封禁 Yahoo/FRED，模型端到端只在 GitHub Actions 跑；本地只做逻辑单测（合成数据）。
> Sandbox blocks Yahoo/FRED; end-to-end runs only in GitHub Actions; locally we run logic unit-tests on synthetic data.

## 9. 风险与注意 · Risks & Caveats

- **重机制、轻择时**：多位空头过往择时屡错（Hussman/Grantham 2022/Kolanovic）——用方法建模，不据喊话择时。
  Mechanism over timing — perma-bear calls have missed; borrow methods, not calls.
- **过拟合 Overfitting**：回测须样本外 + 记录被弃尝试，阈值不迁就历史。
- **前视偏差 Look-ahead**：数据对齐用**已发布值**、滞后处理（FRED 修订）。
- **数据代理 Proxy risk**：部分方法（保证金杠杆、发行量）只有代理，须在文档标注。
- **不构成投资建议 Not advice**：所有输出为研究，非交易指令。

---

*本课题为滚动研究，按 Phase 推进；每完成一阶段更新本文件与 `CHANGELOG.md`。*
*A rolling research project advanced by phase; update this file and `CHANGELOG.md` at each milestone.*
