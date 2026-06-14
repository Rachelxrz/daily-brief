# 动态Watchlist管理模块 — 功能规格 (spec.md)

**模块文件**: `watchlist_manager.py`
**创建日期**: 2026-06-13
**状态**: 待开发（见 status.md）

---

## 模块目标

维护一个动态的、分层的股票观察列表。国会交易信号自动触发标的加入/移除，所有其他模块从同一个 `docs/watchlist.json` 文件读取数据，保持全系统同步。

---

## Watchlist 三层结构

```
Layer 1: 核心持仓（core_holdings）
  → 手动维护，永不自动移除
  → GLD / WTI / QQQ / TLT

Layer 2: 长期观察（long_term）
  → 手动维护，人工判断进出
  → 现有26只 + 手动新增

Layer 3: 国会信号池（congress_signals）
  → 自动进出，由 congress_tracker.py 写入
  → 符合条件自动加入，90天无新信号自动移除
```

---

## 数据文件格式

**文件路径**: `docs/watchlist.json`

```json
{
  "last_updated": "2026-06-13",
  "core_holdings": [
    {"ticker": "GLD", "direction": "long", "weight": 0.30},
    {"ticker": "WTI", "direction": "long", "weight": 0.20},
    {"ticker": "QQQ", "direction": "long", "weight": 0.25},
    {"ticker": "TLT", "direction": "long", "weight": 0.20}
  ],
  "long_term": [
    "ALB","ANET","AVGO","BDRY","CEG","CIEN","COHR","COPX",
    "ETHA","FRO","GEV","GS","HEWJ","LITE","MP","NEE",
    "NVDA","PLTR","PWR","VRT","VST","MPWR","ADI","GOOG","NBIS","MPC"
  ],
  "congress_signals": [
    {
      "ticker": "GEV",
      "added_date": "2026-06-13",
      "expires": "2026-09-11",
      "reason": "Warren Davidson 期权买入",
      "members": ["Warren Davidson"],
      "signal_score": 5,
      "sector": "Industrials"
    }
  ],
  "wheel_positions": [
    {
      "ticker": "NVDA",
      "type": "short_put",
      "strike": 115,
      "expiry": "2026-07-18",
      "premium_received": 3.20,
      "opened_date": "2026-06-13",
      "contracts": 1,
      "status": "open"
    }
  ]
}
```

---

## 自动加入条件（congress_signals层）

congress_tracker.py 写入新标的时，必须同时满足：

```python
ENTRY_RULES = {
    "min_signal_score": 3,        # 中等信号以上
    "min_member_count": 1,        # 至少1名议员买入（强信号可放宽）
    "min_price": 15,              # 股价 > $15（期权流动性）
    "min_market_cap_b": 5,        # 市值 > $50亿
    "exclude_if_in_long_term": False,  # 已在long_term的也记录（避免重复分析）
}
```

强信号（5分）单人买入也可加入，中等信号（3-4分）需要验证市值和价格。

---

## 自动移除条件（congress_signals层）

```python
EXPIRY_RULES = {
    "max_days": 90,               # 90天无新信号自动移除
    "force_remove_if": [
        "ticker_delisted",        # 退市
        "price_below_10",         # 股价跌破$10
    ]
}
```

每次运行 `watchlist_manager.py` 时自动检查过期标的并清理。

---

## 核心函数

```python
def add_congress_ticker(ticker, reason, members, signal_score, sector):
    """从国会信号加入新标的"""
    pass

def remove_expired_tickers():
    """移除超过90天无新信号的标的"""
    pass

def get_full_watchlist():
    """返回三层合并的完整列表（去重）"""
    pass

def add_wheel_position(ticker, position_type, strike, expiry, premium, contracts):
    """记录新的Wheel仓位"""
    pass

def update_wheel_position(ticker, strike, expiry, status):
    """更新Wheel仓位状态"""
    pass

def get_active_wheel_positions():
    """返回当前所有活跃的Wheel仓位"""
    pass
```

---

## 与其他模块的关系

```
congress_tracker.py
    → 调用 add_congress_ticker()
    → 写入 watchlist.json

market_monitor.py
    → 调用 get_full_watchlist()
    → 读取所有标的做技术分析

wheel_strategy.py
    → 调用 get_full_watchlist() 筛选候选
    → 调用 add/update_wheel_position() 管理仓位
    → 读取 watchlist.json 中的 wheel_positions
```

---

## GitHub Actions 集成

不单独运行，由其他模块调用。无需新增 job。

---

## 开发优先级

此模块是基础设施，需要**最先完成**，其他模块依赖它。

| 版本 | 功能 | 优先级 |
|------|------|--------|
| v1.0 | 初始化 watchlist.json，基础读写函数 | 🔴 最高 |
| v1.1 | 自动过期清理 | 🔴 高 |
| v1.2 | Wheel仓位管理 | 🟡 中 |
