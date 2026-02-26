#!/usr/bin/env python3
"""
微信推送模块 - 中文格式优化版
支持: Server酱 / 企业微信机器人 / WxPusher
"""

import requests
import json
import logging
import re
import os
from datetime import datetime, timezone, timedelta
from config import Config

log = logging.getLogger(__name__)

CATEGORY_META = {
    "finance":  {"emoji": "📈", "title": "金融财经"},
    "social":   {"emoji": "📱", "title": "科技自媒体"},
    "wellness": {"emoji": "🧠", "title": "健康·心理·美学"},
}


def format_wechat_message(news_data):
    tz_cst = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%Y年%m月%d日  %H:%M")
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[datetime.now(tz_cst).weekday()]
    total = sum(len(v) for v in news_data.values())

    lines = [
        "📰 每日智识简报",
        "─" * 22,
        "%s %s" % (now_str, weekday),
        "共 %d 条精选新闻" % total,
        "",
    ]

    for cat_key, meta in CATEGORY_META.items():
        items = news_data.get(cat_key, [])
        if not items:
            continue

        lines.append("=" * 22)
        lines.append("%s 【%s】" % (meta["emoji"], meta["title"]))
        lines.append("=" * 22)
        lines.append("")

        for i, item in enumerate(items[:10], 1):
            title   = item.get("title",   item.get("title_en",   "(无标题)"))
            summary = item.get("summary", item.get("summary_en", ""))
            source  = item.get("source", "")
            url     = item.get("url", "")

            lines.append("─" * 20)
            lines.append("【%02d】%s" % (i, title))
            lines.append("📌 来源：%s" % source)
            lines.append("")

            if summary:
                sentences = re.split(r'(?<=[。！？.!?])\s*', summary.strip())
                sentences = [s.strip() for s in sentences if s.strip()]
                for sent in sentences[:5]:
                    lines.append("  %s" % sent)
                lines.append("")

            if url:
                lines.append("🔗 %s" % url)
            lines.append("")

    lines.append("─" * 22)
    lines.append("🤖 每天08:00自动推送")
    lines.append("📊 数据来自30+全球顶级媒体")

    return "\n".join(lines)


def push_serverchan(news_data):
    send_key = Config.SERVERCHAN_SENDKEY
    if not send_key:
        log.warning("Server酱 SendKey 未配置，跳过")
        return False

    tz_cst  = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%m月%d日")
    content = format_wechat_message(news_data)

    try:
        resp = requests.post(
            "https://sctapi.ftqq.com/%s.send" % send_key,
            data={
                "title": "📰 每日智识简报 · %s" % now_str,
                "desp":  content,
            },
            timeout=20
        )
        result = resp.json()
        if result.get("code") == 0:
            log.info("Server酱推送成功")
            return True
        else:
            log.error("Server酱推送失败: %s" % str(result))
            return False
    except Exception as e:
        log.error("Server酱异常: %s" % str(e))
        return False


def push_wecom_robot(news_data):
    webhook_url = Config.WECOM_WEBHOOK_URL
    if not webhook_url:
        log.warning("企业微信 Webhook 未配置，跳过")
        return False

    tz_cst  = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%Y年%m月%d日 %H:%M")
    total   = sum(len(v) for v in news_data.values())

    header = "# 📰 每日智识简报\n> **%s** · 共%d条精选新闻\n" % (now_str, total)
    _send_wecom(webhook_url, header)

    success = True
    for cat_key, meta in CATEGORY_META.items():
        items = news_data.get(cat_key, [])
        if not items:
            continue

        msg_lines = ["## %s %s" % (meta["emoji"], meta["title"]), ""]
        for i, item in enumerate(items[:10], 1):
            title   = item.get("title",   item.get("title_en", ""))
            summary = item.get("summary", "")[:150]
            source  = item.get("source", "")
            url     = item.get("url", "")

            if url:
                msg_lines.append("**%02d** `%s` **[%s](%s)**" % (i, source, title, url))
            else:
                msg_lines.append("**%02d** `%s` **%s**" % (i, source, title))
            if summary:
                msg_lines.append("> %s" % summary)
            msg_lines.append("")

        ok = _send_wecom(webhook_url, "\n".join(msg_lines))
        if not ok:
            success = False
        import time; time.sleep(0.5)

    return success


def _send_wecom(webhook_url, content):
    try:
        resp = requests.post(
            webhook_url,
            json={"msgtype": "markdown", "markdown": {"content": content}},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        result = resp.json()
        return result.get("errcode") == 0
    except Exception as e:
        log.error("企业微信发送异常: %s" % str(e))
        return False


def push_wxpusher(news_data):
    app_token = Config.WXPUSHER_APP_TOKEN
    uids      = Config.WXPUSHER_UIDS
    if not app_token or not uids:
        log.warning("WxPusher 未配置，跳过")
        return False

    tz_cst  = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%m月%d日")
    content = format_wechat_message(news_data)
    html_content = content.replace("\n", "<br>")

    try:
        resp = requests.post(
            "https://wxpusher.zjiecode.com/api/send/message",
            json={
                "appToken":    app_token,
                "content":     html_content,
                "summary":     "📰 每日智识简报 · %s" % now_str,
                "contentType": 2,
                "uids":        uids,
            },
            timeout=20
        )
        result = resp.json()
        if result.get("success"):
            log.info("WxPusher推送成功")
            return True
        else:
            log.error("WxPusher推送失败: %s" % str(result))
            return False
    except Exception as e:
        log.error("WxPusher异常: %s" % str(e))
        return False


def push_all(news_data):
    results = {}

    if Config.SERVERCHAN_SENDKEY:
        results["serverchan"] = push_serverchan(news_data)

    if Config.WECOM_WEBHOOK_URL:
        results["wecom"] = push_wecom_robot(news_data)

    if Config.WXPUSHER_APP_TOKEN:
        results["wxpusher"] = push_wxpusher(news_data)

    if not results:
        log.warning("没有配置任何推送渠道！请在 GitHub Secrets 中设置")

    return results
