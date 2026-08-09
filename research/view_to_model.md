# 从分析师观点到可用模型：建模论证 · From Analyst Views to Models: The Mapping, Justified

> 双语 / Bilingual · 2026-08-08 · 归属课题 `research/README.md` · 数据底稿 `research/registry.jsonl`
>
> **本文回答一个关键问题**：我们把某位分析师的判断，变成了系统里的一个可计算信号——**凭什么说这个信号「代表」了他的观点?**
> **This document answers one question**: when we turn an analyst's judgment into a computable signal in our system, **on what basis do we claim that signal "represents" their view?**
>
> 每位分析师给出五段：**① 观点 View · ② 观点时间 Date · ③ 我们的建模 Our model(具体信号) · ④ 为什么忠实 Why it's faithful(论证) · ⑤ 局限/偏差 Where it diverges**。
> ④ 是本文的核心——不做这一步,「框架→模型」只是贴标签。
>
> **忠实性三原则 Faithfulness criteria**(判断「模型是否代表观点」的标准):
> - **(a) 机制对应 Mechanism match**:模型度量的,是分析师论证里那个**因果机制**,不是表面相关物。
> - **(b) 方向一致 Directional match**:分析师说「更危险」时,模型读数朝「更危险」方向动。
> - **(c) 可证伪 Falsifiable**:模型输出能被数据证伪,且与分析师**自己会看的证据**同源。
> - 任何一条不满足,就在 ⑤ 明确标注为「代理/近似」,不冒充忠实。

---

## 桶 A · 估值 / 泡沫 · Valuation / Bubble → 🫧 `dalio_bubble` 泡沫读数

### Ray Dalio — Bridgewater
- **① 观点**：美股(尤其 AI)处于大债务周期末期的泡沫;泡沫**在货币收紧被戳破前不会真正破裂**;先融涨后崩。建议 10–15% 黄金。
  *US (esp. AI) is a bubble late in the big debt cycle; it won't truly pop until pricked by monetary tightening; melt-up then bust.*
- **② 时间**：2026-08(《Diary of a CEO》)+ 2025-10(CNBC)。
- **③ 我们的建模**：`dalio_bubble` **操作化他的 6 表方法**——每表取「当前值在**它自己那段可得历史**中的百分位」(**窗口各异**:市值/GDP≈1945起、纳指≈1985起、IPO ETF 2013起、VIX 仅 5 年、实现波动≈3 年、远期建设为人工档**无百分位**),其中情绪/杠杆取 `1−百分位`(值越低越危险);**可用表的百分位取均值 ×100 = 泡沫读数**(0–100)。读数再与固定档位比:**超过 60=偏高、超过 80=晚期泡沫——越超过越泡沫**。**双针**(货币针 FEDFUNDS/实际利率 + 供给针 IPO 发行)= 他的「戳破」条件;领先对(新买家+情绪)。
- **④ 为什么忠实**：这是**本项目里忠实度最高的一条**——不是把别人的话套框架,而是**操作化他公开的 6 表方法论**(见 `notes/…§10`、其 2021《Are We in a Stock Market Bubble?》)。机制对应(a):双针直接编码他「泡沫需货币收紧才破」的因果论断;方向一致(b):6 表百分位越高、双针越响 = 他口径的「越危险」;可证伪(c):读数可被价格证伪(检查点=SPY 跌破发言日收盘)。**校准诚实说明**:1929/2000≈100、2021≈77、2024≈52 是我们贴的**软性参照档位**,**不是**把 6 表真的重算回那些年份——底层数据根本不够长(VIX 仅 5 年、IPO ETF 仅 2013 起),故综合读数**与那些历史锚点不严格可比**,只作分档标尺,不作精确校准。
- **⑤ 局限**：各表历史窗口长短不一(见 ③),等权求均值是对其多指标百分位的**近似**、且**未做统一到同一长历史的重算**;表5杠杆用「低波动」代理(非 FINRA 保证金)、表6人工档、供给针用 IPO ETF 代理。已在 spec 标注。

