# 市场广度 / 集中度信号 — 进度追踪 (status.md)

**最后更新**: 2026-08-08
**当前版本**: v1.0（已实现并接入）
**负责角色**: Claude Code
**依赖**: yfinance（SPY/RSP/IWM + 11 SPDR 板块 ETF）

---

## 已完成 v1.0

- [x] 信号1 等权/市值 `RSP÷SPY` 近3月趋势
- [x] 信号2 小盘/大盘 `IWM÷SPY` 近3月趋势
- [x] 信号3 板块广度(11 板块站上 200 日线比例)
- [x] `narrow_score` 0–3(只在有数据的信号里计分)+ 红/黄/绿/muted 判读
- [x] 写入 `docs/data.json` 的 `market_breadth`;双语字段(verdict/note/signal name/detail 的 `_en`)
- [x] 网页 `renderMarketBreadth()`(达利欧面板下方,中英双语,null-safe)
- [x] 接入 `daily_brief.yml` + `macro_gate.yml`(排 dalio_bubble 之后)
- [x] 合成数据测试:狭窄→red / 健康→green / 中性→amber / 空数据→muted;双语字段校验

## 已知限制 / 待办

- [ ] 用 ETF 比率/板块 200 线近似,非全市场成分股广度;Burry 薄名字计数(需成分表)列 `fragility_gate` v1.1。
- [ ] 可加:高低价新高新低比、AD line、前十大权重占比(需成分数据)。
- [ ] 阈值(63日/50%广度)可在 Phase 3 回测中校准。
- [ ] 本地无法跑 yfinance 端到端(沙箱封 Yahoo);线上 GitHub Actions 正常。

## 备注

- Phase 2「框架化建模」首个信号:把 Hussman 内部结构 / Slok·Kolanovic 集中度 / Burry 拥挤 可计算化。
- 与三体制正交,印证 fragility(B)与 dalio_bubble 内部(A);registry 中对应 Hussman/Slok/Kolanovic/Burry 档案。
