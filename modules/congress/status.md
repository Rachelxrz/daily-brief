国会交易信号模块 — 进度追踪 (status.md)
最后更新: 2026-06-13
当前版本: v1.1（v1.0 + v1.1 合并实装）
负责角色: Claude Code
---
当前状态
```
[x] v1.0 基础功能
[x] v1.1 信号评级与持仓对比
[ ] v1.2 AI 解读（第二周，待开发）
```
---
已完成任务清单
v1.0 + v1.1（合并实装，2026-06-13）
[x] 确认数据源：House Stock Watcher 原始端点已失效（S3 403），改用社区镜像
      TattooedHead/house-stock-watcher-data（截至 2026-06-13 持续更新）
[x] 实现 `fetch_house_trades()` — 从 GitHub raw JSON 抓取，23k+ 条记录
[x] 实现 `fetch_senate_trades()` — 暂为 stub（见「已知问题」）
[x] 层一：match_tracked_member() 精确+姓名首字母回退匹配
[x] 层二：delay_days 计算、MIN_TRADE_SIZE($10K) 过滤、RECENT_DAYS(7天) 窗口
[x] 行业信息补全：get_sector() 调用 yfinance.info，带模块级缓存
[x] 层三：score_trade() 完整评分（基础分+加分项+减分项+delay>60强制降级）
[x] 层四：compare_with_holdings() 全四种对比逻辑（持仓/Watchlist/行业/新标的）
[x] MA20/MA50：get_ma_signal() 复用 stock_screener.get_hist()
[x] 层五：格式化推送消息（spec 样式，中英混排）
[x] 层五：build_sector_breakdown() + render_sector_bars()
[x] 去重机制：congress_seen.json，保留14天，防止重复推送
[x] save_congress() 写入 docs/data.json（新增至 save_to_web.py）
[x] requirements.txt 新增 yfinance>=0.2.36, pytz>=2024.1
[x] GitHub Actions：congress-signal job，cron UTC 20:30 工作日
[x] workflow_dispatch 新增 congress_only 选项
[x] 本地 dry-run 验证：抓取 23531 条 House 记录，匹配逻辑正常，参议院 stub 正常

待完成
v1.2 AI 解读（第二周）
[ ] 调用 Claude API 生成中文信号解读文字
[ ] 集成到推送内容（追加到推送消息末尾）
---
技术备注
推送函数
> 从 market_monitor 导入：push_serverchan, push_wecom, push_wxpusher
> 不推送时（无新信号）仍写入 docs/data.json 保持网页数据最新
格式判断
> 推送格式按 spec.md 层五样式（中英混排），优先于 CLAUDE.md 通用双语格式
> 该判断记录于此，避免歧义
"信号强度 X/5" 格式
> spec 示例中 "5/5" 仅为样例，实际输出为 "X 分" 以反映真实得分
> 未来可恢复 X/5 格式（score 上限为 7：3+1+1+1）
---
完成记录
日期          版本   完成内容                               操作者
2026-06-13   v1.1   v1.0+v1.1合并实装，全5层逻辑          Claude Code
---
已知问题
1. 参议院数据源缺失
   原因: Senate Stock Watcher (senatestockwatcher.com) 域名不存在，
         S3 端点 senate-stock-watcher-data.s3-us-west-2.amazonaws.com 返回 403。
         GitHub 上的 timothycarambat/senate-stock-watcher-data 最后更新于 2021-03-16，
         已废弃。目前无可用免费参议院数据源。
   影响: Alex Padilla（参议员）、Rick Scott（参议员）的交易无法抓取。
         实际有效覆盖 = TRACKED_MEMBERS 中的 8 名众议员。
   解决方案（待决策）：
     a) 升级至 Lambda Finance ($19/月)，覆盖参众两院
     b) 自建 Senate 爬虫（efts.senate.gov/public 有官方 JSON API，待验证）
     c) 维持现状，在推送消息中标注"参议院数据暂缺"

2. TRACKED_MEMBERS 名单静态
   当前硬编码 2025 年数据，应每年 1 月更新一次（参考最新年度排名）。

3. 本周(2026-06-07 至今)零信号
   属正常现象：验证数据显示 Nancy Pelosi 最近披露为 2026-01-16，
   Dwight Evans 为 2026-05-14（$8K，低于 MIN_TRADE_SIZE）。
   模块逻辑正确，等待下次真实信号触发。
