# Daily Brief — 项目总纲 (CLAUDE.md)

> **每次新对话第一步：读这个文件，再读 AGENTS.md，然后开始工作。**
> 不需要问用户"项目是什么"——答案都在这里。

---

## 项目概述

自动化投资简报系统，每日通过 GitHub Actions 运行，结果推送至企业微信 + 发布到 GitHub Pages。

- **代码仓库**: `rachelxrz/daily-brief`（GitHub Pages: `rachelxrz.github.io/daily-brief`）
- **本地工作站**: PowerSpec AI300，Ubuntu，RTX Pro 6000 Blackwell（96GB VRAM），运行 vLLM + Qwen2.5-72B-Instruct
- **AI 分析**: Claude API（深度推理）+ 本地 Qwen（高频/敏感数据预处理）
- **推送渠道**: 企业微信（WxPusher + ServerChan）
- **语言**: 中英双语输出

---

## 当前架构

```
GitHub Actions (触发器)
    ├── main.py              → 每日新闻简报（北京时间 08:00）
    ├── market_monitor.py    → 市场结构监控（工作日 09:30 + 23:30）
    └── congress_tracker.py  → 国会交易信号 [🚧 开发中]

输出:
    ├── docs/data.json       → 网页数据
    ├── docs/index.html      → GitHub Pages 展示
    └── 企业微信推送         → 实时提醒
```

---

## 持仓与监控标的

**核心持仓**: GLD · WTI · QQQ · TLT

**Watchlist（26只）**:
ALB, ANET, AVGO, BDRY, CEG, CIEN, COHR, COPX, ETHA, FRO, GEV, GS,
HEWJ, LITE, MP, NEE, NVDA, PLTR, PWR, VRT, VST, MPWR, ADI, GOOG, NBIS, MPC

**板块 ETF 覆盖**: XLE(能源) · XLI(工业) · XLU(公用事业) · XLB(材料) · XLP(消费) · GLD(黄金) · COPX(铜)

---

## 技术指标体系

| 指标 | 参数 | 用途 |
|------|------|------|
| MA | 20/50/200日 | 趋势方向与强度 |
| ADX | 14日 | 趋势强度（>25强趋势，<20震荡） |
| RSI | 14日 | 动量/超买超卖 |
| 连续涨跌 | 3日 | 短期动量信号 |
| VaR/CVaR | 95%置信 | 风险量化 |
| 最大回撤 | 历史 | 风险基准 |

**Screener 规则（严格版）**: 价格>$100, 市值>$150亿, 日均量>30万, EPS>0.25, MA25/50/125正向排列
**Screener 规则（宽松版）**: 价格>$5, 市值>$20亿, 日均量>20万（用于黄金/铜等板块）

---

## 已完成模块

- [x] **模块 A** — 板块 ETF 轮动 Screener（7个板块，严格/宽松双模式）
- [x] **模块 B** — Watchlist 技术分析（MA20/50，连续涨跌，实时价格）
- [x] **市场结构监控** — 10个核心指标（GLD/WTI/QQQ/TLT/DXY），3日连续数据表
- [x] **AI 双语简报** — Claude API 生成中英文投资洞察，推送企业微信
- [x] **风险分析仪表板** — 每资产 VaR/CVaR/最大回撤/ADX/RSI，相关性矩阵

---

## 🚧 开发中模块

- [ ] **国会交易信号模块** (`congress_tracker.py`)
  - 规格详见: `modules/congress/spec.md`
  - 状态详见: `modules/congress/status.md`
  - 优先级: **高**，下一个要完成的模块

---

## 数据源

| 数据类型 | 来源 | 说明 |
|----------|------|------|
| 股价/技术指标 | yfinance | 免费，无需 API Key |
| AI 分析 | Claude API (`claude-sonnet-4-6`) | 需要 `ANTHROPIC_API_KEY` secret |
| 推送 | WxPusher + ServerChan | 需要对应 secret |
| 国会交易 | Capitol Trades / Unusual Whales | 见 congress spec |

---

## GitHub Secrets 清单

```
ANTHROPIC_API_KEY    → Claude API
WXPUSHER_TOKEN       → WxPusher 推送
WXPUSHER_UIDS        → 接收用户 ID（逗号分隔）
SERVERCHAN_KEY       → ServerChan 备用推送
```

---

## 开发规范

1. **语言**: Python 3.11，遵循现有代码风格
2. **依赖**: 新依赖加入 `requirements.txt`
3. **日志**: 写入 `logs/` 目录，GitHub Actions 自动上传
4. **推送格式**: 中英双语，emoji 分隔模块，关键数字加粗
5. **错误处理**: 每个模块独立 try/except，单模块失败不影响整体运行
6. **Git**: Actions bot 自动 commit，格式 `"模块名 YYYY-MM-DD"`

---

## 分工（详见 AGENTS.md）

| 角色 | 工具 | 职责 |
|------|------|------|
| 策略设计 | Claude (claude.ai) | 分析逻辑、规格文档、数据解读 |
| 编码实现 | Claude Code | 写代码、调试、推送 GitHub |
| 文件管理 | Cowork | 本地文档更新、格式整理 |