### Jeremy Grantham — GMO
- **① 观点**：史上最大泡沫,AI 类比 1840s 铁路;靠**长周期估值均值回归**,下行约 −70%。 *Largest-ever bubble; mean reversion; ~−70%.*
- **② 时间**：2026-01(GMO Viewpoints / Bloomberg)。
- **③ 我们的建模**：并入 `dalio_bubble` **表1 估值**(市值/GDP 历史百分位)与整体泡沫读数;`registry_checks` 检查点 = SPY 跌破发言日收盘。
- **④ 为什么忠实**：机制对应(a)——他的核心就是**绝对估值相对历史极端 → 回归**,我们的估值分位度量的正是「相对历史多贵」;方向一致(b):越贵、分位越高 = 他越看空。
- **⑤ 局限**：他用 CAPE / GMO 7 年预测,我们用市值/GDP 百分位**近似**,未含 CAPE 与远期回报模型;下行幅度(−70%)不建模,只建「贵不贵」。

### John Hussman — Hussman Funds
- **① 观点**：估值超 1929/2000/2008,**但要等「内部结构一致性」恶化才兑现**,届时突然而猛烈;下行 50–70%。 *Rich valuation + failing internals → sudden 50–70% drop.*
- **② 时间**：2025-04。
- **③ 我们的建模**：**双落点**——估值面并入 `dalio_bubble`;**「内部结构」面**是 `market_breadth`(RSP÷SPY、IWM÷SPY、板块 200 线广度)。
- **④ 为什么忠实**：这是**最能体现「机制对应」的一条**。Hussman 的独特之处不是「贵」,而是「**贵 + 内部结构裂**才崩」——他明说估值本身不择时。我们没有把他塞进单一估值信号,而是**分别**用泡沫读数(贵)和广度信号(内部结构)对应他论证的**两个必要条件**;方向一致(b):广度越差 `narrow_score` 越高 = 他所谓内部结构恶化。
- **⑤ 局限**：Hussman 用其专有的市值/增加值 + trend uniformity;我们用 ETF 比率/板块广度**近似**内部结构,非其原指标。

### Jim Chanos · Jim Covello · David Cahn — AI 资本开支 ROI
- **① 观点**：AI 资本开支 > 互联网;$1T 投入回报不足 / $600B 收入缺口 / 折旧与循环融资存疑。 *AI capex ROI gap, accounting/circular-financing red flags.*
- **② 时间**：2025-10(Chanos)/ 2026-05(Covello)/ 2026-01(Cahn)。
- **③ 我们的建模**：**暂未有专门 ROI 信号**——目前仅作为 `dalio_bubble` 泡沫读数的**定性印证**(网页「各家印证」),检查点 = SMH 跌破发言日收盘;ROI 子信号列 Phase 2 待办。
- **④ 为什么(还)不完全忠实**:诚实地说,他们的核心是**微观单位经济学**(收入 vs 资本开支),我们现有信号**测不到**——所以我们**不声称**已忠实建模,只把它作为印证声部,并在 roadmap 明确「AI 资本开支 ROI 子信号」。
- **⑤ 局限**:待补真正的 capex/revenue 数据信号,才谈得上忠实。

### Warren Buffett · Torsten Slok
- **Buffett**:①创纪录现金、连续净卖出=以行动示估值贵(2025-11)。③并入 `dalio_bubble` 估值/巴菲特指标(市值/GDP)。④机制对应:市值/GDP 正是「巴菲特指标」本尊;方向一致:越高越贵。⑤只测「贵」,不测其现金择时。
- **Slok**:①前十大 ~50×PE、集中度高(2026-01)。③并入 `market_breadth` 集中度信号。④机制对应:RSP÷SPY 下行 = 涨势向权重股集中,正是他说的「变窄」;方向一致。⑤用 ETF 比率近似「前十大集中度」,非成分权重原数据。

---

## 桶 B · 仓位 / 尾部 · Positioning / Tail → 🔥 `fragility_gate` + 📐 `market_breadth`

