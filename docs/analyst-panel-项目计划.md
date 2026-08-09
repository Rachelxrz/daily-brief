# Analyst Panel — 分析师观点档案与校准系统 项目计划

版本：v0.2（2026-08-09，已补充：复盘规范与储存、面板人选确认、更新时间表）
所属仓库：rachelxrz/daily-brief（扩展）+ Google Drive（PDF 归档）

---

## 一、项目目标

**核心目标**：建立一个带环境快照的分析师判断档案，长期积累后回答三个问题：

1. **谁值得信**：各分析师在什么环境下、哪类判断上系统性地对或错（分析师校准）
2. **我值得信吗**：我基于他们的观点综合出的判断，命中率如何、在哪里被合理化污染（自我校准，与 predict.py 打通）
3. **历史可回放**：任意时点回看"当时的人在当时的环境下为什么这么想"，用于复盘研究和形成报告

**非目标**（明确排除，防止范围膨胀）：

- 不做实时行情系统 —— 环境快照按周/按事件粒度即可
- 不做全网研报爬虫 —— 只追踪确认的 12-18 位面板分析师
- 不追求预测市场 —— 目标价本身不重要，重要的是论断、前提和验证结果

---

## 二、系统架构

```
GitHub (rachelxrz/daily-brief)              Google Drive
├── briefs/YYYY/MM/*.md      每日简报长存    Analyst-Archive/
├── data/                                    ├── macro/
│   ├── analysts.jsonl       结构化论断      ├── strategy/
│   ├── context_snapshots.jsonl 环境快照     ├── energy/
│   └── reviews.jsonl        复盘结果        ├── ai-infra/
├── scripts/                 采集/查询/复盘   └── fx-gold/
└── .github/workflows/       自动化任务          └── *.pdf（原始研报）
```

**分工原则**：GitHub 存文本（简报、JSONL、代码），Drive 存二进制（PDF 原文），两边通过 `drive_file_id` 关联。Drive 目录保持私有（卖方研报有合规限制）。

### 数据 Schema

**analysts.jsonl** — 每条论断一行：

```json
{
  "id": "20260730-feroli-01",
  "analyst": "Feroli", "firm": "JPM", "layer": "macro",
  "date": "2026-07-30", "snapshot_id": "2026-W31",
  "claim": "Fed首次加息提前至2026年12月",
  "premise": "新主席抗通胀可信度不足",
  "falsifiable_by": "2026-12-16",
  "tags": ["fed", "rates"],
  "source_url": "...",
  "drive_file_id": "", "drive_path": "",
  "status": "open"
}
```

**context_snapshots.jsonl** — 每周/每事件一条，被多条论断共享：

```json
{
  "snapshot_id": "2026-W31", "date": "2026-08-01",
  "macro": {"fed_rate": "3.50-3.75%", "core_pce": "", "cpi_yoy": ""},
  "markets": {"spx": 0, "brent": 0, "gold": 0, "dxy": 0, "us10y": 0},
  "geopolitics": ["..."],
  "narrative": "当周市场主流叙事（从每日简报蒸馏）"
}
```

**reviews.jsonl** — 论断到期后的复盘。复盘内容明确为七个必填字段：

```json
{
  "claim_id": "20260730-feroli-01",
  "review_date": "2026-12-17",
  "outcome": "hit | miss | partial，附实际结果数字",
  "error_type": "input（数据没料到）| framework（逻辑本身错）| n/a",
  "timing": "leading（修正领先于事实）| lagging（事实明朗后才改口）| n/a",
  "missed_factors": "分析师当初缺失了什么变量",
  "key_references": "事后证明关键的参考/数据",
  "my_action": "我当时采纳/拒绝该论据 + 关联的 predict.py 预测 ID 及其结果",
  "lesson": "一句话结论，作为该分析师档案权重调整的依据"
}
```

**复盘时点分三级**：
- 单条复盘：论断到达 `falsifiable_by` 时触发（Actions 每日检查，进提示行）
- 季度批量复盘：每季度末汇总本季所有已验证论断，生成季度复盘报告
- 半年面板评审：基于累计 reviews 调整分析师权重、轮换面板

**复盘的储存位置与保存期限**：
- reviews.jsonl 与其他数据同仓库，存于 `data/`，随 Git 永久保存（含全部历史版本）
- 季度/半年复盘报告存 `briefs/reviews/YYYY-QN.md`，同样永久保存
- 保存期限：**无限期**。全部为文本，体积可忽略；Git 历史本身即审计轨迹，任何一次修改都可追溯
- 备份：每年 1 月由 Actions 自动打包上一年度全部数据（briefs + data + reviews）为 zip 存入 Drive `Analyst-Archive/backup/`，实现 GitHub 与 Google 双供应商冗余

### 分析师面板（初始 12-15 人，半年轮换一次）

| 板块 | 确认人选 | 定位 |
|---|---|---|
| 宏观 | Feroli (JPM)、Gapen (MS)、Porcelli (富国，反向锚) | 央行反应函数三视角：鹰派修正 / 温和暂停 / 坚持不降 |
| 策略 | Wilson (MS)、Kostin (GS) | 盈利修正广度模型 vs 事实上的共识锚 |
| 能源 | Struyven 团队 (GS)、EIA（非卖方基准） | 供需平衡表 + 官方基准对照 |
| AI 与基建 | ① Morgan Stanley 半导体团队（Joseph Moore 等，覆盖 AI 资本开支周期与封装/测试/存储链）② 高盛 Ronald Keung 团队（中国 AI 模型与应用层）③ 硬数据基准：四大云厂商季度资本开支 + TSMC 月度营收 + SIA 半导体月度销售（相当于本板块的"EIA"） | 基建层为主、应用层为辅；以可核查的 capex 硬数据为锚 |
| 货币与黄金 | ① 高盛贵金属：Lina Thomas / Samantha Dart（央行购金 + ETF 资金流框架）② JPM 大宗商品主管 Natasha Kaneva ③ UBS 贵金属团队（相对保守锚）；DXY 不单设人，由宏观层利差逻辑推导 + 月度记录 | 金价论断反向检验宏观框架；高盛 2025-26 连续低估金价的修正记录本身就是第一批复盘素材 |

