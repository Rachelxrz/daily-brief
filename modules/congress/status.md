国会交易信号模块 — 进度追踪 (status.md)
最后更新: 2026-06-13
当前版本: v0.0（未开始）
负责角色: Claude Code
---
当前状态
```
[ ] v1.0 基础功能
[ ] v1.1 信号评级与持仓对比
[ ] v1.2 AI 解读
```
---
待完成任务清单
v1.0 基础功能
[ ] 确认 Capitol Trades 数据结构（手动访问页面，确认 HTML/JSON 格式）
[ ] 实现 `fetch_recent_trades()` 抓取函数
[ ] 实现行业信息补全（yfinance `info['sector']`）
[ ] 实现 `delay_days` 计算
[ ] 实现 WxPusher 推送（复用现有推送函数）
[ ] 本地测试运行
[ ] 写入 docs/data.json
v1.1 信号评级与持仓对比
[ ] 实现信号强度评分逻辑（见 spec.md 层三）
[ ] 实现持仓对比逻辑（见 spec.md 层四）
[ ] 实现 MA20/MA50 联动确认（复用现有技术分析函数）
[ ] 优化推送格式（见 spec.md 层五）
v1.2 AI 解读
[ ] 调用 Claude API 生成中文信号解读
[ ] 集成到推送内容
GitHub Actions 集成
[ ] 在 `.github/workflows/` 中新增 congress-signal job
[ ] 设置运行时间：UTC 20:30（美东盘后 16:30）
---
技术备注
Capitol Trades 数据结构（待确认）
> Claude Code 开始时请先访问 https://www.capitoltrades.com/trades
> 检查是否有 JSON API 端点（通过 Network tab 或 robots.txt）
> 如果只有 HTML，使用 BeautifulSoup 解析
推送函数复用
> 参考 main.py 或 market_monitor.py 中已有的 `push_to_wxpusher()` 函数
> 直接 import 或复制，不要重写
MA20/MA50 联动
> 参考 market_monitor.py 中的 `analyze_watchlist()` 函数
> congress_tracker.py 调用时只需传入 ticker，复用逻辑
---
完成记录
日期	版本	完成内容	操作者
—	—	—	—
---
已知问题
> 遇到问题在此记录，方便下次继续
（暂无）
---
2026-06-13 更新记录
确认 Capitol Trades 无官方API
数据源调整为：
第一阶段：Senate Stock Watcher + House Stock Watcher（免费JSON）
第二阶段：Lambda Finance（$19/月，验证后升级）
spec.md 已更新