### Michael Burry — Scion → Substack
- **① 观点**：被动/指数资金流不做价格发现,底层个股太薄——「**剧场拥挤、出口未变**」,反转时机械踩踏;2025 加折旧会计质疑,做空 NVDA/PLTR。 *Passive flows + illiquidity; a crowded-theater mechanical unwind on reversal.*
- **② 时间**：2019-09(原始论点)+ 2026-08(现持仓)。
- **③ 我们的建模**：`fragility_gate` 的**拥挤/脆弱**评分(VIX 低位、期限结构、实现波动低分位、**一篮 AI/半导体拥挤票的 RSI 中位数**)+ 崩盘当天的**性质诊断**;广度差由 `market_breadth` 补。
- **④ 为什么部分忠实**：方向一致(b)与可证伪(c)成立——「拥挤」用**一篮项目自定义的 AI/半导体拥挤票**度量动量拥挤度(NVDA/PLTR 是他登记在案的空头,另加 MU/AVGO/AMD/TSLA/CAT/AMAT/SOXX 作**与本组合重叠敞口**的代理,**并非其真实空头组合**);崩盘诊断读的是他关心的**跨资产机械踩踏指纹**。但机制对应(a)**只做到一半**:他最核心的「薄名字/流动性错配」硬 tell(成分股日成交额分布)我们**还没做**(需全市场成分表)。
- **⑤ 局限**：**最忠实的那块(流动性硬 tell)恰恰缺位**,列 `fragility_gate` v1.1 首要待办;拥挤篮里多数票**不是他的空头**,其无关波动可能带动该项得分(应视为项目自定义拥挤代理,非「Burry 空头篮」);13F put 名义值≠敞口(文档已警示)。这条我们**不敢声称完全忠实**。

### Mark Spitznagel · Nassim Taleb — Universa
- **① 观点**:先狂欢冲顶后约 −80% 崩(Spitznagel);市场「数十年最脆弱」,非线性尾部(Taleb)。 *Blow-off then ~−80%; most-fragile, non-linear tail.*
- **② 时间**:2025-09 / 2026-01。
- **③ 我们的建模**:`fragility_gate` 的**脆弱性评分**(把「脆弱」量化成 0–5 的干柴)。
- **④ 为什么忠实**:机制对应(a)极强——Taleb 的哲学**正是**「脆弱性是**状态**、不是预测」,我们的侧栏刻意**只量化干柴、不预测火星、不发买卖信号**,与其思想同构;Spitznagel「先融涨后崩」也与 `dalio_bubble` 的「泡沫高+无针→melt-up」判读一致。
- **⑤ 局限**:我们不做尾部对冲/凸性头寸(那是他们的产品),只做「脆弱程度」度量。

### David Einhorn — Greenlight
- **①**被动/动量「打破价格发现」,资金机械涌向高估值(2025)。**③**并入 `fragility_gate`(拥挤)+ `market_breadth`(广度/集中)。**④**机制对应:与 Burry 同源的「被动流扭曲价格发现」,广度变窄正是其可观测后果。**⑤**「被动 AUM/底层流动性错配」的直接 tell 待补(同 Burry 局限)。

### Michael Hartnett — BofA
- **①** Bull & Bear Indicator(资金流/仓位/信用/广度/股债比 0–10)+ 拥挤示警(2026-01)。**③**并入 `market_breadth`(广度/情绪)。**④**机制对应:他的 B&B 本质是**广度+仓位+情绪的合成**,我们的广度信号覆盖其中「广度」支柱、方向一致(变窄=更危险)。**⑤**只覆盖其一支柱(广度),未含资金流(EPFR)与信用分项——**部分忠实**,已标注。

---

## 桶 C · 债务 / 货币 · Debt / Monetary → 🚦 `macro_gate` + 🫧 `dalio_bubble` 货币针

