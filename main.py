#!/usr/bin/env python3
"""
每日智识简报 - 主运行脚本
Daily Intelligence Brief - Main Runner

用法:
  python main.py              # 立即执行一次（抓取+推送）
  python main.py --test       # 测试推送（不抓取，用缓存数据）
  python main.py --schedule   # 定时模式（保持运行，每天定时推送）
  python main.py --dry-run    # 仅抓取，不推送，查看结果
"""

import sys
import json
import logging
import os
import time
import schedule
from datetime import datetime, timezone, timedelta
from pathlib import Path

from scraper     import scrape_all
from pusher      import push_all
from config      import Config
from save_to_web import save_news

# ─── 日志设置 ──────────────────────────────────────────────
os.makedirs(Config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            f'{Config.LOG_DIR}/main_{datetime.now().strftime("%Y%m%d")}.log',
            encoding='utf-8'
        )
    ]
)
log = logging.getLogger(__name__)


def get_cache_path() -> str:
    today = datetime.now().strftime("%Y%m%d")
    return f"{Config.LOG_DIR}/news_{today}.json"


def load_cache() -> dict | None:
    path = get_cache_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log.info(f"📦 已加载缓存: {path}")
        return data
    return None


def save_cache(data: dict):
    path = get_cache_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"💾 数据已缓存: {path}")


def cleanup_old_logs():
    """清理超过 LOG_KEEP 天的旧日志文件。"""
    log_dir = Path(Config.LOG_DIR)
    cutoff  = datetime.now().timestamp() - Config.LOG_KEEP * 86400
    
    for f in log_dir.glob("*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            log.info(f"🗑  已清理旧缓存: {f.name}")
    
    for f in log_dir.glob("*.log"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            log.info(f"🗑  已清理旧日志: {f.name}")


def run_daily_job(dry_run: bool = False):
    """执行每日抓取和推送任务。"""
    tz_cst = timezone(timedelta(hours=8))
    start  = datetime.now(tz_cst)
    
    log.info("=" * 60)
    log.info(f"🚀 每日智识简报任务启动")
    log.info(f"   时间: {start.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log.info("=" * 60)
    
    # Step 1: 抓取新闻
    log.info("\n📡 Step 1/3: 抓取新闻...")
    news_data = scrape_all(items_per_category=Config.ITEMS_PER_CATEGORY)
    
    total = sum(len(v) for v in news_data.values())
    log.info(f"   ✅ 共抓取 {total} 条新闻")
    for cat, items in news_data.items():
        log.info(f"      {cat}: {len(items)} 条")
    
    # Step 2: 缓存数据
    log.info("\n💾 Step 2/3: 缓存数据...")
    save_cache(news_data)
    
    if dry_run:
        log.info("\n🔍 [Dry Run 模式] 跳过推送，数据预览:")
        for cat, items in news_data.items():
            log.info(f"\n--- {cat.upper()} ---")
            for i, item in enumerate(items, 1):
                log.info(f"  {i:02d}. [{item['source']}] {item['title'][:80]}")
        return news_data
    
    # Step 3: 推送微信
    log.info("\n📲 Step 3/3: 推送微信...")
    results = push_all(news_data)

    # 保存到网页（传入 news_data dict，save_to_web 自动生成英文版+翻译中文版）
    try:
        save_news(news_data=news_data)
        log.info("🌐 新闻数据已保存到网页")
    except Exception as e:
        log.warning("⚠️  网页数据保存失败: " + str(e))
    # 汇报结果
    end      = datetime.now(tz_cst)
    duration = (end - start).total_seconds()
    
    log.info("\n" + "=" * 60)
    log.info("📊 任务完成报告")
    log.info(f"   耗时: {duration:.1f}s")
    log.info(f"   新闻: {total} 条")
    
    if results:
        for channel, ok in results.items():
            status = "✅ 成功" if ok else "❌ 失败"
            log.info(f"   {channel}: {status}")
    else:
        log.warning("   ⚠️  未配置任何推送渠道！")
        log.warning("   请编辑 config.py 填入 Webhook 或 Token")
    
    log.info("=" * 60)
    
    # 清理旧文件
    cleanup_old_logs()
    
    return news_data


def run_schedule_mode():
    """定时模式：保持进程运行，每天指定时间自动推送。"""
    push_time = f"{Config.PUSH_HOUR:02d}:{Config.PUSH_MINUTE:02d}"
    
    log.info("=" * 60)
    log.info(f"⏰ 定时模式启动")
    log.info(f"   每天 {push_time} (北京时间) 自动推送")
    log.info(f"   按 Ctrl+C 停止")
    log.info("=" * 60)
    
    schedule.every().day.at(push_time).do(run_daily_job)
    
    # 计算下次执行时间
    next_run = schedule.next_run()
    log.info(f"   下次执行: {next_run}")
    
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    args = sys.argv[1:]
    
    if "--schedule" in args:
        run_schedule_mode()
    elif "--test" in args:
        # 使用缓存数据测试推送
        data = load_cache()
        if data:
            push_all(data)
        else:
            log.error("没有找到今日缓存，请先运行 python main.py 抓取数据")
    elif "--dry-run" in args:
        run_daily_job(dry_run=True)
    else:
        run_daily_job(dry_run=False)
