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
- **③ 我们的建模**：`dalio_bubble` **就是他方法的直接实现**——6 表(估值/涨势/新买家/情绪/杠杆/远期建设)按 1900 以来百分位取均值 = 泡沫读数;**双针**(货币针 FEDFUNDS/实际利率 + 供给针 IPO 发行)= 他的「戳破」条件;领先对(新买家+情绪)。
- **④ 为什么忠实**：这是**本项目里忠实度最高的一条**——不是把别人的话套框架,而是**照抄他公开的 6 表方法论**(见 `notes/…§10`、其 2021《Are We in a Stock Market Bubble?》)。机制对应(a):双针直接编码他「泡沫需货币收紧才破」的因果论断;方向一致(b):6 表越高、双针越响 = 他口径的「越危险」;可证伪(c):百分位锚点(1929/2000≈100、2021≈77、2024≈52)是他本人给的刻度。
- **⑤ 局限**：表5杠杆用「低波动」代理(非 FINRA 保证金)、表6人工档、等权是对其多指标百分位的**近似**、供给针用 IPO ETF 代理。已在 spec 标注。

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
- **③ 我们的建模**：`fragility_gate` 的**拥挤/脆弱**评分(VIX 低位、期限结构、实现波动低分位、**Burry 做空篮子 RSI 拥挤**)+ 崩盘当天的**性质诊断**;广度差由 `market_breadth` 补。
- **④ 为什么部分忠实**：方向一致(b)与可证伪(c)成立——「拥挤」用他做空的**那一篮子**的动量拥挤度直接度量,崩盘诊断读的是他关心的**跨资产机械踩踏指纹**。但机制对应(a)**只做到一半**:他最核心的「薄名字/流动性错配」硬 tell(成分股日成交额分布)我们**还没做**(需全市场成分表)。
- **⑤ 局限**：**最忠实的那块(流动性硬 tell)恰恰缺位**,列 `fragility_gate` v1.1 首要待办;13F put 名义值≠敞口(文档已警示)。这条我们**不敢声称完全忠实**。

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
- **③ 我们的建模**:**同一仓位框架、反向结论**——Wilson 与我们的 `fragility_gate` 用**同一套「拥挤度」变量**,但他把「已出清」读成买点。我们据此把「拥挤」编码为**双向**信号(拥挤高=脆;拥挤已解除=可能是底),而非单边看空。
- **④ 为什么重要**:忠实性不止对空头——把 Wilson 纳入,正是为满足忠实三原则里的**方向一致**必须双向:同一变量在两端都要说得通,否则模型是「找证据支持看空」而非中立度量。
- **⑤ 局限**:Lee/Ives 的盈利/采用驱动多头,我们仅作检查点(SPY/SMH 高于发言日收盘),未建正向模型。

---

## 一句话总纲 · The through-line

> 我们**只在能满足「机制对应 + 方向一致 + 可证伪」时才声称忠实**;满足不了的(Burry 流动性硬 tell、Chanos/Covello 的 ROI、Dimon 的私人信贷),一律在 ⑤ 标为「印证/待建」,**绝不用贴标签冒充建模**。这份「诚实的不完整」清单,本身就是 Phase 2/3 的施工图。
> We claim faithfulness **only** when mechanism-match + directional-match + falsifiability all hold; where they don't (Burry's illiquidity tell, the AI-ROI cluster, Dimon's private credit), we label it "corroboration / to-build" rather than dress a label up as a model. This honest list of gaps *is* the Phase 2/3 blueprint.

*研究底稿,随建模推进滚动更新;不构成投资建议。 A living draft; not investment advice.*
