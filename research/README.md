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
- [x] 把 registry 的 `check` **物化为带绝对到期日的台账**:`research/sync_checks.py` → `research/registry_checks.jsonl`(**确切发言日 `stated_date`** + horizon,保留发言日的「日」,`date_precision` 标 day/month,确定性,不污染网页分析师板);`registry.checks_due()` 统一合并「analyst_history + registry 台账」两源,按 (analyst,date,ticker,**check 文本**) 去重(保留同人同日的不同/相反预测)。
- [x] 扩充机构首席:新增 **Michael Hartnett(BofA · Bull & Bear Indicator)** 入 registry + analyst_watch(21 人)。
- [ ] 继续扩充更多机构首席(花旗/大摩/德银经济学家)并回填 registry。

### Phase 2 — 框架化建模 · Frameworks → models（进行中 In progress）
- [x] **市场广度/集中度信号 `market_breadth.py`**（首个 Phase 2 模型）：`RSP÷SPY`、`IWM÷SPY`、板块 200 日线广度 → `narrow_score`;把 **Hussman 内部结构 / Slok·Kolanovic 集中度 / Burry 拥挤** 可计算化(只用流动 ETF)。接入两 workflow + 网页面板(双语)。见 `modules/market_breadth/`。
- [ ] **A 估值表**：CAPE / 市值-GDP（巴菲特指标已在 dalio_bubble）/ AI 资本开支 ROI 子信号。
- [ ] **B 流动性错配**：Burry 成分股日成交额分布「薄名字」计数（需全市场成分表）；被动流反转。
- [ ] **C 债务/货币**：私人信贷压力、期限溢价、DXY/美债供需，补强货币针。

