#!/usr/bin/env python3
"""
微信推送模块 - 支持三种推送方式
WeChat Push Module

支持:
  1. 企业微信群机器人 Webhook (推荐，免费稳定)
  2. WxPusher (个人微信，需扫码关注)
  3. Server酱 (个人微信，简单易用)
"""

import requests
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from config import Config

log = logging.getLogger(__name__)

# ─── 企业微信 Markdown 颜色 ───────────────────────────────
COLOR_GOLD    = "warning"    # 黄色
COLOR_RED     = "comment"    # 红色  
COLOR_GREEN   = "info"       # 绿色
COLOR_GRAY    = "comment"    # 灰色

CATEGORY_META = {
    "finance": {
        "emoji": "📈",
        "title": "金融财经",
        "subtitle": "Bloomberg · Reuters · FT · CNBC · WSJ",
        "color": COLOR_GOLD,
    },
    "social": {
        "emoji": "📱",
        "title": "自媒体精选",
        "subtitle": "TechCrunch · Wired · HN · MIT Review · 36kr",
        "color": COLOR_RED,
    },
    "wellness": {
        "emoji": "🧠",
        "title": "健康·心理·美学",
        "subtitle": "ScienceDaily · PsyPost · Aeon · Nature · Big Think",
        "color": COLOR_GREEN,
    },
}

def format_wecom_markdown(news_data: dict) -> str:
    """
    格式化为企业微信 Markdown 消息。
    企业微信 Markdown 支持有限，使用粗体+引用块。
    """
    tz_cst = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%Y年%m月%d日 %H:%M")
    
    lines = []
    lines.append(f"# 📰 每日智识简报")
    lines.append(f"> <font color=\"comment\">{now_str} · AI自动聚合 · 30条精选</font>")
    lines.append("")
    
    for cat_key, meta in CATEGORY_META.items():
        items = news_data.get(cat_key, [])
        if not items:
            continue
        
        lines.append(f"---")
        lines.append(f"## {meta['emoji']} {meta['title']}")
        lines.append(f"> <font color=\"comment\">{meta['subtitle']}</font>")
        lines.append("")
        
        for i, item in enumerate(items[:10], 1):
            title   = item.get('title', '').replace('\n', ' ')
            summary = item.get('summary', '').replace('\n', ' ')
            source  = item.get('source', '')
            url     = item.get('url', '')
            
            # 标题行：编号 + 来源 + 标题（可点击）
            if url:
                lines.append(f"**{i:02d}** `{source}` **[{title}]({url})**")
            else:
                lines.append(f"**{i:02d}** `{source}` **{title}**")
            
            # 摘要（如果有）
            if summary and len(summary) > 20:
                lines.append(f"> {summary}")
            
            lines.append("")
    
    lines.append("---")
    lines.append(f"<font color=\"comment\">🤖 每日 08:00 自动推送 · 数据来自30+全球顶级媒体</font>")
    
    return "\n".join(lines)


def format_text_message(news_data: dict) -> str:
    """格式化为纯文本消息（用于Server酱 / WxPusher）。"""
    tz_cst = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%Y/%m/%d %H:%M")
    
    lines = [f"📰 每日智识简报 · {now_str}", ""]
    
    for cat_key, meta in CATEGORY_META.items():
        items = news_data.get(cat_key, [])
        if not items:
            continue
        
        lines.append(f"{meta['emoji']} {meta['title']}")
        lines.append("─" * 30)
        
        for i, item in enumerate(items[:10], 1):
            title   = item.get('title', '').replace('\n', ' ')
            summary = item.get('summary', '')[:100] + '…' if item.get('summary', '') else ''
            source  = item.get('source', '')
            url     = item.get('url', '')
            
            lines.append(f"{i:02d}. [{source}] {title}")
            if summary:
                lines.append(f"    {summary}")
            if url:
                lines.append(f"    🔗 {url}")
            lines.append("")
        
        lines.append("")
    
    lines.append("🤖 每日08:00自动推送 | Daily Intelligence Brief")
    return "\n".join(lines)


