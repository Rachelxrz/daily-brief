# 动态Watchlist管理模块 — 进度追踪 (status.md)

**最后更新**: 2026-06-13
**当前版本**: v0.0（未开始）
**负责角色**: Claude Code
**优先级**: 🔴 最高（其他模块依赖此模块）

---

## 待完成任务

### v1.0 基础功能
- [ ] 创建初始 `docs/watchlist.json`（含现有26只长期标的）
- [ ] 实现 `get_full_watchlist()` — 三层合并去重
- [ ] 实现 `add_congress_ticker()` — 加入国会信号标的
- [ ] 实现 `remove_expired_tickers()` — 90天过期清理
- [ ] 实现 `add_wheel_position()` — 记录Wheel仓位
- [ ] 实现 `update_wheel_position()` — 更新仓位状态
- [ ] 实现 `get_active_wheel_positions()` — 读取活跃仓位
- [ ] 本地测试

### v1.1
- [ ] 自动过期清理逻辑完善
- [ ] 价格跌破$10自动移除

---

## 完成记录

| 日期 | 版本 | 内容 | 操作者 |
|------|------|------|--------|
| — | — | — | — |

---

## 已知问题

（暂无）