### Phase 3 — 回测 · Backtest（进行中 In progress）
- [x] 建**统一回测框架** `research/backtest.py`:`perf_stats`(CAGR/vol/Sharpe/MaxDD)、`backtest`(仓位型择时 vs 买入持有 + 规避回撤/敞口/换手,信号按 lag 滞后**无前视**)、`event_eval`(事件型:命中率/判别力/规避回撤/**领先时间**)。合成数据单测锁定指标正确性 + 无前视。
- [x] **历史重算 + 回测** `research/backtest_models.py`:把 macro_gate / fragility / dalio_bubble / market_breadth 四模型的**历史信号序列**(point-in-time,**无前视**:分位一律用扩张/滚动窗口)喂入 `backtest.py`,产出各模型真实的**命中率 / 判别力 / 规避回撤 / 领先时间 / vs 买入持有**,写 `research/backtest_results.json` + `docs/data.json['backtest_results']`。阈值从各模型模块 import(不复制,防漂移);合成数据 self-test 断言无前视(前缀不变性)。由 `.github/workflows/backtest_models.yml`(月度 + 手动)在 Actions 用真实 FRED/yfinance 跑。诚实边界:dalio 略去表6(人工档)、breadth 受 ETF 历史限制(RSP≈2003)、fragility 期限结构受 ^VIX3M≈2007 限制。
- [x] **危机前30天轨迹** `research/crisis_windows.py`:过去 ~30 年 10 次危机(2000/2001/2007/2008/2010/2011/2015/2018/2020/2022),逐日记录四模型的**数值 / 连续天数 / 闸门提前多少天报警** + onset 后 63 日峰谷回撤(危机严重度)→ `research/crisis_windows.json` + 网页「危机前30天」面板(火花线)。同一批数据、同一信号构造器,只按日期切片(无前视)。
- [x] **校准结论(基于真实回测,非过拟合)**:首轮结果——**macro_gate 是唯一真·风控**(规避回撤 **+43pp**、超额 CAGR **+0.84%**、Sharpe 0.80>0.66),保留阈值;**达利欧读数 = 量级表非择时器**(判别力**为正** = 示警后反而更涨 = 融涨,恰印证其框架),故**不据其单独择时**——并新增「读数≥80 **且**货币针 ON」的**完整判据**回测,检验「针」是否补上择时价值;**fragility / breadth 判别力≈0**,确认为「情境 / 印证」信号,**刻意不为追回测收益去调其触发线**(那是过拟合)。诚实结论:**大多数阈值不动**,只把 dalio 明确降格为「量级参考」。被丢弃的尝试:把 fragility/breadth 当退出信号——数据显示当卖点均为负超额,舍弃。

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
| D1b | **观点→模型 建模论证**（每人:观点/时间/建模/为什么忠实/局限,双语） | `research/view_to_model.md` |
| D2 | 分析师/机构档案库 + 加载器 | `research/registry.jsonl`(21人)+ `research/registry.py` ✅ Phase 1 |
| D2b | 检查点台账(预测记账种子) | `research/registry_checks.jsonl` + `research/sync_checks.py` ✅ Phase 1 |
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

## 10. 当前状态快照与已知问题 · Status Snapshot & Known Issues（2026-08-08）

### ✅ 已完成 Done
- **Phase 0**：三体制模型 `macro_gate`(衰退闸门) · `fragility_gate`(脆弱+崩盘诊断) · `dalio_bubble`(泡沫 6 表+双针+领先对) —— 全部上线。
- **Phase 1**：`registry.jsonl`(21 人档案) + `registry.py`(加载/`checks_due`) + `registry_checks.jsonl` + `sync_checks.py`(检查点台账) + 分框架报告 + 机构扩充(BofA)。
- **Phase 2(开工)**：`market_breadth`(广度/集中度信号 = Hussman/Slok/Kolanovic/Burry 方法可计算化)。
- 网页：三体制总览+各家印证说明页、各模型双语面板。备忘录 `notes/1987型崩盘_vs_六因子闸门.md`(10 节)。

### ⏳ 未完成 Pending
- **Phase 2 剩余**：A 估值表(CAPE/AI-ROI) · C 债务信号(私人信贷/期限溢价/DXY) · Burry「薄名字」流动性硬 tell(需全市场成分表)。
- **Phase 3 回测 `backtest.py`（未开始）** · **Phase 4 预测记分卡（未开始）** · **Phase 5 信念叠加集成（未开始）**。

### ⚠️ 已知问题 Known Issues
1. ~~**新模型线上尚无数据**~~ **✅ 已解决(2026-08-08)**:原因不是失败,而是 `dalio_bubble`/`market_breadth` 合并到 main **晚于**当日最后一次定时运行(`macro_gate.yml` 仅周一~五 14–21 UTC)。手动 `workflow_dispatch` 触发后,main 已产出 `dalio_bubble`(72% 偏高·双针 ON)与 `market_breadth`(narrow 0/3·广度健康)。FRED/yfinance 在 Actions 正常 —— 之后定时运行自动保持更新。
2. **未回测 = 阈值未验证**（Phase 3 引擎已建 `backtest.py`,下一步用它把各模型跑历史）:所有模型的分档/触发线(dalio 60/80、fragility 各阈值、breadth 63日/50%/7板块、K=2/PERSIST=10)**均未经历史验证**,命中率/领先时间/规避回撤全未知 —— 这是最大方法论空缺(待 Phase 3)。
3. **模型口径为近似/代理**:dalio 表5杠杆=低波动代理(非 FINRA 保证金)、表6=人工档、等权=多指标百分位的近似、供给针=IPO ETF 代理;breadth=ETF 比率(非真·全市场广度)。均已在各 spec 标注。
4. **检查点多为月精度**:registry 多数 `date_precision=month`;相对表现类 check(如"GLD 跑赢 SPY")需起始价基准,Phase 4 打分器需处理。
5. **收录偏空**:名单多为长期看空者、过往择时屡错 —— 集成时须防单边看空(重机制轻择时)。
6. **流程**:每日 Actions bot 推进 `main`(data.json/analyst_history)会造成 PR 合并冲突(已多次手动解);沙箱封 Yahoo/FRED,数据类模型只能 Actions 端到端跑,本地仅合成单测。

---

*本课题为滚动研究，按 Phase 推进；每完成一阶段更新本文件与 `CHANGELOG.md`。*
*A rolling research project advanced by phase; update this file and `CHANGELOG.md` at each milestone.*