# ─── 推送方法1: 企业微信群机器人 ─────────────────────────────
def push_wecom_robot(news_data: dict) -> bool:
    """
    推送到企业微信群机器人。
    
    配置方法:
      1. 在企业微信群里 → 右上角 ··· → 添加机器人
      2. 复制 Webhook URL
      3. 填入 config.py 的 WECOM_WEBHOOK_URL
    """
    webhook_url = Config.WECOM_WEBHOOK_URL
    if not webhook_url:
        log.warning("WECOM_WEBHOOK_URL 未配置，跳过企业微信推送")
        return False
    
    # 企业微信单条消息限制约4096字符，需要分段发送
    sections = []
    
    # 发送头部
    tz_cst = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%Y年%m月%d日 %H:%M")
    header = f"# 📰 每日智识简报\n> **{now_str}** · AI自动聚合 · 30条精选新闻\n"
    sections.append(header)
    
    # 每个分类单独发送（避免超长）
    for cat_key, meta in CATEGORY_META.items():
        items = news_data.get(cat_key, [])
        if not items:
            continue
        
        msg_lines = [
            f"## {meta['emoji']} {meta['title']}",
            f"> <font color=\"comment\">{meta['subtitle']}</font>",
            ""
        ]
        
        for i, item in enumerate(items[:10], 1):
            title  = item.get('title', '').replace('\n', ' ')[:100]
            source = item.get('source', '')
            url    = item.get('url', '')
            summary = item.get('summary', '')[:120]
            
            if url:
                msg_lines.append(f"**{i:02d}** `{source}`")
                msg_lines.append(f"**[{title}]({url})**")
            else:
                msg_lines.append(f"**{i:02d}** `{source}` **{title}**")
            
            if summary:
                msg_lines.append(f"> {summary}")
            msg_lines.append("")
        
        sections.append("\n".join(msg_lines))
    
    # 逐段推送
    success = True
    for i, content in enumerate(sections):
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content}
        }
        try:
            resp = requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            result = resp.json()
            if result.get("errcode") == 0:
                log.info(f"✅ 企业微信段落 {i+1}/{len(sections)} 推送成功")
            else:
                log.error(f"❌ 企业微信推送失败: {result}")
                success = False
        except Exception as e:
            log.error(f"❌ 企业微信请求异常: {e}")
            success = False
        
        import time; time.sleep(0.5)  # 避免频率限制
    
    return success


# ─── 推送方法2: WxPusher ─────────────────────────────────────
def push_wxpusher(news_data: dict) -> bool:
    """
    推送到 WxPusher（推送到个人微信）。
    
    配置方法:
      1. 访问 https://wxpusher.zjiecode.com
      2. 注册并创建应用，获取 APP_TOKEN
      3. 扫码关注，获取你的 UID
      4. 填入 config.py
    """
    app_token = Config.WXPUSHER_APP_TOKEN
    uids      = Config.WXPUSHER_UIDS  # list of UIDs
    
    if not app_token or not uids:
        log.warning("WxPusher 未配置，跳过推送")
        return False
    
    content = format_text_message(news_data)
    
    # WxPusher 支持 HTML 格式
    html_content = content.replace('\n', '<br>')
    
    payload = {
        "appToken": app_token,
        "content": html_content,
        "summary": f"📰 每日智识简报 · {datetime.now().strftime('%m/%d')}",
        "contentType": 2,  # 2=HTML
        "uids": uids,
        "url": "",
    }
    
    try:
        resp = requests.post(
            "https://wxpusher.zjiecode.com/api/send/message",
            json=payload,
            timeout=15
        )
        result = resp.json()
        if result.get("success"):
            log.info(f"✅ WxPusher 推送成功")
            return True
        else:
            log.error(f"❌ WxPusher 推送失败: {result}")
            return False
    except Exception as e:
        log.error(f"❌ WxPusher 请求异常: {e}")
        return False


# ─── 推送方法3: Server酱 (Server Chan) ───────────────────────
def push_serverchan(news_data: dict) -> bool:
    """
    推送到 Server酱（推送到微信）。
    
    配置方法:
      1. 访问 https://sct.ftqq.com
      2. 微信扫码登录，获取 SendKey
      3. 填入 config.py 的 SERVERCHAN_SENDKEY
    """
    send_key = Config.SERVERCHAN_SENDKEY
    if not send_key:
        log.warning("Server酱 SendKey 未配置，跳过推送")
        return False
    
    content = format_text_message(news_data)
    now_str = datetime.now().strftime("%Y/%m/%d")
    
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{send_key}.send",
            data={
                "title": f"📰 每日智识简报 {now_str}",
                "desp": content,
            },
            timeout=15
        )
        result = resp.json()
        if result.get("code") == 0:
            log.info("✅ Server酱推送成功")
            return True
        else:
            log.error(f"❌ Server酱推送失败: {result}")
            return False
    except Exception as e:
        log.error(f"❌ Server酱请求异常: {e}")
        return False


# ─── 统一推送入口 ─────────────────────────────────────────
def push_all(news_data: dict) -> dict:
    """尝试所有已配置的推送渠道。"""
    results = {}
    
    if Config.WECOM_WEBHOOK_URL:
        results['wecom'] = push_wecom_robot(news_data)
    
    if Config.WXPUSHER_APP_TOKEN:
        results['wxpusher'] = push_wxpusher(news_data)
    
    if Config.SERVERCHAN_SENDKEY:
        results['serverchan'] = push_serverchan(news_data)
    
    if not results:
        log.warning("⚠️  没有配置任何推送渠道！请编辑 config.py")
    
    return results


if __name__ == "__main__":
    # 测试用：发送示例数据
    test_data = {
        "finance": [
            {"title": "测试金融新闻标题", "summary": "这是一条测试摘要内容。", "source": "Reuters", "url": "https://reuters.com"}
        ],
        "social": [
            {"title": "测试自媒体新闻标题", "summary": "这是一条测试摘要内容。", "source": "TechCrunch", "url": "https://techcrunch.com"}
        ],
        "wellness": [
            {"title": "测试健康心理新闻标题", "summary": "这是一条测试摘要内容。", "source": "ScienceDaily", "url": "https://sciencedaily.com"}
        ],
    }
    results = push_all(test_data)
    print("推送结果:", results)