### Jamie Dimon · Stanley Druckenmiller · Albert Edwards · Paul Tudor Jones
- **① 观点**:政府债务/赤字 → 债市危机(Dimon)、财政失序+流动性抽离(Druckenmiller)、财政主导+通胀(Edwards)、主权债务泡沫市值/GDP 252%(PTJ)。 *Sovereign debt/fiscal/liquidity → the pin.*
- **② 时间**:2026-07 / 2025-12 / 2025-11 / 2025-10。
- **③ 我们的建模**:**信用/衰退面**→ `macro_gate` 的信用(Baa-10Y)、曲线、CFNAI 因子;**货币扳机面**→ `dalio_bubble` 的**货币针**(联邦基金 + 10y 实际利率变化)。
- **④ 为什么忠实**:机制对应(a)——这一桶的共同扳机是**利率/流动性/信用**,不是估值;我们的货币针**正是**用「利率是否在收紧」编码「戳破泡沫的针」,与他们**共同关注的触发变量**同源;方向一致(b):利率上行/信用走阔 → 读数转危险。Druckenmiller 检查点 = TLT 下跌(利率收紧的直接价格表现),与其逻辑闭环。
- **⑤ 局限**:未含**私人信贷压力、期限溢价、DXY/美债供需**(Dimon/Edwards 强调的),列 Phase 2 待办;PTJ 的市值/GDP 252% 我们有(表1),但其「近端买、远端对冲」的择时不建模。

---

## 🟢 看多制衡 · Bull Counterweights(防单边看空)

### Mike Wilson · Tom Lee · Dan Ives
- **① 观点**:仓位已出清=新牛市(Wilson)、SPX 7700(Lee)、AI「第三局」(Ives)。
- **③ 我们的建模**:**同一仓位框架、反向解读**——Wilson 与我们的 `fragility_gate` 关注**同一套「拥挤度」变量**,但他把「已出清」读成买点。**须诚实说明:当前实现是单向的**——`fragility_gate` 只对每个因子做「更脆」的布尔阈值、计数求和,低分只给「🟢 低脆弱」标签,**并不输出「底部」判断**。把「拥挤已解除→可能是底」做成显式反向信号,列为 roadmap 待办;此处纳入 Wilson,是为**提醒「低脆弱」不等于看多**、防止单边解读,而非声称模型已具双向能力。
- **④ 为什么重要**:忠实性不止对空头——纳入 Wilson,是要求忠实三原则里的**方向一致 应当**在两端都说得通(否则模型沦为「找证据支持看空」)。但这目前是**设计目标而非已实现能力**:模型尚未产出底部信号,只做到「低分不主张看空」这一步,双向化仍待建。
- **⑤ 局限**:Lee/Ives 的盈利/采用驱动多头,我们仅作检查点(SPY/SMH 高于发言日收盘),未建正向模型。

---

## 附录 · 各模型「怎么算、跟什么比、哪个方向危险」详解 · Appendix: How each model computes, against what, and which direction is dangerous

> 上文 ③ 说了「用哪个模型」;这一节把每个模型**拆到可复核的算法层**——**每个输入怎么变成分数 / 票、跟什么比、越高还是越低才危险、合成后对哪条档位线**,与达利欧那条同样的粒度。**诚实优先**:凡是「近似 / 代理 / 固定阈值 / 短历史」处一律点名,不美化。
> Section ③ said *which* model; this appendix opens each one to the **auditable algorithm** — how each input becomes a score/vote, what it's compared against, whether higher or lower is dangerous, and which band the composite is judged by — at the same granularity as Dalio's. **Honesty first**: every approximation, proxy, fixed threshold, or short lookback is named, not smoothed over.

### A · 🫧 `dalio_bubble` — 泡沫读数(0–100,越高越泡沫)· bubble reading (0–100, higher = more bubbly)
- **怎么算**:6 表(估值/涨势/新买家/情绪/杠杆/远期建设),每表取「当前值在**它自己那段可得历史**中的百分位」;窗口各异(市值/GDP≈1945、纳指≈1985、IPO ETF 2013、VIX 5年、实现波动≈3年、远期建设人工无分位),情绪/杠杆取 `1−百分位`。**可用表百分位取均值 ×100 = 读数**。
- **跟什么比 / 方向**:①表内——当前值 vs 自己历史分布(越高越极端);②合成后——读数 vs 固定档位 **60 / 80**。**读数越高越泡沫**:**≥60** 偏高、**≥80** 晚期泡沫(读数先取整再分类,边界值 60/80 本身落在**高**档,与代码 `>=` 一致)。
- **诚实边界**:1929/2000≈100、2021≈77、2024≈52 是**软性参照档位、非真的重算回那些年**(底层数据不够长),故读数与历史锚点**不严格可比**;等权求均值是对其多指标百分位的**近似**;杠杆/远期建设/供给针均为代理。**+ 双针**(货币针 FEDFUNDS 6月Δ≥+0.25% 或 DFII10 3月Δ≥+0.25%;供给针 IPO 6月分位≥85)= 达利欧「戳破」条件,与读数**正交**(读数说「多大」,针说「何时破」)。
- **How**: 6 gauges, each = current value's percentile **within its own available history** (windows differ widely; sentiment & leverage inverted as `1−pct`). Mean of available gauges ×100 = reading. **Against what / direction**: inside each gauge, current vs its own history (higher = more extreme); the composite vs fixed bands — **≥60** elevated, **≥80** late-stage (the reading is rounded to an integer first, so the boundary values 60/80 fall in the **higher** band, matching the code's `>=`). **Honest edge**: the 1929/2000/2021/2024 anchors are soft reference bands, **not a recompute**, so the reading is **not strictly comparable** to them; equal-weight mean is an approximation; leverage/buildout/issuance are proxies. The **dual pin** (monetary + issuance) is orthogonal — the reading says *how big*, the pin says *when it pops*.

