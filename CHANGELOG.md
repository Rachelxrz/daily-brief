# 更新日志 (CHANGELOG)

系统功能改动记录。watchlist 每日自动增删/暂停的**数据审计**见 `docs/watchlist_changelog.json`（网页「均线信号」页可展开查看）。

## 2026-08-07

### 新增：个股基本面分档（成长性核心/稳定核心/趋势成长/题材投机）
- 新增 `stock_classifier.py`：按**纯基本面**给每只股票定档，写入 `docs/watchlist.json` 的 `classification`（每票含 archetype/profit/市值/上市年限 + 特性 vol/beta/maxdd）。
- **定档规则**（回撤/波动/Beta 不参与定档，只作特性给交易层）：
  - 题材投机 = 当前亏损 或 上市<3年；
  - 核心 = 市值≥$50B 且 上市≥8年 且 **近3年逐年净利润为正**（成长核心=最新>3年前；稳定核心=年年正但未超3年前）；
  - 趋势成长 = 有盈利但够不到核心。
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
