#!/usr/bin/env python3
"""
微信推送模块 - 中文格式优化版
支持: Server酱 / 企业微信机器人 / WxPusher
"""

import requests, json, logging, os
from datetime import datetime, timezone, timedelta
from config import Config

log = logging.getLogger(__name__)

CATEGORY_META = {
    "finance":  {"emoji": "📈", "title": "金融财经"},
    "social":   {"emoji": "📱", "title": "科技自媒体"},
    "wellness": {"emoji": "🧠", "title": "健康·心理·美学"},
}


def format_wechat_message(news_data: dict) -> str:
    """
    生成美观的中文微信消息。
    每条新闻：标题 + 来源 + 3-5句摘要 + 链接
    """
    tz_cst = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%Y年%m月%d日  %H:%M")
    weekdays = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday  = weekdays[datetime.now(tz_cst).weekday()]

    lines = [
        f"📰 每日智识简报",
        f"{'─'*22}",
        f"🗓 {now_str} {weekday}",
        f"共 {sum(len(v) for v in news_data.values())} 条精选新闻",
        "",
    ]

    for cat_key, meta in CATEGORY_META.items():
        items = news_data.get(cat_key, [])
        if not items:
            continue

        lines.append(f"{'═'*22}")
        lines.append(f"{meta['emoji']} 【{meta['title']}】")
        lines.append(f"{'═'*22}")
        lines.append("")

        for i, item in enumerate(items[:10], 1):
            title   = item.get("title",   item.get("title_en",   "（无标题）"))
            summary = item.get("summary", item.get("summary_en", ""))
            source  = item.get("source", "")
            url     = item.get("url", "")

            lines.append(f"{'—'*20}")
            lines.append(f"【{i:02d}】{title}")
            lines.append(f"📌 来源：{source}")
            lines.append("")

            # 摘要：每句单独一行，更易读
            if summary:
                # 按句号、问号、叹号分句
                sentences = re.split(r'(?<=[。！？.!?])\s*', summary.strip())
                sentences = [s.strip() for s in sentences if s.strip()]
                for sent in sentences[:5]:
                    lines.append(f"  {sent}")
                lines.append("")

            if url:
                lines.append(f"🔗 {url}")
            lines.append("")

    lines.append(f"{'─'*22}")
    lines.append("🤖 每天08:00自动推送")
    lines.append("📊 数据来自30+全球顶级媒体")

    return "\n".join(lines)


def push_serverchan(news_data: dict) -> bool:
    """Server酱推送（个人微信）"""
    send_key = Config.SERVERCHAN_SENDKEY
    if not send_key:
        log.warning("Server酱 SendKey 未配置，跳过")
        return False

    tz_cst  = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%m月%d日")
    content = format_wechat_message(news_data)

    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{send_key}.send",
            data={
                "title": f"📰 每日智识简报 · {now_str}",
                "desp":  content,
            },
            timeout=20
        )
        result = resp.json()
        if result.get("code") == 0:
            log.info("✅ Server酱推送成功")
            return True
        else:
            log.error(f"❌ Server酱推送失败: {result}")
            return False
    except Exception as e:
        log.error(f"❌ Server酱异常: {e}")
        return False


def push_wecom_robot(news_data: dict) -> bool:
    """企业微信群机器人推送"""
    webhook_url = Config.WECOM_WEBHOOK_URL
    if not webhook_url:
        log.warning("企业微信 Webhook 未配置，跳过")
        return False

    tz_cst  = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%Y年%m月%d日 %H:%M")
    success = True

    # 企业微信每条消息限4096字，分类分批发送
    # 先发头部
    header = f"# 📰 每日智识简报\n> **{now_str}** · 共{sum(len(v) for v in news_data.values())}条精选新闻\n"
    _send_wecom(webhook_url, header)

    for cat_key, meta in CATEGORY_META.items():
        items = news_data.get(cat_key, [])
        if not items:
            continue

        msg_lines = [f"## {meta['emoji']} {meta['title']}", ""]
        for i, item in enumerate(items[:10], 1):
            title   = item.get("title", item.get("title_en", ""))
            summary = item.get("summary", "")[:150]
            source  = item.get("source", "")
            url     = item.get("url", "")

            if url:
                msg_lines.append(f"**{i:02d}** `{source}` **[{title}]({url})**")
            else:
                msg_lines.append(f"**{i:02d}** `{source}` **{title}**")
            if summary:
                msg_lines.append(f"> {summary}")
            msg_lines.append("")

        ok = _send_wecom(webhook_url, "\n".join(msg_lines))
        if not ok:
            success = False
        import time; time.sleep(0.5)

    return success


def _send_wecom(webhook_url: str, content: str) -> bool:
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
        log.error(f"企业微信发送异常: {e}")
        return False


def push_wxpusher(news_data: dict) -> bool:
    """WxPusher推送（个人微信）"""
    app_token = Config.WXPUSHER_APP_TOKEN
    uids      = Config.WXPUSHER_UIDS
    if not app_token or not uids:
        log.warning("WxPusher 未配置，跳过")
        return False

    tz_cst  = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_cst).strftime("%m月%d日")
    content = format_wechat_message(news_data)
    # 转HTML换行
    html_content = content.replace('\n', '<br>')

    try:
        resp = requests.post(
            "https://wxpusher.zjiecode.com/api/send/message",
            json={
                "appToken":    app_token,
                "content":     html_content,
                "summary":     f"📰 每日智识简报 · {now_str}",
                "contentType": 2,
                "uids":        uids,
            },
            timeout=20
        )
        result = resp.json()
        if result.get("success"):
            log.info("✅ WxPusher推送成功")
            return True
        else:
            log.error(f"❌ WxPusher推送失败: {result}")
            return False
    except Exception as e:
        log.error(f"❌ WxPusher异常: {e}")
        return False


def push_all(news_data: dict) -> dict:
    """尝试所有已配置的推送渠道"""
    results = {}

    if Config.SERVERCHAN_SENDKEY:
        results['serverchan'] = push_serverchan(news_data)

    if Config.WECOM_WEBHOOK_URL:
        results['wecom'] = push_wecom_robot(news_data)

    if Config.WXPUSHER_APP_TOKEN:
        results['wxpusher'] = push_wxpusher(news_data)

    if not results:
        log.warning("⚠️  没有配置任何推送渠道！请在 GitHub Secrets 中设置")

    return results


# ─── 补充 import（format_wechat_message 用到）─────────────
import re

if __name__ == "__main__":
    # 测试格式
    test_data = {
        "finance": [{
            "title": "英伟达Q4营收681亿美元，大幅超出华尔街预期",
            "summary": "英伟达公布第四季度营收681亿美元，同比增长73%，超出分析师预期近20亿美元。数据中心业务营收达到623亿美元，创历史新高。公司第一季度营收指引为780亿美元，再度震撼市场。CEO黄仁勋宣称"AI代理拐点已经到来"，显示出公司对未来增长的强烈信心。分析师普遍上调目标价，AI算力需求在短期内不存在见顶风险。",
            "source": "Reuters",
            "url": "https://reuters.com/test"
        }],
        "social": [{"title": "测试自媒体新闻", "summary": "这是第一句。这是第二句。这是第三句。", "source": "TechCrunch", "url": ""}],
        "wellness": [{"title": "测试健康新闻", "summary": "研究表明。数据显示。结论如下。影响深远。建议如此。", "source": "ScienceDaily", "url": ""}],
    }
    msg = format_wechat_message(test_data)
    print(msg)