### B · 🚦 `macro_gate` — 六因子衰退闸门(0–6 票,越多越像衰退熊)· six-factor recession gate (0–6 votes)
- **怎么算**:6 因子,每条命中 = 1 张 risk-off 票 —— ①VIX>28 ②收益率曲线 10Y-3M<0(倒挂) ③信用 Baa-10Y 利差的**3年滚动 z 分>1** ④Sahm:失业率3月均 − 近12月最低≥0.5 ⑤CFNAI 3月均<−0.7 ⑥趋势:纳指收盘<200日线**且** 200日线较~1季度前更低。
- **跟什么比 / 方向**:每因子当前值 vs **固定阈值**(唯信用是 vs 自己近3年分布的 z 分)。数值朝衰退方向越过阈值 → 该票亮红。**票数越多越危险**。
- **闸门与仓位**:票数 **≥2 且连续≥10 个交易日**(`PERSIST=10`,约2周)才 ON → 清仓 QQQ;<2 → 买回。连续要求专门**滤掉单日假警报**。仓位:ON→0;否则 `min(100%, 20%目标波动 ÷ QQQ 20日实现波动)`——波动越高仓位越低,**不加杠杆**。这是**唯一发仓位信号**的模型(其余三个只描述、不发买卖)。
- **How**: 6 factors, each a risk-off vote against a **fixed threshold** (credit uses a 3-yr rolling z-score); more votes = more dangerous. **Gate**: votes **≥2 for ≥10 consecutive trading days** → sell QQQ; the persistence requirement filters single-day false alarms. Position = 0 when on, else `min(100%, 20% target-vol ÷ QQQ realized vol)`, never levered. **The only model that emits a position signal.**

### C · 🔥 `fragility_gate` — 脆弱性侧栏(0–5,越高越脆)· fragility sidebar (0–5, higher = more fragile)
- **怎么算**:5 个布尔「干柴」因子,命中各记 1 —— ①VIX<14 ②期限结构 VIX3M/VIX−1>12% **且** VIX<16 ③QQQ 20日实现波动处于近1年**<20 分位** ④QQQ 高于200日线>12%(拉伸) ⑤拥挤篮 RSI(14) 中位数>65。
- **跟什么比 / 方向**:每项当前值 vs 固定阈值(③是 vs 自己近1年分布的分位)。**注意方向与直觉相反——低 VIX、低波动=更危险**,因为它们是「干柴」(波动卖方舒适、vol-target 加杠杆的温床)。命中数求和:≥4 高度脆弱、≥2 中度、否则低脆弱。
- **诚实边界**:**高分 ≠ 卖出**——只量化「一旦有火星火会烧多大」,不预测火星何时来,**不发买卖信号**;当前**单向**(低分只给「🟢 低脆弱」,不判底)。⑤的拥挤篮是**项目自定义 AI/半导体代理**(9 票仅 NVDA/PLTR 是 Burry 登记空头),非其真实空头组合。
- **How**: 5 Boolean "dry-tinder" flags vs fixed thresholds (realized-vol uses a 1-yr percentile). **Counter-intuitive direction: low VIX / low vol = *more* dangerous** (they are the tinder). Sum → ≥4 highly / ≥2 moderately / else low fragile. **High ≠ sell**: it gauges *how big the fire could get*, not *when the spark comes*; emits no buy/sell signal and is currently single-direction. The crowded basket is a **project-defined AI/semiconductor proxy**, not Burry's real short book.

