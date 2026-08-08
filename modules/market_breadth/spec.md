# 市场广度 / 集中度信号 — 功能规格 (spec.md)

**模块文件**: `market_breadth.py`
**创建日期**: 2026-08-08
**状态**: 已实现 v1.0（见 status.md）
**归属**: 专项研究课题 Phase 2（框架化建模）· `research/README.md`

---

## 模块目标

把多位分析师**共用**的「市场内部结构 / 集中度 / 拥挤」方法**可计算化**,只用流动 ETF(避免 Burry「成分股日成交额分布」所需的全市场成分表):

- **Hussman** —「市场内部结构一致性」(trend uniformity)
- **Slok / Kolanovic** —「前十大集中度、涨势变窄」
- **Burry** —「拥挤、广度差 = 反转时更脆」

与三体制模型正交、互补:**广度差 = 内部结构弱 → 印证 `fragility_gate`(B 仓位)与 `dalio_bubble` 的泡沫内部(A 估值)**。不发买卖信号。

## 信号(均自流动 ETF)

| # | 信号 | 计算 | 弱(变窄)条件 |
|---|------|------|--------------|
| 1 | 等权/市值 | `RSP÷SPY` 比率近 ~3 月(63 交易日)变化 | < 0(权重股独强,变窄) |
| 2 | 小盘/大盘 | `IWM÷SPY` 比率近 ~3 月变化 | < 0(小盘落后,变窄) |
| 3 | 板块广度 | 11 个 SPDR 板块(XLK/XLF/XLE/XLV/XLI/XLY/XLP/XLU/XLB/XLRE/XLC)站上各自 200 日线的比例 | < 50% |

**狭窄计分 `narrow_score`**（0–3,越高越窄/越脆）:三条各命中记 1;**只在有数据的信号里计分**(缺数据不当成健康)。
> 广度信号要求**至少 `MIN_SECTORS=7`/11 个板块有效**才计;否则视为不可用("—",不计分),避免个别 ETF 拉取失败时用 1 只误报「广度差」。

## 判读

| narrow_score | 判读 | 色 |
|---|---|---|
| ≥ 2 | 🔴 市场狭窄 / 内部结构弱(涨势集中、反转更脆) | red |
| 1 | 🟡 广度中性偏弱 | amber |
| 0 | 🟢 广度健康(普涨、内部结构稳) | green |
| 无可用信号 | 数据不足 | muted |

## 输出

写入 `docs/data.json` 的 `[today]["market_breadth"]`:`narrow_score / signals_used / signals_total / breadth_pct / color / signals[] / verdict / verdict_en / note / note_en`。
网页 `docs/index.html` `renderMarketBreadth()`,位于达利欧泡沫面板下方,**中英双语**、null-safe。**不推送微信**。

## 运行时机

`daily_brief.yml`(盘后)与 `macro_gate.yml`(盘中每小时)中,排在 `dalio_bubble.py` 之后。均 `continue-on-error: true`。

## 边界

- 用 ETF 比率/板块 200 日线**近似**内部结构与集中度,**非**全市场成分股广度(Burry 的薄名字计数需全市场成分表,列 fragility v1.1 roadmap)。
- 数据缺失优雅降级(缺信号不计分)。**不构成投资建议**。