（注：AI 板块如需数据中心租赁层面的渠道调研数据，可后续补充 TD Cowen 数据中心团队一类的专项来源，Phase 2 再定。）

### 分析师更新时间表（采集日历，写入 Actions cron）

| 板块 | 定期更新 | 事件触发 |
|---|---|---|
| 宏观 | 每月：CPI（月中）、非农（首个周五）当日快评；每季度展望 | FOMC 一年 8 次，会前预览 + 会后 24h 点评必采 |
| 策略 | 每周一：Wilson 周报；11-12 月年度展望；5-6 月中期修正 | 目标价临时调整（市场大幅偏离时） |
| 能源 | EIA 周度库存（周三）；OPEC 月报（月中）；EIA STEO（月初） | 地缘事件（如霍尔木兹）期间高盛可能双周改预测 |
| AI 与基建 | 财报季（1/4/7/10 月）：四大云厂商 capex 指引 + NVDA/TSMC 财报；TSMC 月度营收（每月 10 日前后）；SIA 月度数据 | 大型发布会、重大订单/出口管制变化 |
| 货币与黄金 | WGC 央行购金季度报告；各行金价预测通常随重大资金流数据按月/按事件修正 | 央行政策转向、地缘避险事件 |

**采集原则**：每次采集记录的是"新论断或修正"，分析师重复旧观点不入库；修正必须记录修正前后的值和理由（timing 字段的判断依据）。

---

## 三、实施步骤

### Phase 1 — 地基（第 1 周）

1. Drive 建 `Analyst-Archive/` 五个板块目录，定文件命名规范：`日期_机构_分析师_主题.pdf`
2. daily-brief 仓库加 `briefs/`、`data/` 目录；Actions 加一步：每日简报生成后自动 commit 到 `briefs/YYYY/MM/`
3. 三个 JSONL 建空文件 + schema 校验脚本（`scripts/validate.py`）
4. 手工录入第一批论断（当前已知的 Feroli / Wilson / Struyven 案例），跑通完整链路

**验收**：一条论断从"PDF 上传 Drive → JSONL 记录 → 能被查询命中"全程走通。

### Phase 2 — 采集自动化（第 2-3 周）

5. 采集日历写成 Actions cron：FOMC 前后、CPI/非农日、OPEC 月报、EIA 周报、财报季、策略周报（周一）
6. PDF 入库辅助：脚本读新上传的 PDF → Claude API 提取论断/前提/验证日期草稿 → 人工确认后写入 JSONL
7. 每周环境快照自动化：Actions 读本周 7 天简报 → 蒸馏出 snapshot（关键数据 + narrative）→ 写入 context_snapshots.jsonl

**验收**：一周内新增论断无需手写 JSON，只需确认草稿。

### Phase 3 — 展示与检索（第 4-5 周）

8. 推送/网页三层显示：核心行（本周新论断）、提示行（规则自动生成：临近验证期限 / 分析师改口 / 层间新矛盾）、其余折叠
9. 查询 CLI：`query --analyst X --tag Y --since DATE`，命中后返回论断 + 关联 snapshot + Drive PDF 链接
10. 深度检索：结构化查询走 JSONL（90% 场景），需要进报告内文时走 Drive API + Claude API

**验收**：能回答"回放 2026 年 4 月油价冲击时各层分析师的反应"这类查询。

### Phase 4 — 复盘闭环（持续运行）

11. 到期触发：Actions 每日检查 `falsifiable_by`，到期论断进入提示行待复盘
12. 复盘写入 reviews.jsonl：方向对错、输入错还是框架错、领先还是滞后、分析师当初缺失了什么
13. 与 predict.py 打通：我基于面板综合形成的判断照常走 predict.py（含 --rationalized 追踪），复盘时对照"我采纳/拒绝了谁的论据"
14. 半年一次面板评审：框架错的降权或剔除，补新人；生成一份"分析师校准报告"

**验收**：第一个完整的"论断 → 到期 → 复盘 → 校准档案更新"循环跑完。

---

## 四、关键设计决策（供评审）

1. **环境快照独立成表**而不是嵌在每条论断里 —— 多条论断共享一份快照，几年后可做"哪类环境下谁失灵"的横截面研究
2. **premise 字段是灵魂** —— 前提比结论更早暴露对错（Wilson 8000 点的前提是"再降息两次"）
3. **narrative 必须当时写** —— 数字事后能查，市场情绪查不回来；由每日简报自动蒸馏，零人工成本
4. **error_type 区分 input/framework** —— 数据没料到可以原谅，逻辑本身错要降权
5. **只存提取物 + 链接进 Git，PDF 进 Drive** —— 控制仓库体积，文本存 50 年 < 500MB

---

## 五、开放问题（待你决定）

- ~~AI 与基建、货币与黄金板块人选~~ —— 已确认（见面板表）
- ~~复盘内容与储存~~ —— 已明确（见 reviews 规范）
- 提示行的触发规则阈值（如"临近验证期限"提前几天提示，建议默认 7 天）
- 网页展示是复用现有推送渠道（WxPusher/ServerChan）还是加一个静态页面（GitHub Pages 读 JSONL 渲染）