### C-2 · 🧭 崩盘性质诊断(崩盘当天读盘面)· crash-nature diagnostic (reads the same-day tape)
- **怎么算**:SPY/QQQ 单日**≤−3%** 正式触发(平日显示「若今日崩会偏哪型」预演)。读同日 **6 个 tell**,各投「机械型 mech」或「衰退型 reco」:①VIX 期限结构骤然倒挂(<−5%)=急性恐慌(两型皆有) ②长债 TLT:涨≥+0.5%=避险=衰退 / 跌≤−0.3%=无差别抛售=机械 ③高收益信用 HYG 相对其对 SPY 的 beta(0.35)超跌>0.5%=信用走坏=衰退 ④黄金 GLD:跟跌≤−0.5%=流动性挤兑=机械 / 涨≥+0.5%=有序避险=衰退 ⑤防御 vs 科技(XLP/XLU 均值−XLK)>+2%=轮动=衰退 / 否则=同跌=机械 ⑥当日闸门票数:0=全绿里崩=机械 / ≥2=衰退语境。
- **判读 / 方向**:mech 票 > reco → **机械/1987型**(不带衰退、恢复最快,约2年);reco > mech → **衰退型**(恢复最慢:2000≈7年、2008≈5.5年);打平=待确认。对应 Burry「机械踩踏」vs 基本面熊的区分——**答的是「崩的性质」,不是「会不会崩」**。
- **How**: triggers at a same-day SPY/QQQ move **≤−3%**; reads 6 cross-asset tells, each voting *mechanical* or *recessionary* (bonds/gold/credit/defensives-vs-tech/term-structure/gate-votes). More mech → 1987-type (no recession, ~2-yr recovery); more reco → recession-type (slowest: ~7 yrs 2000, ~5.5 yrs 2008). It answers *what kind of crash*, not *whether* one comes.

### D · 📐 `market_breadth` — 广度/集中度(0–3 狭窄计分,越高越窄)· breadth/concentration (0–3, higher = narrower)
- **怎么算**:3 信号命中各记 1 —— ①RSP÷SPY(等权/市值)近 **63 交易日(~3月)变化<0** ②IWM÷SPY(小盘/大盘)近 63 交易日变化<0 ③板块广度:11 个 SPDR 站上各自 200日线的比例**<50%**(需≥7 板块有效才计)。
- **跟什么比 / 方向**:①②是比率的**时间变化**(现在 vs 3月前,向下=涨势向权重股集中/小盘落后=变窄);③是**横截面比例** vs 50%。**越窄=内部结构越弱=反转时越脆**。命中数:≥2 狭窄、1 中性偏弱、0 健康;只在有数据的信号里计分。
- **印证**:Hussman 内部结构一致性 / Slok·Kolanovic 前十大集中度 / Burry 拥挤;**与三体制正交、不发买卖**。
- **How**: 3 signals — RSP÷SPY and IWM÷SPY **3-month ratio changes** (falling = narrowing) and the share of 11 SPDR sectors above their 200-DMA (**<50% = weak**, needs ≥7 valid). Narrower = weaker internals = more fragile on reversal. Corroborates Hussman/Slok/Burry; orthogonal, no buy/sell.

