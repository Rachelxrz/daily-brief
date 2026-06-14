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

**自动刷新时间**：2026-06-15 04:12 CST
**data.json 今日更新**：—

**今日各模块产出状态**（依据 `docs/data.json`）：
- 每日简报 (main.py)：⚪ 今日无产出
- 市场结构监控 (market_monitor.py)：⚪ 今日无产出
- 国会交易信号 (congress_tracker.py)：⚪ 今日无产出
- Wheel Strategy (wheel_strategy.py)：⚪ 今日无产出

**自上次刷新以来的开发变更**（git commit，已过滤每日数据提交）：
- `3ec74b8` 2026-06-14 — ci: 新增 update-status job 2026-06-14
- `4768933` 2026-06-14 — docs: 网页新增国会信号面板 2026-06-14
- `caa07a8` 2026-06-14 — Add files via upload

<!-- AUTO:END -->

---

## 1. 整体进度快照

| 模块 | 状态 | 网页显示 | 企业微信 | 写入 data.json |
|------|------|---------|---------|---------------|
| 模块 A — 板块 ETF 轮动 Screener | ✅ 已完成 | ✅ 强势股筛选 tab | ✅ | ✅ |
| 模块 B — Watchlist 技术分析 | ✅ 已完成 | ✅ 自选股技术分析 | ✅ | ✅ |
| 市场结构监控 | ✅ 已完成 | ✅ 结构监控 tab | ✅ | ✅ `monitor` |
| AI 双语简报（Claude API） | ✅ 已完成 | ✅ 每日简报 tab | ✅ | ✅ `news` |
| 风险分析仪表板 | ✅ 已完成 | ✅ | — | ✅ |
| **国会交易信号** (`congress_tracker.py`) | 🚧 代码已写，**未合入仓库** | ❌ | ❌ | ❌ |
| **Wheel Strategy** (`wheel_strategy.py`) | ⬜ 仅有 spec | ❌ | ❌ | ❌ |
| `watchlist_manager.py`（wheel 前置） | ⬜ 待开发 | — | — | — |

---

## 2. 各模块详细状态

### 已完成模块（A / B / 市场监控 / AI简报 / 风险面板）
稳定运行，网页三 tab（每日简报 / 结构监控 / 强势股筛选）正常展示。`data[today]` 写入 `news` 与 `monitor` 两个 key。

### 🚧 国会交易信号 (`congress_tracker.py`)
**重要：代码已在 Claude Code 写好（5 层 spec），但尚未合入仓库。** 证据：当前仓库的 `save_to_web.py` 没有 `save_congress()`，`daily_brief.yml` 没有 congress job。这就是网页看不到议员交易的根因——Actions 从未运行过它。

实现内容（待合入）：5 层 spec、`TRACKED_MEMBERS` 匹配、7 天披露窗口、$10K 门槛、评分公式、四种持仓对比、推送格式 + 板块条形图 + anti-signals、去重 `congress_seen.json`；连带改 `save_to_web.py` / `requirements.txt` / `daily_brief.yml`。Dry-run 抓 23,531 条 House 记录，窗口内 0 笔（正常）。

**已知问题 / 待确认**：
- **代码合入**：先确认 commit + push（这是第一步）。
- **参议院缺失**：`fetch_senate_trades()` 是 stub，只有 House → `TRACKED_MEMBERS` 里 Rick Scott / Alex Padilla（参议员）抓不到。
- **评分顺序**：实现里 `delay>60` 是“强制弱信号”硬规则，spec 里只是 -2 分；确认加分不会突破封顶。
- **微信条形图**：方块字符（████）在手机端易错位，真机验证。
- **去重 key**：确认用披露/交易 ID，而非 member+ticker+date。
- ✅ spec 已澄清：基础分区分买/卖（期权买3/股票买2/股票卖1），规模按区间分桶。

### ⬜ Wheel Strategy (`wheel_strategy.py`)
仅有 spec。三大功能：卖 Put 候选筛选、持仓追踪（安全/注意/危险）、推送日报 + 月度收益。前置依赖 `watchlist_manager.py`（v1.0，未建）。Premium 用 yfinance 取 IV 估算，不依赖期权链 API。v1.0 仓位手动写 `docs/watchlist.json` 的 `wheel_positions`。

---

## 3. 输出渠道现状

- **网页 tab**：每日简报 ✅ ｜ 结构监控 ✅ ｜ 强势股筛选 ✅ ｜ 国会信号 ❌（待加）｜ Wheel ❌（待加）
- **企业微信**：WxPusher + ServerChan + WeCom，中英双语。
- **data.json**：`docs/data.json`，结构为 `data[YYYY-MM-DD] = {updated, news, monitor, ...}`，保留最近 30 天。

---

## 4. 当前持仓与 Watchlist

**核心持仓**：GLD 30% · QQQ 25% · WTI 20% · TLT 20%（均 long）

**Watchlist（26）**：ALB, ANET, AVGO, BDRY, CEG, CIEN, COHR, COPX, ETHA, FRO, GEV, GS, HEWJ, LITE, MP, NEE, NVDA, PLTR, PWR, VRT, VST, MPWR, ADI, GOOG, NBIS, MPC

**板块 ETF**：XLE · XLI · XLU · XLB · XLP · GLD · COPX

---

## 5. 数据源与 Secrets

| 数据 | 来源 | 状态 |
|------|------|------|
| 股价 / 技术指标 | yfinance | ✅ 稳定 |
| AI 分析 | Claude API | ✅ 模型串见 `save_to_web.py` |
| 推送 | WxPusher + ServerChan + WeCom | ✅ |
| 国会交易 | Capitol Trades（备用 Unusual Whales / Quiver） | ⚠️ 无官方 API，结构易变 |

**GitHub Secrets（以真实 `daily_brief.yml` 为准）**：
`WECOM_WEBHOOK_URL` · `WXPUSHER_APP_TOKEN` · `WXPUSHER_UIDS` · `SERVERCHAN_SENDKEY` · `ANTHROPIC_API_KEY`

> ⚠️ 注意：`CLAUDE.md` 里列的 secret 名（`WXPUSHER_TOKEN` / `SERVERCHAN_KEY`）与真实 yaml 不一致，建议同步修正 CLAUDE.md。

---

## 6. 待确认 / 立即可做

- [ ] 确认 `congress_tracker.py` 及连带改动**是否已 commit + push**（当前证据显示**未合入**）。
- [ ] 合入后，给 `index.html` 加“国会信号” tab，读取 `data[today]["congress"]` 渲染。
- [ ] 让 congress / wheel 模块往 `data[today]` 写自己的 key，运行状态才会在 AUTO 区块显示。
- [ ] 真机检查微信条形图对齐。
- [ ] 同步修正 `CLAUDE.md` 的 secret 名。

---

## 7. 下一步优先级

1. 把 congress 真正合入并跑通上线（commit → 触发 → 前端 tab）。
2. 补 `fetch_senate_trades()`（参议院覆盖）。
3. 建 `watchlist_manager.py`（wheel 前置）。
4. 开发 wheel v1.0。

---

## 8. 变更日志

- **2026-06-14**：加入 AUTO 自动刷新区块（`update_status.py`）；按真实 yaml 修正 secret 名；确认 congress 代码尚未合入仓库（save_to_web 无 save_congress、yaml 无 congress job）。
- **2026-06-13**：congress_tracker.py v1.0 在 Claude Code 完成实现，dry-run 通过。
