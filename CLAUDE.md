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

**普通账户持仓（10只）**:
ADI · ALB · ASML · COHR · ETN · GEV · GOOG · MPWR · NVDA · VRT

**宏观/ETF 观测（8只，不计算期权建议）**:
GLD · QQQ · SLV · ETHA · XBI · COIN · FPX · FLJH

**Watchlist 组一·高优先级（22只，每次必跑）**:
存储/内存: MRVL · MU · NVMI · ONTO · WDC · STX · SNDK
半导体设备: AEHR · KLAC · TSM · SMH
大型科技: ARM · AVGO · AMD
光纤/网络: LITE · CIEN · ANET
近期活跃: NBIS · PLTR · PWR · GS · GLW · CEG · FTAI

**Watchlist 组二·扩展（29只，盘后单独跑）**:
原有: BDRY · COPX · FRO · HEWJ · MP · NEE · VST · MSFT
能源/工业: LNG · TXN · XOM · DHT · TNK · DUK · RTX · AVAV
科技/云: SE · DOCN · EQIX · INTC · RKLB · SPCX
ETF/宏观: XMMO · IWM · BNO · UTES · REMX · GDX · USD

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
- [x] **三体制监测（正交）** — ①`macro_credit_gate`(原 macro_gate)六因子衰退闸门 ②`tail_fragility`(原 fragility_gate)脆弱性侧栏+崩盘性质诊断（Burry/1987型）③`dalio_inspired_bubble`(原 dalio_bubble)达利欧泡沫指标+货币收紧扳机（债务周期型;另 `internals_state` 原 market_breadth）。三者互不混票，见 `notes/1987型崩盘_vs_六因子闸门.md`

---

## 🚧 开发中模块

- [ ] **专项研究课题：市场判断 → 可用模型** (`research/`)
  - 章程与实施计划: `research/README.md`(双语,5 阶段)
  - 分析师分框架报告: `research/analyst_frameworks_report.md`(双语,A估值/B仓位/C债务)
  - 目标: 持续收集分析师/机构对金融·证券·经济·货币的判断 → 溯因 → 建模 → **回测 + 预测**
  - 优先级: **高**(三体制模型的延续与集成)

- [ ] **动态Watchlist管理** (`watchlist_manager.py`)
  - 规格详见: `modules/watchlist/spec.md`
  - 优先级: **最高**，其他模块依赖此模块
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

## 🧭 三组件扩展:观点层(analyst-panel)· 机制层(gate 预警)· 自我校准层(predict)

> 2026-08-09 立项。**原则:既有结构与流程不变**——三组件以**独立页面 + 独立数据文件**接入,不改动既有 tab/模块/workflow 逻辑。

- **治理文档**(主控在 `docs/`,按此优先级): `docs/工作计划书.md`(任务 C1-C16)→ `docs/analyst-panel-项目计划.md` → `docs/审计文章修订补编.md` → `docs/三组件系统宪法.md`;原始审计文章 `docs/审计文章-从分析师观点到金融体系重大变化预警系统.pdf`(按用户指令附件保留在 GitHub)
- **独立页面**: `docs/warning.html`(预警系统·机制层)/ `docs/panel.html`(分析师面板·观点层)/ `docs/review.html`(校准·监测·总结·反省·整合层)——从主页导航链接进入,不参与既有 tab 渲染流程
- **数据**: `data/analysts.jsonl` · `data/context_snapshots.jsonl` · `data/reviews.jsonl` · `data/registry.jsonl`(experiment registry;注意与既有 `research/registry.jsonl` 分析师档案是**两个不同文件**)。JSONL **只追加**,更正用新行+`supersedes`;schema 先行:改字段先改 `scripts/validate.py`(CI: `validate_data.yml`)
- **✅ 四条冲突已裁决**(用户 2026-08-09,全部执行):
  1. **模块已按宪法重命名**(冲突检查:7 个目标名无一重复):`macro_gate.py→macro_credit_gate.py`、`fragility_gate.py→tail_fragility.py`、`dalio_bubble.py→dalio_inspired_bubble.py`、`market_breadth.py→internals_state.py`;各 payload 增 `module`+`fidelity` 字段。**data.json 数据键不改**(macro_gate/fragility_gate/dalio_bubble/market_breadth 保留,历史连续性;宪法约束的是模块名)。未来名 grantham_two_sigma/valuation_state/passive_liquidity_mismatch 留给新模块
  2. **predict.py 已入仓库**(按宪法接口实现:add/resolve/list/stats + `--rationalized` 合理化单独统计,数据 `data/predictions.jsonl` 只追加+schema 校验;若本地/InvestOS 有历史版本,以仓库 schema 为准迁移合并)
  3. **审计 PDF 双录**:GitHub `docs/` 原件 + Drive `Analyst-Archive/system-design/`(目录树已建,设计文档归档副本已上传;PDF 二进制本体待 R2 管线或手动补,见 `docs/drive_index.md`)
  4. **briefs/ 每日自动入库已接**:`scripts/archive_brief.py`(只追加、幂等、失败不拖垮管线)+ daily_brief.yml 附加步骤;首条 `briefs/2026/08/2026-08-09.md`
- **Drive 双向链接索引**: `docs/drive_index.md`(folder/file ids,无孤儿文件)

## 分工（详见 AGENTS.md）

| 角色 | 工具 | 职责 |
|------|------|------|
| 策略设计 | Claude (claude.ai) | 分析逻辑、规格文档、数据解读 |
| 编码实现 | Claude Code | 写代码、调试、推送 GitHub |
| 文件管理 | Cowork | 本地文档更新、格式整理 |
