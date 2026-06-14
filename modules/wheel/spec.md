# Wheel Strategy 模块 — 功能规格 (spec.md)

**模块文件**: `wheel_strategy.py`
**创建日期**: 2026-06-13
**状态**: 待开发（见 status.md）

---

## 模块目标

每日从动态Watchlist中筛选Wheel Strategy候选标的，追踪现有Wheel仓位状态，生成操作建议，推送至企业微信。

---

## Wheel Strategy 简介

```
Step 1: 卖出 Cash-Secured Put
  → 股价上涨/持平: 保留全部premium ✅
  → 股价下跌破Strike: 以Strike价买入股票

Step 2: 持股后卖出 Covered Call
  → 股价上涨破Strike: 股票被Call走，获利了结 ✅
  → 股价下跌/持平: 保留premium，继续持股，重复Step 2

Step 3: 股票被Call走后回到Step 1，重新开始
```

---

## 功能一：候选标的筛选

### 数据来源
从 `watchlist_manager.get_full_watchlist()` 获取全部标的（三层合并）。

### 筛选条件（卖Put候选）

```python
PUT_CANDIDATE_RULES = {
    # 技术面
    "above_ma20": True,           # 价格在MA20上方
    "above_ma50": True,           # 价格在MA50上方
    "adx_min": 20,                # ADX > 20，有趋势
    "rsi_range": (35, 70),        # RSI不超买不超卖

    # 期权面
    "min_iv": 0.25,               # 隐含波动率 > 25%
    "min_price": 15,              # 股价 > $15
    "min_avg_volume": 500000,     # 日均成交量 > 50万

    # 加分项（国会信号）
    "congress_signal_bonus": True # 有国会买入信号额外标注
}
```

### Strike价格建议逻辑

```python
# 卖Put Strike = 当前价格的 90-95%（OTM，略低于市价）
# 到期日 = 最近的月度到期日，距今25-35天（Theta衰减最快区间）

def suggest_put_strike(current_price, iv, target_delta=0.25):
    """
    目标Delta约0.25（25%被行权概率）
    实际用价格的92%作为简化估算
    """
    strike = round(current_price * 0.92, 0)
    return strike
```

---

## 功能二：持仓追踪

### 数据来源
从 `watchlist.json` 的 `wheel_positions` 字段读取。

### 每个持仓每日计算

```python
POSITION_METRICS = {
    "current_price": "实时股价",
    "distance_to_strike": "距Strike价格百分比",
    "days_to_expiry": "距到期天数",
    "current_option_value": "当前期权市值（估算）",
    "unrealized_pnl": "未实现盈亏",
    "status": "安全/注意/危险"
}

# 状态判断
STATUS_RULES = {
    "安全": "distance_to_strike > 5%",
    "注意": "2% < distance_to_strike <= 5%",
    "危险": "distance_to_strike <= 2% 或 已破Strike"
}
```

### 操作建议逻辑

```python
# Short Put 建议
if status == "安全" and days_to_expiry > 7:
    advice = "持有，继续收Theta"
elif status == "注意":
    advice = "关注，考虑在到期前买回（50%利润可止盈）"
elif status == "危险":
    advice = "警告：接近被行权，考虑Roll Down or Roll Out"
elif days_to_expiry <= 5:
    advice = "即将到期，准备下一张或接收股票"

# Short Call 建议
if distance_above_strike <= 2%:
    advice = "注意：即将被Call走，确认是否愿意交割"
elif unrealized_pnl >= premium * 0.5:
    advice = "已达50%利润，可考虑买回锁定"
```

---

## 功能三：推送格式

```
🎡 Wheel Strategy 日报 2026-06-13

━━━ 📋 今日候选（卖Put） ━━━

1. NVDA  $120.50  ⭐国会信号
   建议Strike: $111 | 到期: 7/18 | IV: 42%
   预估Premium: ~$3.20/股（$320/张）
   技术面: MA20✅ MA50✅ ADX:31 RSI:58
   
2. AVGO  $185.20
   建议Strike: $170 | 到期: 7/18 | IV: 38%
   预估Premium: ~$4.50/股（$450/张）
   技术面: MA20✅ MA50✅ ADX:28 RSI:62

━━━ 📊 我的持仓 ━━━

[PUT] NVDA $115 到期7/18  剩14天
  当前价: $120.50 | 距Strike: +4.8% 🟢安全
  建议: 持有

[CALL] GS $520 到期7/18  剩14天
  当前价: $522.30 | 距Strike: +0.4% 🔴注意
  建议: 即将被Call走，确认是否接受交割

━━━ 💰 本月Wheel收益 ━━━
已收Premium: $1,240
已实现盈亏: +$860
```

---

## 用户仓位输入方式

用户通过修改 `watchlist.json` 的 `wheel_positions` 字段手动记录仓位，或者通过企业微信回复指令（后续版本实现）。

**v1.0 手动记录方式**（最简单）：
直接编辑 `docs/watchlist.json` 加入仓位信息。

---

## 技术实现要点

### Premium估算（无需期权API）

```python
# 用Black-Scholes简化公式估算，或直接用IV×价格×时间估算
# 不需要实时期权链，只需要IV（从yfinance获取）

import yfinance as yf

def get_iv(ticker):
    """从yfinance获取近月ATM隐含波动率"""
    t = yf.Ticker(ticker)
    try:
        # 获取最近到期日的期权链
        expiry = t.options[1]  # 第二个到期日（约30天）
        chain = t.option_chain(expiry)
        # 取ATM Put的IV
        puts = chain.puts
        atm_put = puts.iloc[(puts['strike'] - t.fast_info.last_price).abs().argsort()[:1]]
        return atm_put['impliedVolatility'].values[0]
    except:
        return 0.35  # 默认值
```

### 依赖库

无需新增（yfinance已有）。

---

## 开发阶段规划

| 版本 | 功能 | 优先级 |
|------|------|--------|
| v1.0 | 候选筛选 + 基础推送 | 🔴 高 |
| v1.1 | 持仓追踪 + 操作建议 | 🔴 高 |
| v1.2 | 月度收益统计 | 🟡 中 |
| v2.0 | 企业微信指令输入仓位 | 🟢 后续 |

---

## 开发依赖

**必须先完成**: `watchlist_manager.py`（v1.0）
**可并行**: `congress_tracker.py`