### E · 🧪 `research/backtest.py` — 统一回测框架(**已在 `main`**,经 PR #7 合并)· unified backtest framework (**now in `main`**, merged via PR #7)
- **状态**:框架代码 + 合成数据单测已随 **PR #7 合并进 `main`**,`research/README.md` 的 Phase 3 已勾选「统一回测框架」。它是**研究工具**(手动/研究时跑,**不接**定时 workflow),下述为其接口与口径。
- **作用**:承接忠实三原则里的 **(c) 可证伪**。输入「价格序列 + 信号序列」→ 输出**命中率 / 领先时间 / 规避回撤 / Sharpe / vs 买入持有**。**无前视**:信号按 `lag=1` 滞后(今天的信号明天才调仓)。
- **两种口径**:**事件型** `event_eval`——示警日之后 `fwd`(默认 63 交易日≈1季度)前瞻收益<0 的比例=命中率;示警 vs 非示警平均前瞻收益之差=判别力(**越负越有效**);示警起点→其后低点的交易日数=领先时间。**仓位型** `backtest`——weight∈[0,1] 择时 vs 买入持有,输出规避回撤 / 超额 CAGR / 在市比例 / 换手。
- **意义**:前三个「描述型」模型(泡沫/脆弱/广度)本身不发买卖,但**能不能提前区分危险**是可检验的——框架已在 `main`,**下一步(Phase 3 续)** 是在 Actions 用历史 FRED/yfinance 重算各模型读数喂入,把「模型代表某分析师观点」从 ④ 的**文字论证**推进到**可证伪的历史数据检验**。
- **Status**: the framework and its synthetic unit tests are now **merged into `main` via PR #7**; `research/README.md` checks off the Phase-3 framework line. It is a **research tool** (run manually, **not** wired to a scheduled workflow); the following describes its interface and semantics.
- **Role**: it lands faithfulness criterion **(c) falsifiable**. Price + signal → hit-rate / lead-time / drawdown-avoided / Sharpe / vs buy-hold, with **no look-ahead** (`lag=1`). Event mode scores whether warnings precede losses (discrimination, the more negative the better); position mode scores timing vs buy-hold. The framework is in `main`; the **next step (Phase 3 continued)** is to recompute each model's historical readings in Actions and feed them in, moving "this model represents the analyst's view" from a **written argument (④)** to a **testable historical result**.

---

## 附录二 · 实证:历史回测 + 危机前30天(数据怎么说)· Appendix II — Empirics: historical backtest + the 30 days into each crisis

> 前面是「我们**声称**这些模型代表某观点」;这一节让**数据自己说话**。`research/backtest_models.py` 把四模型的历史信号(无前视)喂进回测引擎;`research/crisis_windows.py` 回放过去 ~30 年 10 次危机、看崩盘前 30 交易日仪表盘的真实读数。**结论既验证了主张,也诚实暴露了边界**。实时数字见网页「🧪 模型回测记分卡」「🧭 危机前30天」两面板 + `research/backtest_results.json`、`research/crisis_windows.json`。
> The claims above are ours; this section lets the **data** speak. Full history fed through the backtest engine (no look-ahead), plus a replay of the 30 trading days into 10 crises over ~30 years. It both **confirms the claims and honestly exposes the limits**.

### 回测记分卡(判别力:负=示警后更差=有效)· Backtest scorecard (discrimination: negative = effective)
| 模型 · model | 判别力 discrim. | 规避回撤 DD-avoided | 超额CAGR | 读法 · reading |
|---|---|---|---|---|
| **macro_gate** | **−2.35%** ✅ | **+43pp** ✅ | **+0.84%** ✅ | **唯一真·风控**(且只对衰退熊) |
| fragility ≥4 | −1.52% ✅ | +0pp | −0.11% | 轻微预警,非卖点 |
| fragility ≥2 | −0.19% | +3.5pp | −2.4% ✗ | 太松,当卖点亏 |
| dalio ≥60 | **+1.35%** ⚠️ | +0pp | −1.5% ✗ | 正=**融涨**(量级表非择时器) |
| dalio ≥80 | **+2.47%** ⚠️ | +0pp | −0.27% | 越晚期越涨(纯融涨) |
| **dalio ≥80 且货币针** | **+3.19%** ⚠️ | +0pp | +0.03% | **校准实验:针没能补上择时价值** |
| breadth ≥2 | +0.10% | +0.6pp | −5.2% ✗ | 当卖点最亏 |

