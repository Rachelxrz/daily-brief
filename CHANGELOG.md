# 更新日志 (CHANGELOG)

系统功能改动记录。watchlist 每日自动增删/暂停的**数据审计**见 `docs/watchlist_changelog.json`（网页「均线信号」页可展开查看）。


## 2026-08-09

### Phase 3 续②:历史回测跑出真实数字 + 危机前30天轨迹 + 记分卡网页(PR #10 #11)
- **`research/backtest_models.py`**:把四模型历史信号(分位扩张/滚动窗口,信号再经 `lag=1`,**月度/季度宏观按发布滞后前移=无前视**,修订值仍最新=非 ALFRED vintage,待办)喂入 `backtest.py`。真实结果(发布滞后口径,1985→今):
  - **macro_gate = 唯一真·风控**:判别力 **−2.53%**、规避回撤 **+43pp**(策略 MaxDD −40% vs 买入持有 −83%)、超额 CAGR **+0.09%(≈打平)**、Sharpe 0.77>0.66。
  - **dalio 泡沫读数 = 量级表非择时器**:判别力**为正**(≥60 +1.09%、≥80 +2.95%、**≥80且货币针 +1.49%**)——示警后反而更涨=**融涨**,印证达利欧框架;**新增「≥80且货币针」完整判据回测:针未能补上择时价值**,货币针操作化列为待细化。
  - **fragility / breadth 判别力≈0**:确认为「情境/印证」信号,当卖点均负超额;**刻意不为追回测收益调触发线**(过拟合)。
- **`research/crisis_windows.py`**:回放过去 ~30 年 10 次危机,逐日记录四模型数值/连续/闸门提前多少天报警 + onset 后 63 日峰谷回撤。**关键发现**:
  - **macro_gate 精准预警唯二的「真·衰退危机」**:2001(**闸门提前 39 日**)、2008 雷曼(**提前 126 日**);对机械/快速崩盘(2010/2020新冠/2022)保持沉默——设计使然(衰退探测器,非闪崩)。
  - **fragility 抓住 macro 漏掉的自满型抛售**:2018 Q4(**3/5**)、2015(2/5)、2020(onset 2/5,**窗内峰 5/5**),低波动/拥挤驱动;两模型互补。
  - **触发不可测但脆弱性可见**:2020 新冠(−34%)病毒火星谁都测不到、衰退闸门也没亮,但 **fragility 崩前升至 5/5**(非「四表皆温和」);**达利欧扩张分位读数在最早泡沫失真**(2000 见顶仅 42,短历史+IPO表2013才有),2013 后读数(2015=76、2018=73)才可信。
