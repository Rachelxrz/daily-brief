#!/usr/bin/env python3
"""
配置文件 - 填入你的密钥和推送设置
Configuration File

⚠️  重要: 不要将此文件提交到 Git！
    在 .gitignore 中添加: config.py
"""

import os

class Config:
    # ─── 推送方式1: 企业微信群机器人 Webhook（推荐）───────────────
    # 步骤: 企业微信群 → 右上角 ··· → 群机器人 → 添加 → 复制Webhook地址
    # 格式: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
    WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL", "")
    # 示例: WECOM_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key-here"

    # ─── 推送方式2: WxPusher（推送到个人微信）────────────────────
    # 步骤: 访问 https://wxpusher.zjiecode.com → 注册 → 创建应用 → 获取Token
    #       然后用微信扫码关注公众号获取 UID
    WXPUSHER_APP_TOKEN = os.getenv("WXPUSHER_APP_TOKEN", "")
    WXPUSHER_UIDS      = os.getenv("WXPUSHER_UIDS", "").split(",") if os.getenv("WXPUSHER_UIDS") else []
    # 示例:
    # WXPUSHER_APP_TOKEN = "AT_xxxxxxxxxxxxxxxxxxxxxxxx"
    # WXPUSHER_UIDS      = ["UID_xxxxxxxxxxxxxxxx"]

    # ─── 推送方式3: Server酱（最简单，推送到个人微信）────────────
    # 步骤: 访问 https://sct.ftqq.com → 微信扫码登录 → 复制SendKey
    SERVERCHAN_SENDKEY = os.getenv("SERVERCHAN_SENDKEY", "")
    # 示例: SERVERCHAN_SENDKEY = "SCT123456Txxxxxxxxxxxxxxxxxxxxxxxx"

    # ─── 推送时间设置 ─────────────────────────────────────────
    PUSH_HOUR   = int(os.getenv("PUSH_HOUR", "8"))    # 推送小时 (0-23, 北京时间)
    PUSH_MINUTE = int(os.getenv("PUSH_MINUTE", "0"))  # 推送分钟 (0-59)
    TIMEZONE    = "Asia/Shanghai"

    # ─── 抓取设置 ─────────────────────────────────────────────
    ITEMS_PER_CATEGORY = 10   # 每分类推送条数
    REQUEST_TIMEOUT    = 15   # HTTP请求超时(秒)
    CRAWL_DELAY        = 0.5  # 爬取间隔(秒)，礼貌爬取

    # ─── 日志设置 ─────────────────────────────────────────────
    LOG_DIR  = "logs"
    LOG_KEEP = 30  # 保留最近N天的日志文件