### 危机前30天:四模型当时真显示什么 · What the models showed into each crisis
| 危机 | 崩幅63d | 🚦macro | 🔥脆弱 | 🫧泡沫 | 📐狭窄 |
|---|---|---|---|---|---|
| 2001 9·11 | −12% | **4/6·闸门提前60日** | 1/4 | 10 | 2/2 |
| **2008 雷曼** | **−40%** | **4/6·闸门提前146日** | 0/5 | 31 | 1/3 |
| 2018 Q4 | −20% | 0/6 off | **3/5** | 73·针ON | 2/3 |
| 2015 人民币 | −11% | 1/6 off | 2/5 | 76·针ON | 2/3 |
| 2020 新冠 | −34% | 1/6 off | 2/5 | 60 | 2/3 |
| 2000 互联网 | −11% | 0/6 off | 1/4* | 42* | 1/1* |
*（`部分`:该危机早于 VIX3M 2007 / RSP 2003,按真实分母呈现。full table on the webpage.）

### 五个诚实结论 · Five honest takeaways
1. **macro_gate 精准预警了唯二的「真·衰退危机」——2001(提前60日)、2008(提前146日)**,且对所有机械/快速崩盘(2010/2020/2022)保持沉默。这不是漏报,正是设计:**它是衰退熊探测器,不是闪崩探测器**;与其 +43pp 规避回撤、唯一正超额一致。
   *macro_gate pre-warned the only two recession crises (60d, 146d lead) and stayed silent for the mechanical/fast crashes — by design, a recession detector, not a flash-crash detector.*
2. **fragility 抓住了 macro 漏掉的「自满型」抛售**——2018 Q4(3/5)、2015 / 2020(2/5),都是低波动/拥挤驱动。**两模型互补**,正如正文所述。
   *fragility caught the low-vol/complacency selloffs macro misses — the two are complementary.*
3. **没有任何单一模型能预警一切**:2020 新冠(−34%)是外生冲击,四表皆温和。**没有基本面模型能预见一次病毒冲击**——这是诚实边界,不是 bug。
   *No single model warns of everything; COVID was exogenous — no fundamentals model foresees a virus.*
4. **达利欧扩张分位读数在最早的泡沫上失真**:2000 互联网见顶读数仅 42(短历史可比样本少 + IPO 表 2013 才有)。**2013 后的读数(2015=76、2018=73)才可信**——这是扩张分位+短历史的已知伪影,如实标注。
   *The expanding-percentile bubble reading is muted for the earliest bubbles (2000 = 42) — a known short-history artifact; only post-2013 readings are trustworthy.*
5. **校准实验的诚实结果**:「泡沫≥80 **且**货币针」判别力仍为正(+3.19%)——**我们操作化的货币针没能把泡沫读数变成择时信号**。保留 dalio 为「量级参考」的定位,**货币针的操作化列为待细化**(粗代理「任意6月+0.25%加息」可能不够特异)。
   *Calibration result, honestly: gating the bubble on our monetary-pin proxy did **not** turn it into a timer — the reading stays a magnitude gauge; the pin's operationalization is flagged as to-refine.*

> 一句话:**数据证明了正文的核心分工**——macro_gate 是唯一能提前拉响的风控(且只对衰退熊),fragility 补机械崩,达利欧读数是「量级表」不是「闹钟」,而外生冲击谁都测不到。
> In one line, the data confirms the division of labor the body argues: macro_gate is the only advance risk tool (recession bears only), fragility covers mechanical crashes, the Dalio reading is a magnitude gauge not an alarm clock, and exogenous shocks are beyond all of them.

---

## 一句话总纲 · The through-line

> 我们**只在能满足「机制对应 + 方向一致 + 可证伪」时才声称忠实**;满足不了的(Burry 流动性硬 tell、Chanos/Covello 的 ROI、Dimon 的私人信贷),一律在 ⑤ 标为「印证/待建」,**绝不用贴标签冒充建模**。这份「诚实的不完整」清单,本身就是 Phase 2/3 的施工图。
> We claim faithfulness **only** when mechanism-match + directional-match + falsifiability all hold; where they don't (Burry's illiquidity tell, the AI-ROI cluster, Dimon's private credit), we label it "corroboration / to-build" rather than dress a label up as a model. This honest list of gaps *is* the Phase 2/3 blueprint.

*研究底稿,随建模推进滚动更新;不构成投资建议。 A living draft; not investment advice.*
