# 📈 Stock Screener — 部署说明

整合进 `rachelxrz.github.io/daily-brief` 项目的每日强势股筛选模块。

---

## 文件结构

```
daily-brief/
├── stock_screener.py              ← 主程序（放在根目录）
├── docs/
│   ├── stock_screener.html        ← 展示页面（放在 docs/ 下）
│   └── data/
│       └── stock_screener.json    ← 自动生成（不需要手动创建）
└── .github/
    └── workflows/
        └── stock_screener.yml     ← GitHub Actions 定时任务
```

---

## 部署步骤

### Step 1: 复制文件到你的 repo

```bash
# 在你的 daily-brief repo 根目录执行
cp stock_screener.py ./
cp stock_screener.html ./docs/
mkdir -p .github/workflows
cp stock_screener.yml .github/workflows/
```

### Step 2: 安装依赖（本地测试用）

```bash
pip install yfinance pandas requests pytz
```

### Step 3: 配置 GitHub Secrets

进入 repo → Settings → Secrets and variables → Actions → New repository secret

| Secret 名称 | 说明 | 示例 |
|---|---|---|
| `SERVERCHAN_KEY` | Server酱 SendKey | `SCTxxx...` |
| `WXPUSHER_TOKEN` | WxPusher App Token | `AT_xxx...` |
| `WXPUSHER_UIDS` | WxPusher 用户UID，多个用逗号分隔 | `UID_xxx,UID_yyy` |

> ⚠️ 如果不需要某个推送渠道，对应 Secret 留空即可，程序会自动跳过。

### Step 4: 在 daily-brief 首页加入入口链接

在你的 `docs/index.html` 中加一行：

```html
<a href="./stock_screener.html">📈 每日强势股</a>
```

### Step 5: 提交并推送

```bash
git add .
git commit -m "✨ Add stock screener module"
git push
```

---

## 运行时间

- **自动运行**: 每个交易日（周一至周五）美东时间 4:30PM（UTC 21:30）
- **手动触发**: GitHub repo → Actions → "Daily Stock Screener" → Run workflow

---

## 筛选逻辑

```
1. 获取 XLE/XLI/XLU/XLB/XLP 今日涨幅
2. 选出今日涨幅前3的板块（且为正涨）
3. 对板块内所有候选股检查：
   ✅ 股价 ≥ $100
   ✅ 市值 ≥ $15B
   ✅ 日均成交量 ≥ 300,000
   ✅ EPS ≥ 0.25
   ✅ 收盘价高于 MA25（至少+0.1%）
   ✅ 收盘价高于 MA50（至少+0.2%）
   ✅ 收盘价高于 MA125（至少+0.7%）
4. 按今日涨幅排序，输出 TOP 3
```

---

## 自定义

修改 `stock_screener.py` 顶部的配置区：

```python
SCREENER_CONFIG = {
    "min_price":        100,    # 改这里调整最低股价
    "min_market_cap_b": 15,     # 改这里调整最低市值(B)
    "top_n":            3,      # 改这里调整输出数量
    ...
}
```

添加/删除候选股只需编辑 `SECTOR_STOCKS` 字典。
