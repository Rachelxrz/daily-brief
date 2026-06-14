国会交易信号模块 — 功能规格 (spec.md)
模块文件: `congress_tracker.py`
创建日期: 2026-06-13
最后更新: 2026-06-13（数据源修订）
状态: 待开发（见 status.md）
---
模块目标
追踪表现最佳的美国国会议员股票交易，与持仓对比后生成投资信号，每日并入 daily-brief 推送。
---
数据源
第一阶段（免费，立即可用）
Senate Stock Watcher — senatestockwatcher.com
免费 JSON API，无需注册
覆盖参议院所有披露
端点示例：`https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json`
House Stock Watcher — housestockwatcher.com
免费 JSON API，无需注册
覆盖众议院所有披露
端点示例：`https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json`
两者合并 = 参众两院全覆盖，零成本验证整个模块逻辑。
第二阶段（推荐升级，$19/月）
Lambda Finance — lambdafin.com
统一 REST API，参众两院单一端点
`/api/congressional/recent` 返回标准化数据
字段：政党、股票代码、交易类型、金额区间、申报日期
支持按政党/州/代码/日期过滤
数据在官方 STOCK Act 申报后数小时内更新
免费 tier：50次/月（够测试用）
不推荐
Capitol Trades 直接爬取 — 无官方 API，网页结构随时可能变化，维护成本高，不适合生产环境。
---
功能规格
层一：议员筛选
筛选逻辑（按优先级）：
年度回报排名 — 取当年 Top 15 议员
过滤条件:
排除"声明由基金经理全权委托"的议员（信号失真）
排除交易量极小（全年 <5 笔）的议员
附加信息:
委员会背景（金融/能源/国防/科技/医疗）
党派（民主党/共和党）
职位（参议员/众议员）
硬编码 Top 关注名单（基于 2025 年数据，每年 1 月更新）:
```python
TRACKED_MEMBERS = [
    {"name": "Warren Davidson",  "party": "R", "chamber": "House", "committee": "Financial Services"},
    {"name": "Donald Norcross",  "party": "D", "chamber": "House", "committee": "Armed Services"},
    {"name": "Terri Sewell",     "party": "D", "chamber": "House", "committee": "Ways and Means"},
    {"name": "Bryan Steil",      "party": "R", "chamber": "House", "committee": "Financial Services"},
    {"name": "Alex Padilla",     "party": "D", "chamber": "Senate","committee": "Judiciary"},
    {"name": "Rick Scott",       "party": "R", "chamber": "Senate","committee": "Commerce"},
    {"name": "Nancy Pelosi",     "party": "D", "chamber": "House", "committee": "N/A"},  # 长期跟踪
    {"name": "Michael Guest",    "party": "R", "chamber": "House", "committee": "Ethics"},
    {"name": "Tom McClintock",   "party": "R", "chamber": "House", "committee": "Budget"},
    {"name": "Dwight Evans",     "party": "D", "chamber": "House", "committee": "Ways and Means"},
]
```
---
层二：交易解析
每条交易记录需提取：
字段	说明
`member`	议员姓名
`ticker`	股票代码
`asset_type`	Stock / Call Option / Put Option / ETF
`transaction`	Buy / Sell / Exercise
`trade_date`	交易发生日期
`disclosure_date`	披露日期
`delay_days`	披露延迟天数（disclosure - trade）
`size_range`	金额区间（如 $15K–$50K）
`sector`	所属行业（用 yfinance 获取）
过滤规则:
忽略 `size_range` < $10,000 的交易（噪音）
`delay_days` > 60 时，信号强度降级为"弱"
---
层三：信号强度评级
```
信号强度 = 基础分 + 加分项 - 减分项

基础分:
  期权买入   = 3分（最强信号，有明确时间窗口）
  股票买入   = 2分
  股票卖出   = 1分（卖出原因复杂，参考价值较低）

加分项:
  委员会与行业匹配  +1分（如金融委员会买银行股）
  多名议员同向买入  +1分
  交易规模 >$50K   +1分

减分项:
  delay_days > 45  -1分
  delay_days > 60  -2分
  已知委托基金经理  -3分（直接过滤）

最终评级:
  5分+ → 🔴 强信号
  3-4分 → 🟡 中等信号
  1-2分 → 🟢 弱信号/观察
```
---
层四：与持仓对比
持仓配置（硬编码，定期手动更新）:
```python
MY_HOLDINGS = {
    "GLD": {"weight": 0.30, "direction": "long"},
    "WTI": {"weight": 0.20, "direction": "long"},
    "QQQ": {"weight": 0.25, "direction": "long"},
    "TLT": {"weight": 0.20, "direction": "long"},
}

MY_WATCHLIST = [
    "ALB","ANET","AVGO","BDRY","CEG","CIEN","COHR","COPX",
    "ETHA","FRO","GEV","GS","HEWJ","LITE","MP","NEE",
    "NVDA","PLTR","PWR","VRT","VST","MPWR","ADI","GOOG","NBIS","MPC"
]
```
对比逻辑:
```
A. 直接重叠（议员交易 = 我的持仓）
   → 方向一致：✅ 持仓确认信号
   → 方向相反：⚠️ 预警，考虑减仓

B. Watchlist 重叠（议员交易 = 我的 watchlist）
   → 优先级提升，结合 MA20/MA50 决定是否建仓

C. 行业关联（议员交易的行业 = 我持仓的行业 ETF）
   → 例如：议员买能源股 → WTI 相关提示

D. 全新标的（我没有的）
   → 列为"候选观察"，不直接推荐买入
   → 需结合技术指标二次确认
```
---
层五：输出格式
企业微信推送（每个交易日，并入 daily-brief）:
```
🏛 国会交易信号 2026-06-13

🔴 强信号
  Warren Davidson (R-金融服务委)
  买入 GEV 期权 · $15K-50K · 交易延迟8天
  行业：工业/电力设备
  ⚡ 与您 Watchlist 重叠 | MA50向上 ✅
  信号强度：5/5

🟡 中等信号
  Nancy Pelosi (D)
  买入 AVGO 股票 · $50K-100K · 交易延迟21天
  行业：半导体
  📌 Watchlist 标的 | 建议关注突破信号

📊 本周国会买入最多行业
  半导体 ████████ 42%
  能源   ████     18%
  工业   ███      15%

⚠️ 与您持仓方向相反的交易
  无
```
JSON 存储（写入 docs/data.json，供网页展示）:
```json
{
  "congress_signals": {
    "date": "2026-06-13",
    "strong": [...],
    "medium": [...],
    "watch": [...],
    "sector_breakdown": {...}
  }
}
```
---
技术实现要点
数据抓取（第一阶段）
```python
import requests

# 参议院数据
SENATE_URL = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"

# 众议院数据
HOUSE_URL = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"

def fetch_senate_trades():
    resp = requests.get(SENATE_URL, timeout=30)
    return resp.json()

def fetch_house_trades():
    resp = requests.get(HOUSE_URL, timeout=30)
    return resp.json()
```
数据抓取（第二阶段，Lambda Finance）
```python
LAMBDA_API = "https://www.lambdafin.com/api/congressional/recent"
LAMBDA_KEY = os.environ.get("LAMBDA_API_KEY", "")

def fetch_congress_trades_lambda(days=7):
    headers = {"Authorization": f"Bearer {LAMBDA_KEY}"}
    params = {"days": days}
    resp = requests.get(LAMBDA_API, headers=headers, params=params, timeout=30)
    return resp.json()
```
依赖库
在 `requirements.txt` 中新增（第一阶段无需新增，requests 已有）：
```
# 第一阶段：无需新增
# 第二阶段：无需新增（requests 已有）
```
GitHub Actions 集成
在现有 workflow 中新增 job（工作日，美东盘后 16:30 = UTC 20:30）：
```yaml
congress-signal:
  name: 🏛 国会交易信号
  runs-on: ubuntu-latest
  timeout-minutes: 10
  if: |
    (github.event_name == 'schedule' && github.event.schedule == '30 20 * * 1-5') ||
    (github.event_name == 'workflow_dispatch' && (github.event.inputs.job_type == 'both' || github.event.inputs.job_type == 'congress_only'))
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
        cache: 'pip'
    - run: pip install -r requirements.txt
    - run: python congress_tracker.py
      env:
        ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        WXPUSHER_TOKEN: ${{ secrets.WXPUSHER_TOKEN }}
        WXPUSHER_UIDS: ${{ secrets.WXPUSHER_UIDS }}
        LAMBDA_API_KEY: ${{ secrets.LAMBDA_API_KEY }}  # 第二阶段启用
```
---
开发阶段规划
版本	数据源	功能	优先级
v1.0	Senate + House Stock Watcher（免费）	基础抓取 + 推送	🔴 立即
v1.1	同上	信号强度评级 + 持仓对比	🔴 立即
v1.2	同上	Claude API 生成中文解读	🟡 第二周
v2.0	Lambda Finance（$19/月）	升级数据源，提升稳定性	🟢 验证后
---
已知限制
披露延迟: 最长 90 天，务必结合技术指标确认
数据准确性: 各平台数据存在差异，以官方披露为准
法律声明: 本系统仅用于信息参考，不构成投资建议
