# Daily Brief — 项目状态总览 (PROJECT_STATUS.md)

> **用法**：新对话开始时把这份文件发给 Claude，即可一次性同步项目全貌、各模块进度、已知问题与下一步。
> **AUTO 区块由 `update_status.py` 自动刷新**（运行状态 + 开发变更）；其余章节人工维护，程序不碰。
> **配套文档**：`CLAUDE.md`（总纲）、`AGENTS.md`（分工）。

---

## 0. 一句话概述

自动化投资简报系统，GitHub Actions 每日运行，结果推送企业微信 + 发布 GitHub Pages（`rachelxrz.github.io/daily-brief`）。中英双语输出。

---

## ⚙️ 运行状态（自动刷新）

<!-- AUTO:START — 程序生成，请勿手改 -->

**自动刷新时间**：2026-07-09 22:44 CST
**data.json 今日更新**：—

**今日各模块产出状态**（依据 `docs/data.json`）：
- 每日简报 (main.py)：⚪ 今日无产出
- 市场结构监控 (market_monitor.py)：⚪ 今日无产出
- 国会交易信号 (congress_tracker.py)：⚪ 今日无产出
- Wheel Strategy (wheel_strategy.py)：⚪ 今日无产出

**自上次刷新以来的开发变更**（git commit，已过滤每日数据提交）：
- `1290986` 2026-07-09 — Fix: batch news translation per-category to prevent truncation dropping later sections

<!-- AUTO:END -->

---

## 1. 整体进度快照

| 模块 | 状态 | 网页 tab | 企业微信 | data.json key |
|------|------|---------|---------|--------------|
| 模块 A — 板块 ETF 轮动 Screener | ✅ 已完成 | ✅ 强势股筛选 | ✅ | ✅ |
| 模块 B — Watchlist 技术分析 | ✅ 已完成 | ✅ 每日简报内 | ✅ | ✅ |
| 市场结构监控 (`market_monitor.py`) | ✅ 已完成 | ✅ 结构监控 | ✅ | ✅ `monitor` |
| AI 双语简报（Claude API） | ✅ 已完成 | ✅ 每日简报 | ✅ | ✅ `news` |
| 风险分析仪表板 | ✅ 已完成 | ✅ 简报内嵌 | — | ✅ |
| `watchlist_manager.py` | ✅ v1.1 已完成 | — | — | — |
| **国会交易信号** (`congress_tracker.py`) | ✅ **v1.2 已上线** | ✅ 国会信号 tab | ✅ | ✅ `congress` |
| **Wheel Strategy** (`wheel_strategy.py`) | ✅ **v1.1 已上线** | ✅ Wheel tab | ✅ | ✅ `wheel` |
| **技术信号+期权建议** (`signal_advisor.py`) | ✅ **v1.1 已上线** | ✅ 技术信号 tab | ✅ | ✅ `signal_advisor` |

---

## 2. 各模块详细状态

### 已完成模块（A / B / 市场监控 / AI简报 / 风险面板）
稳定运行，网页三 tab（每日简报 / 结构监控 / 强势股筛选）正常展示。`data[today]` 写入 `news` 与 `monitor` 两个 key。

### ✅ watchlist_manager.py（v1.1）
三层结构：`core_holdings`（手动，4只持仓）/ `long_term`（手动，26只）/ `congress_signals`（自动，90天过期清理）。Wheel 仓位 CRUD。数据文件：`docs/watchlist.json`。congress_tracker 已接入（买入信号自动写入 congress_signals 层）。

### ✅ 国会交易信号（congress_tracker.py v1.2）
- 数据源：House Stock Watcher 社区镜像（TattooedHead，23,531+ 条，House only）
- 5 层评分 + 4 类持仓对比 + 反向信号检测 + 14天去重
- AI 解读：有强/中信号时调用 Claude API 生成 2-3 句中文洞察
- 推送：ServerChan + WeCom + WxPusher，每工作日 16:30 ET 自动运行
- 网页：国会信号 tab，含 AI 解读卡片、行业分布、反向信号
- watchlist 集成：买入信号 ≥3分 自动写入 `congress_signals`

**已知限制**：
- 参议院数据源（原 Senate Stock Watcher）完全失效，Rick Scott / Alex Padilla 无覆盖
- 当前 7 天窗口内信号稀少（Pelosi 最新披露 2026-01-16，为正常状态）