- **网页(`docs/index.html`)**:新增两折叠面板 `renderBacktestScorecard`(回测记分卡)+ `renderCrisisWindows`(危机前30天,**火花线 ▁▂▃▄▅▆▇█** 展示逐日走高 + 闸门提前天数),双语 null-safe,并入结构监控页。
- **月度 workflow `backtest_models.yml`**:同时跑两脚本、`--self-test` 前置守门;commit 仅在新结果非空时覆盖(抓数失败保留上一份有效面板)。
- **Codex 评审(PR#10 2 条 / #11 3 条)全部核实修正**:泡沫档位 ≥60/≥80(取整边界)、backtest 标 PR#7 已合并;**缺分量不当健康**(fragility/breadth 增 n_valid 掩码,部分缺→按真实分母 partial、全缺→unavailable)、闸门**已清除的预警**回看窗捕捉、空结果**不覆盖**既有面板;外加数据源健壮性 `_align()`(失败源降级为缺输入而非崩溃)。
- **`research/view_to_model.md`**:新增「**附录二 · 实证**」章,把回测记分卡 + 危机前30天发现 + 五个诚实结论写入(双语);校准结论写入 `research/README.md` Phase 3。
- **Codex 评审 PR#12(2 条)修正**:**P1 无前视口径**——`backtest_models.fetch_all` 新增 `_pub_lag`,把月度/季度宏观(UNRATE/CFNAI/FEDFUNDS +1月、GDP +4月、Z.1市值 +5月)按**发布滞后前移**,不再用尚未发布的读数;残留 caveat 诚实标注「仍取最新修订值=非 ALFRED vintage,头条数字据此打折」,vintage 对齐列为待办。**P2 COVID 结论**——原「四表皆温和」有误(与数据及结论2矛盾):`fragility` 崩前升至 **5/5**(−30日 4/5),改为「触发不可测但脆弱性可见」,病毒火星测不到 ≠ 干柴不满。

### 观点→模型 建模论证底稿 `research/view_to_model.md`(PR #8 #9)
- **逐位分析师(21 人)论证「凭什么这个信号代表他的观点」**:①观点 ②时间 ③建模 ④为什么忠实(机制对应/方向一致/可证伪三原则)⑤局限;单独成篇(PR #8)。
- **附录:各模型「怎么算/跟什么比/哪个方向危险」**(PR #9),与达利欧同粒度拆到可复核算法层。
- **诚实更正(据 Codex)**:达利欧 6 表非「1900以来」而是各表自有窗口分位(市值/GDP≈1945、纳指≈1985、IPO 2013、VIX 5y…),锚点为软性参照非重算;Burry 拥挤篮标为项目自定义 AI/半导体代理(非其真实空头);fragility 当前单向、非双向;泡沫档位 ≥60/≥80。


## 2026-08-08

### 解决「线上无数据」+ Phase 3 回测引擎 `research/backtest.py`
- **已知问题#1 解决**:`dalio_bubble`/`market_breadth` 合并晚于当日最后一次定时运行,手动 `workflow_dispatch` 触发 macro_gate.yml 后 main 已产出真实读数(达利欧泡沫 **72% 偏高·货币针+供给针 ON**;广度 **narrow 0/3·健康**;衰退闸门 0/6)。FRED/yfinance 在 Actions 正常。
- **Phase 3 统一回测框架** `research/backtest.py`:`perf_stats`(CAGR/vol/Sharpe/MaxDD)、`backtest`(仓位型择时 vs 买入持有,信号按 lag 滞后**无前视**,输出规避回撤/敞口/换手)、`event_eval`(事件型:**命中率/判别力/规避回撤/领先时间**)。合成数据单测锁定指标 + 无前视(6 断言全过)。下一步:在 Actions 用历史数据重算各模型读数喂入回测。

### 研究项目状态快照 + 已知问题清单(见 research/README §10)
- 汇总 Phase 0/1/2 已完成部分、Phase 2 剩余与 Phase 3/4/5 未开始项。
- **已知问题**:①新模型 dalio_bubble/market_breadth 线上尚无数据(需确认下次 Actions 产出);②未回测→阈值未验证(最大方法论空缺);③模型口径多为代理/近似(已在各 spec 标注);④检查点多月精度;⑤名单偏空需防单边;⑥Actions bot 推进 main 造成合并冲突、沙箱封 Yahoo/FRED。

### 研究课题 Phase 2(开工):市场广度/集中度信号 `market_breadth.py`
- 把多位分析师**共用**的「内部结构/集中度/拥挤」方法**可计算化**(只用流动 ETF):**Hussman 内部结构一致性 · Slok/Kolanovic 集中度 · Burry 拥挤**。
- 三信号:`RSP÷SPY` 近3月(等权/市值)、`IWM÷SPY` 近3月(小盘/大盘)、11 板块站上 200 日线的广度;`narrow_score` 0–3(只在有数据的信号里计分)→ 红/黄/绿/muted。
- 与三体制正交,印证 `fragility_gate`(B 仓位)与 `dalio_bubble` 内部(A 估值)。写入 `data.json` 的 `market_breadth`;网页 `renderMarketBreadth()`(达利欧面板下方,中英双语);接入 `daily_brief.yml`+`macro_gate.yml`(排 dalio 之后)。合成测试狭窄/健康/中性/空数据全过。规格见 `modules/market_breadth/`。

### 研究课题 Phase 1(续):检查点台账 + 统一到期查询 + BofA 入库
- **`research/sync_checks.py` → `research/registry_checks.jsonl`**:把 registry 每条 `check` 物化为**带绝对到期日**的检查点(`latest`+`horizon` 换算,区间取上界,long/open 默认 24m),确定性可复现;作为 Phase 4 预测记账台账,**不污染网页分析师板**。
- **`registry.checks_due()` 升级**:统一合并「`analyst_history.jsonl` 策展/自动记录 + `registry_checks.jsonl` 台账」两源,按 (analyst, check_date, ticker) 去重;`--due` CLI。
- **扩充机构首席**:新增 **Michael Hartnett(BofA · Bull & Bear Indicator)** 入 `registry.jsonl`(21 人)+ `analyst_watch` 追踪 + 网页徽章(逆向·空头);映射 `fragility_gate`。

### 研究课题 Phase 1:分析师档案库 `research/registry.jsonl` + 加载器
- **`research/registry.jsonl`**:一人一档 20 位(GMO/Hussman/Chanos/Marks/Slok/Covello/Cahn/Buffett · Burry/Spitznagel/Taleb/Einhorn · Dalio/Dimon/Druckenmiller/Edwards/PTJ · Tom Lee/Ives/Wilson),把「判断→框架→监测方法→**可算代理**→可证伪检查点→对应模型」结构化(双语)。字段:framework/primary_framework/stance/method/computable_proxy/action/maps_to_model/check{ticker,check,horizon}/tracked。
- **`research/registry.py`**:加载/查询器(按 framework/model/stance 过滤 + 汇总;`load()/by_framework()/by_model()`)。
- 按主框架:A 估值 8 · B 仓位 4 · C 债务 5 · 看多 3;已自动追踪 16/20;映射 dalio_bubble 11 / fragility_gate 6 / macro_gate 1 / 看多制衡 2。
- `research/README.md` Phase 1 勾选;交付物 D2 完成。

## 2026-08-07

### 修复：PR #2 code review（dalio_bubble）+ fragility 面板双语化
- **P1** 估值表改用市值序列 `NCBEILQ027S`(非金融企业股权)/GDP,替换价格指数 `WILL5000INDFC`(量纲不匹配)。
- **P1** 货币针数据缺失时保留「未知」态(`monetary_known`),不再把未评估误报为 off→melt-up;判读转「暂缓结论」。
- **P2** 判读措辞据实际触发的针生成(货币针/供给针),供给针单独触发不再误写「货币在收紧」。
- **P2** `dalio_bubble` + `fragility_gate` 两个面板**全字段双语化**(band/verdict/note/表名/说明/tell/性质/恢复提示均输出 `_en`),网页按语言选用;EN 无中文泄漏已验证。

### 立项：专项研究课题「市场判断 → 可用模型」+ 分析师分框架报告
- **新目录 `research/`**：
  - `research/README.md` — 课题章程（双语）：目标（采集各方对金融/证券/经济/货币的判断 → 溯因 → 建模 → 回测 → 预测）+ 5 阶段实施计划（Phase 0 已完成三体制；Phase 1 采集结构化；Phase 2 框架建模；Phase 3 统一回测 `backtest.py`；Phase 4 预测记分卡；Phase 5 信念叠加集成）+ 交付物/成功指标/数据源/风险。
  - `research/analyst_frameworks_report.md` — 分析师分框架说明报告（双语）：按 A 估值/B 仓位/C 债务分桶，逐位给「主要观点 / 监测方法 / 值得借鉴」（Grantham/Hussman/Chanos/Marks/Slok/Covello/Cahn/Buffett/Burry/Spitznagel/Taleb/Einhorn/Dalio/Dimon/Druckenmiller/Edwards/PTJ + 看多制衡 Tom Lee/Ives/Wilson），末附「综合借鉴→我们的模型」映射表。
- 复用现有基建：`analyst_watch`（检查点机制）、`prediction_watch.py`/`prediction_snapshots.jsonl`（预测记账）。
- CLAUDE.md「开发中模块」新增本课题。

### 深化：三体制模型调研丰富 + 网页模型说明与各家印证
- **调研**（Dalio/Burry 方法论 + 其他基金经理）落地：
  - `dalio_bubble.py`：分档校准到达利欧百分位锚点（1929/2000≈100、2021≈77、2024≈52）；新增**供给针**（IPO 发行热 ≥85 分位,达利欧 2026 新增,与货币针并列）；新增**领先对早期预警**（新买家+情绪同高,先于综合读数亮）；note 标注等权均值为其多指标百分位的近似。合成测试加「供给针单独触发」「发行冷→melt-up」场景。
  - `fragility_gate` v1.1 roadmap（Burry 2019 流动性错配硬 tell/被动流反转/内部人抛售/AI 折旧盈利质量/13F 权利金口径）。
- **分析师板块扩容**：`analyst_watch.py` 追踪名单增 11 位（Grantham/Hussman/Chanos/Marks/Spitznagel/Einhorn/Druckenmiller/PTJ/Dimon/Edwards/Tom Lee）；网页按框架分桶徽章（宏观·债务/估值·泡沫/逆向·空头）。
- **网页「结构监控」新增可折叠「🧭 三体制监测·模型总览与使用范围」**：三模型各测什么/何时看/触发含义/它不管 + 如何一起用 + **各家印证**（按框架分桶列印证声部 + 看多制衡 + 重机制轻择时提醒）。中英双语。
- 备忘录 `notes/1987型崩盘_vs_六因子闸门.md` 增第 9（各家印证分桶）、第 10 节（达利欧 6 表确切机制 + Burry 2019 流动性错配先声 + 择时命中率警示 + 落地映射）。

### 新增：达利欧泡沫预测模型 `dalio_bubble.py`（泡沫「多大」+「何时被戳破」）
- 操作化 Ray Dalio 两条框架：**6 表泡沫指标**（估值=巴菲特指标 Wilshire/GDP、涨势=纳指12月回报分位、新买家=IPO ETF 6月回报分位、情绪=1−VIX分位、杠杆=1−实现波动分位[代理]、远期建设=`dalio_config.json` 人工档）取均值 → 泡沫读数 %（≥80 晚期泡沫/≥60 偏高/<60 中性）。
- **货币收紧「扳机」**：FEDFUNDS 6月变化 + DFII10 3月变化 ≥+0.25% → pin.on。核心论断「泡沫在货币收紧前不会真正破裂」。
- 判读：泡沫高+无pin→🫧melt-up(分散+黄金,勿裸空)；泡沫高+有pin→📌破裂风险；泡沫低→🟢。
- 写入 `data.json` 的 `dalio_bubble`，网页 `renderDalioBubble()`（脆弱性侧栏下方，中英双语，带 60/80 门槛线）；接入 `daily_brief.yml`+`macro_gate.yml`（排 fragility_gate 之后）。合成数据测三体制判读+pin+纯函数分位均通过。规格见 `modules/dalio_bubble/`。

### 新增：脆弱性/拥挤度侧栏 + 崩盘性质诊断 `fragility_gate.py`（PR #1，已合并）
- 与六因子衰退闸门**正交、不混票、不发买卖信号**：脆弱性评分 0–5（VIX低位/期限结构contango/实现波动低分位/QQQ拉伸/Burry篮子RSI拥挤）+ 崩盘当天读跨资产联动（VIX期限结构/TLT/HYG/GLD/防御vs科技/闸门票数）判「机械1987型 vs 衰退型」。
- 网页 `renderFragilityGate()`，接入两个 workflow（排 macro_gate 之后读当日票数）。新增 `.gitignore`。Code review（Codex）三条修复：RSI全涨=100不毒化中位、闸门票数只读当日、补模块 spec/status。规格见 `modules/fragility_gate/`。

### 新增：分析师板块纳入 Ray Dalio + Michael Burry（含监测时间）
- `analyst_watch.py` 追踪名单增补 Dalio(Bridgewater)、Burry(Scion)；网页徽章：Dalio=宏观、Burry=逆向·空头。
- 策展记录写入 `analyst_history.jsonl`：**Burry**（发言 2026-08-04，1987型闪崩+做空半导体/AI，测试 SMH 低于发言日收盘，检查点 **2026-11-04**）；**Dalio**（泡沫高但先融涨、2026–2028危险期、5–15%黄金，测试 GLD 跑赢 SPY，检查点 **2027-02-04**）。

### 新增：分析备忘录 `notes/1987型崩盘_vs_六因子闸门.md`
- 八节：六因子 vs Burry 逻辑、闸门为何抓不到1987型、1987崩盘程度与恢复、崩盘性质×恢复时间对照、组合敞口、**Burry vs 达利欧框架对比**（债务周期/主权宏观 vs 仓位反身性）、**崩盘当天性质判读法则**、模块落地。

### 新增：均线信号按分档差异化 + 每只标注分档
- `ma_cross_signal` 新增 `archetype_signal()`：按每只股票分档给出信号(payload 增 `signal_arch`/`rule`)。
  - 🔵稳定核心 = 买入持有(MA50>MA150且价格>150MA买,回调≤MA50加仓,**不出卖出信号**,止损交给周线150MA/QQQ闸门)
  - 🟢成长核心 = 策略C 但清仓用 **MA50<MA200**(新增 MA200)
  - 🟡趋势成长/🔴题材 = 策略C 清仓 MA50<MA150(现有)
- 均线信号页对齐：主表"当前信号"改用分档信号 + 规则小字；每只旁挂分档徽章;计数新增"持有";移除已过时的"策略C分歧"栏与近7天C建议;顶/底说明改写为三档规则。
- 效果:稳定核心(如ADI/CAT)不再被趋势止损绞杀,显示买入/持有。

### 新增：watchlist 系统规则写入 watchlist.json 的 `spec` 节
- 把完整定义(构成/进入/分档/移出/回归/复检频率)固化进 `docs/watchlist.json` 顶层 `spec` 键，规则随数据走。
- 各 load-modify-save 流程(classifier/gate/screener)均保留该键，已验证。改规则请同步更新 `spec`。

### 新增：用QQQ替代低效稳定核心（3年跑不过QQQ→移入 Secondary）
- `stock_classifier.py` 计算每股近3年价格年化(r3y)与 QQQ 对比(beats_qqq)。
- **稳定核心 若近3年年化 < QQQ → 移入 Secondary Watchlist**（reason=「3年回报低于QQQ」），停止买卖信号；回到QQQ之上再放回。由半年分类任务复查，不走周线MA回归。
- `watchlist_gate.py` 的每周回归复查**跳过**「QQQ」类条目（避免用MA规则把它们错误放回）。
- 本次移入 Secondary 7 只：CSX/HON/JNJ/LMT/LNG/NEE/TXN；留主 watchlist 的稳定核心仅 ADI/CAT/CSCO/MPC（3年跑赢QQQ）。
- Secondary Watchlist 现有两类移出原因：①周线跌破150MA ②3年回报低于QQQ；页面说明已更新。

### 变更：Secondary 移出闸门确认为 周线150MA（引擎/文案统一）

### 新增：个股基本面分档（成长性核心/稳定核心/趋势成长/题材投机）
- 新增 `stock_classifier.py`：按**纯基本面**给每只股票定档，写入 `docs/watchlist.json` 的 `classification`（每票含 archetype/profit/市值/上市年限 + 特性 vol/beta/maxdd）。
- **定档规则**（回撤/波动/Beta 不参与定档，只作特性给交易层）：
  - 题材投机 = 当前亏损 或 上市<3年；
  - 核心 = 市值≥$50B 且 上市≥8年 且 **近3年逐年净利润为正**（成长核心=最新>3年前；稳定核心=年年正但未超3年前 **且 年化波动≤45%**）；
  - 趋势成长 = 有盈利但够不到核心；**利润不增长但波动>45%(如 TSLA/CIEN)也归此档**（波动型非成长，需趋势管理而非买入持有）。
- 设计取舍记录：先用「波动/Beta」定档 → 发现把 LLY/NVDA 等误判 → 改纯基本面；「近4年」放宽为「近3年」；曾尝试「3年降幅>15%出局」，因一次性收益(JNJ 2023 Kenvue)与周期高点基数误伤优质股而**弃用**，最终**利润为正为唯一硬闸门**，"利润下滑"仅作标签。
- **每半年复核一次**：`.github/workflows/stock_classify.yml`（1/1 与 7/1），档位变化写入 `watchlist_changelog.json`。
- 均线信号页每只股票挂「分档徽章」；`ma_cross_signal` 从 classification 读取 archetype 带入 payload。

### 变更：Secondary 移出闸门 200周MA → 150周MA
- 「移入 Secondary Watchlist」的闸门由周线200MA改为**周线150MA**（与强势股进场的周线120MA更接近，避免长期倒挂股「过了120进场线却低于200出场线」）。
- 一次性迁移：已在 Secondary 里但已站上周线150MA的标的迁回主 watchlist（如 ALB：周收125.7 > 150wMA 111.3）。CI/COIN/INTU/ISRG 仍低于各自150MA，留在 Secondary。
- 回归条件不变：周线 > 150MA 且 > 20MA 且 近2季净利润上升。

### 新增：Secondary Watchlist（二级观察名单）+ 移出/回归分频
- 把「跌破周线200MA被移出」的标的正式命名为 **Secondary Watchlist**（页面标题、说明更新）。
- **移出**（主→二级）：仍每日检测（`daily_brief` 里 `watchlist_gate.py`）。
- **回归复查**（二级→主）：改为**每周一次**——新增 `.github/workflows/watchlist_promote.yml`（每周六 `watchlist_gate.py --promote`）。
- `watchlist_gate.py` 加 `--promote` 开关：默认仅移出；`--promote` 才复查回归。

### 变更：强势股筛选 新增「周线价格 > 120周MA」基础条件
- 潜在/现有两档的基础条件都加入 **周线收盘 > 120周MA**（价格站上长期周线均线；周线不足120根淘汰）。
- 副作用（好事）：上升趋势中 120周MA 高于 200周MA，故入选股天然在周线200MA之上，不会再被 watchlist 闸门暂停——消除了「刚筛出又被暂停」的矛盾。

### 新增：watchlist 周线200MA 暂停/恢复闸门
- 新增 `watchlist_gate.py`：每交易日在均线信号前运行。
  - **暂停**：任一标的周线收盘 < 200周MA → 移出活跃跟踪，不再给买卖信号；记住来源以便恢复。
  - **恢复**：周线收盘 > 150周MA 且 > 20周MA 且 近2季度净利润>0并上升，才恢复。ETF/无财报标的仅看价格。
  - `core_holdings`（GLD/QQQ/TLT/WTI 战略锚仓）**豁免**本闸门。
- `watchlist_manager.py`：新增 `suspended` 层、来源标记（screener/manual）、`apply_suspension()`、审计日志 `log_watchlist_changes()`。
- `ma_cross_signal.py`：`load_tickers()` 排除已暂停标的；payload 增加 `suspended` / `wl_changes` / 每票 `source`。
- 前端均线信号页：新增「已暂停」区、「watchlist 变更日志」折叠区、来源徽章（筛选/自选）。

### 变更：强势股写入 watchlist 的清理规则
- 由「30天未再入选移除」改为「**周线跌破200MA才移除**」；入选即常驻。
- 强势股筛选写入的标的与我自己添加的，用来源标记区分。

## 2026-08-06

### 变更：强势股筛选（选股口径 + 自动写入 watchlist）
- 选股排序由「2个月涨幅」改为「**6个月波动率从小到大**」取前3（挑最稳的）。
- 入选个股（现有+潜在）自动写入 watchlist，并在均线信号页跟踪。

### 变更：强势股筛选（两档 + 移除自选股分析）
- 删除「自选股技术分析」页（与均线信号页重复）。
- 板块强势股拆两档：**潜在强势股**（市值>2亿 + 近3季净利润增/平）、**现有强势股**（潜在 + 20MA>50MA>150MA 多头排列）。
- 条件3由股价改为**净利润**：最近3季净利润增加或持平（环比降幅≤2%视为持平）。

### 新增：市场结构页「板块强弱·资金流向」面板
- 新增 `sector_board.py`：11大GICS板块+SMH/GLD/TLT 的今日/3月/YTD 表现 + 相对大盘RS推算资金流入流出，置于六因子闸门下方。

### 变更：均线信号页 策略C 措辞
- 近7天信号的策略C建议改为「红灯 N<阈值，维持某日建议」的语境化措辞。