### ✅ Wheel Strategy（wheel_strategy.py v1.1）
- **候选筛选**：全 Watchlist 扫描，MA20/MA50/ADX(>20)/RSI(35-70)/IV(>20%)/均量(>50万) 六重过滤，推荐最近月度到期日 Strike（92% 当前价）和 Premium 估算
- **持仓追踪**：读取 `wheel_positions`，实时拉价，判断安全/注意/危险，输出操作建议
- **触发时间**：每工作日 08:00 ET（开盘前），支持 `wheel_only` 手动触发
- **网页**：Wheel tab（第5个），候选卡片 + 持仓色块 + 本月收益统计
- **添加仓位**：直接编辑 `docs/watchlist.json` → `wheel_positions`

**已知限制**：
- Premium 为简化估算，非实时期权链报价
- IV 从 yfinance 期权链近月 ATM Put 取值，无期权时退回默认 0.35

---

## 3. 输出渠道现状

- **网页 tab（6个）**：每日简报 ✅ ｜ 结构监控 ✅ ｜ 强势股筛选 ✅ ｜ 国会信号 ✅ ｜ Wheel ✅ ｜ 技术信号 ✅
- **企业微信**：WxPusher + ServerChan + WeCom，中英双语。
- **data.json**：结构 `data[YYYY-MM-DD] = {updated, news, monitor, congress, wheel, signal_advisor}`，保留最近 30 天。

---

## 4. 当前持仓与 Watchlist

**核心持仓**：GLD 30% · QQQ 25% · WTI 20% · TLT 20%（均 long）

**Watchlist（26）**：ALB, ANET, AVGO, BDRY, CEG, CIEN, COHR, COPX, ETHA, FRO, GEV, GS, HEWJ, LITE, MP, NEE, NVDA, PLTR, PWR, VRT, VST, MPWR, ADI, GOOG, NBIS, MPC

数据文件：`docs/watchlist.json`（三层结构 + wheel_positions）

---

## 5. GitHub Actions 触发时间表

| Job | 触发时间（ET） | 说明 |
|-----|--------------|------|
| `daily-news-brief` | 08:00 + 18:00（每日）| 新闻简报 + AI 双语报告 |
| `market-monitor` | 09:30 + 18:30（工作日）| 市场结构监控 |
| `wheel-strategy` | 08:00（工作日）| Wheel 候选筛选 + 持仓追踪 |
| `congress-signal` | 16:30（工作日）| 国会交易信号 |
| `signal-advisor-premarket` | 08:00（工作日）| 技术信号+期权建议 盘前 |
| `signal-advisor-postmarket` | 17:30（工作日）| 技术信号+期权建议 盘后 |
| `update-status` | 随 news + market 后自动触发 | 刷新 PROJECT_STATUS.md AUTO 区块 |

---

## 6. 数据源与 Secrets

| 数据 | 来源 | 状态 |
|------|------|------|
| 股价 / 技术指标 / IV | yfinance | ✅ 稳定 |
| AI 分析 | Claude API (`claude-sonnet-4-20250514`) | ✅ |
| 推送 | WxPusher + ServerChan + WeCom | ✅ |
| 国会交易（House） | House Stock Watcher 社区镜像（TattooedHead） | ✅ 稳定 |
| 国会交易（Senate） | 原 Senate Stock Watcher | ❌ 完全失效 |

**GitHub Secrets**：
`WECOM_WEBHOOK_URL` · `WXPUSHER_APP_TOKEN` · `WXPUSHER_UIDS` · `SERVERCHAN_SENDKEY` · `ANTHROPIC_API_KEY`

---

## 7. 下一步优先级

1. **signal_advisor IRA 持仓**：`IRA_HOLDINGS` 待用户补充真实 IRA 仓位
2. **参议院数据补全**：寻找可靠免费替代（Quiver Quant 免费层 / Capitol Trades 抓取）
3. **Wheel v1.2**：月度收益统计完善（胜率、P&L 明细）
4. **signal_advisor v2.0**：接入真实 IV 数据（Unusual Whales）
5. **congress_tracker v2.0**：参议院覆盖（依赖第2项）

---

## 8. 变更日志

- **2026-06-15**：`signal_advisor.py` v1.1 上线；四指标（Supertrend/SQZ Momentum/ADX+DI/MA）+ 六种信号 + LEAP/MID_TERM 期权建议；网页新增第6个 tab（技术信号）；daily_brief.yml 新增盘前(08:00 ET) + 盘后(17:30 ET) 两个 job。
- **2026-06-14**：`watchlist_manager.py` v1.1、`congress_tracker.py` v1.2（AI 解读）、`wheel_strategy.py` v1.1（候选筛选+持仓追踪）全部上线；网页新增第5个 tab（Wheel）；PROJECT_STATUS 全面更新。
- **2026-06-13**：congress_tracker.py v1.0/v1.1 完成，干运行通过。`update_status.py` + AUTO 区块加入仓库。
