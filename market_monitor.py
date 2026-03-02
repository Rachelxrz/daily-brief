#!/usr/bin/env python3
"""
📌 每日市场结构监控 - 自动生成并推送到微信
Market Structure Monitor - Auto-generate & Push to WeChat

功能：
  - 通过 Claude API + Web Search 自动抓取最新市场数据
  - 生成标准化的结构监控报告（6大模块）
  - 推送到微信（支持企业微信/Server酱/WxPusher）
  - 每天定时自动执行（通过 GitHub Actions）

报告结构：
  1) 🌪️ 波动性结构（VIX）
  2) 🧠 信用风险结构（HY Spread）
  3) 💰 资金流向结构（QQQ/GLD/XLE/XLU/TLT）
  4) 💵 美元与利率结构（DXY/10Y）
  5) 📊 板块轮动结构
  6) 🧭 结构等级判定 + 操作建议
"""

import os
import re
import json
import logging
import requests
import time
from datetime import datetime, timezone, timedelta
from config import Config

log = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL   = "claude-sonnet-4-20250514"

# ─── 生成报告的 Prompt ────────────────────────────────────────
MARKET_MONITOR_PROMPT = """你是一位专业的宏观市场结构分析师。请使用 web_search 工具搜索今天最新的市场数据，然后生成一份完整的【📌 结构监控 标准版】报告。

今天的日期是：{date}

请按以下格式输出报告（使用中文，数据要精确）：

---
# 📌 结构监控 标准版
### {date} · [当前主要市场事件]

---

## 1) 🌪️ 波动性结构
- VIX 当前水平：XX.XX
- 风险区判定：[正常区 <20 / 警戒区 20-30 / 危险区 30-40 / 极度恐慌 >40]
- 近期趋势：[连续上升/下降/横盘] X天
- WTI 原油隐含波动率（如有数据）：XX%

---

## 2) 🧠 信用风险结构
- 高收益债利差（HY Spread）：X.XX%（参考值：正常<4%，警戒4-6%，危机>6%）
- 趋势方向：[扩大/收窄/横盘]
- 阶段性突破：[是/否，说明]
- 信用市场情绪：[风险偏好/中性/风险厌恶]

---

## 3) 💰 资金流向结构

**主要流出方向：**
- 科技/成长：QQQ [今日涨跌%]，Nasdaq [今日涨跌%]
- 其他流出板块：[说明]

**主要流入方向：**
| 资产 | 今日表现 | 信号 |
|------|---------|------|
| 🛢️ 能源 XLE/XOM | [%] | [✅/⚠️/❌] |
| 🥇 黄金 GLD | [%] | [✅/⚠️/❌] |
| 🔌 公用事业 XLU | [%] | [✅/⚠️/❌] |
| 🏦 国债 TLT | [%] | [✅/⚠️/❌] |
| 🛡️ 国防 LMT/RTX | [%] | [✅/⚠️/❌] |

---

## 4) 💵 美元与利率结构

**美元指数 DXY：**
- 当前水平：XXX.XX
- 结构方向：[多头/空头/中性]
- 是否突破关键位：[是/否]

**美国国债 10Y：**
- 当前收益率：X.XX%
- 方向：[上升/下降/横盘]
- 主导逻辑：[避险需求 / 通胀预期 / 两者混合]

---

## 5) 📊 板块轮动结构

| 板块 vs 大盘 | 今日表现 | 相对强弱 |
|------------|---------|---------|
| ⚡ 能源 vs SPY | +/-X% vs +/-X% | [跑赢/跑输/持平] |
| 🛡️ 国防 vs SPY | [数据] | [判断] |
| 🥇 黄金矿股 GDX vs SPY | [数据] | [判断] |
| 🔌 公用事业 XLU vs SPY | [数据] | [判断] |
| 💻 科技 QQQ vs SPY | [数据] | [判断] |
| 📦 小盘 IWM vs SPY | [数据] | [判断] |

---

## 6) 🧭 结构等级判定

**综合判定：[🟢 稳定 / 🟡 轻度风险 / 🟠 中等风险 / 🔴 系统性风险]**

**判定理由：**
[2-3句话说明核心逻辑]

**操作倾向建议：**
| 操作方向 | 建议 | 理由 |
|---------|------|------|
| 减少科技（QQQ） | ✅是/❌否/🟡观望 | [理由] |
| 提高实体资产（能源/LNG） | ✅是/❌否/🟡观望 | [理由] |
| 加黄金（GLD） | ✅是/❌否/🟡观望 | [理由] |
| 加防御板块（XLU/国债） | ✅是/❌否/🟡观望 | [理由] |
| 减风险暴露 | ✅是/❌否/🟡观望 | [理由] |
| 美元/现金仓位 | [具体建议] | [理由] |

---

**🔔 下次更新触发条件：**
[列出2-3个需要重新评估的关键触发事件]

---

⏰ 数据时间：{date} 北京时间 · 🤖 AI自动生成
"""


def call_claude_with_search(date_str: str, max_retries: int = 3) -> str:
    """
    调用 Claude API（带 Web Search 工具）生成市场结构报告。
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("未设置 ANTHROPIC_API_KEY 环境变量")

    prompt = MARKET_MONITOR_PROMPT.format(date=date_str)

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "tools": [
            {
                "type": "web_search_20250305",
                "name": "web_search"
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "web-search-2025-03-05",
        "Content-Type": "application/json"
    }

    for attempt in range(1, max_retries + 1):
        try:
            log.info(f"🔍 第 {attempt} 次尝试调用 Claude API...")
            resp = requests.post(
                ANTHROPIC_API_URL,
                json=payload,
                headers=headers,
                timeout=120  # 搜索+生成需要较长时间
            )
            resp.raise_for_status()
            data = resp.json()

            # 提取所有 text 内容
            full_text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    full_text += block.get("text", "")

            if full_text.strip():
                log.info(f"✅ Claude API 返回成功，字符数: {len(full_text)}")
                return full_text
            else:
                log.warning(f"⚠️ 第 {attempt} 次：返回内容为空")

        except requests.exceptions.Timeout:
            log.warning(f"⚠️ 第 {attempt} 次：请求超时")
        except requests.exceptions.RequestException as e:
            log.error(f"❌ 第 {attempt} 次：请求失败: {e}")
        except Exception as e:
            log.error(f"❌ 第 {attempt} 次：未知错误: {e}")

        if attempt < max_retries:
            wait = 2 ** attempt * 5  # 指数退避: 10s, 20s
            log.info(f"   等待 {wait}s 后重试...")
            time.sleep(wait)

    raise RuntimeError(f"Claude API 调用失败，已重试 {max_retries} 次")


def format_for_serverchan(report: str, date_str: str) -> tuple[str, str]:
    """
    格式化为 Server酱 推送格式。
    返回 (title, content)
    """
    title = f"📌 市场结构监控 · {date_str}"
    # Server酱 支持 Markdown
    content = report
    return title, content


def format_for_wecom(report: str) -> list[str]:
    """
    格式化为企业微信分段 Markdown（每段 < 4096 字符）。
    返回分段列表。
    """
    # 按 --- 分割报告为多段
    sections = re.split(r'\n---+\n', report)
    chunks = []
    current = ""

    for section in sections:
        if len(current) + len(section) + 5 < 3800:
            current += section + "\n---\n"
        else:
            if current.strip():
                chunks.append(current.strip())
            current = section + "\n---\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [report[:3800]]


def push_market_report_serverchan(report: str, date_str: str) -> bool:
    """推送市场报告到 Server酱。"""
    send_key = Config.SERVERCHAN_SENDKEY
    if not send_key:
        log.warning("Server酱 SendKey 未配置，跳过")
        return False

    title, content = format_for_serverchan(report, date_str)

    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{send_key}.send",
            data={
                "title": title,
                "desp":  content,
            },
            timeout=15
        )
        result = resp.json()
        if result.get("code") == 0:
            log.info("✅ Server酱 市场报告推送成功")
            return True
        else:
            log.error(f"❌ Server酱推送失败: {result}")
            return False
    except Exception as e:
        log.error(f"❌ Server酱请求异常: {e}")
        return False


def push_market_report_wecom(report: str) -> bool:
    """推送市场报告到企业微信群机器人（分段发送）。"""
    webhook_url = Config.WECOM_WEBHOOK_URL
    if not webhook_url:
        log.warning("WECOM_WEBHOOK_URL 未配置，跳过")
        return False

    chunks = format_for_wecom(report)
    success = True

    for i, chunk in enumerate(chunks):
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": chunk}
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
                log.info(f"✅ 企业微信段落 {i+1}/{len(chunks)} 推送成功")
            else:
                log.error(f"❌ 企业微信段落 {i+1} 失败: {result}")
                success = False
        except Exception as e:
            log.error(f"❌ 企业微信请求异常: {e}")
            success = False
        time.sleep(0.5)

    return success


def push_market_report_wxpusher(report: str, date_str: str) -> bool:
    """推送市场报告到 WxPusher。"""
    app_token = Config.WXPUSHER_APP_TOKEN
    uids      = Config.WXPUSHER_UIDS

    if not app_token or not uids:
        log.warning("WxPusher 未配置，跳过")
        return False

    html_content = report.replace('\n', '<br>').replace('# ', '<h3>').replace('## ', '<h4>')

    payload = {
        "appToken":    app_token,
        "content":     html_content,
        "summary":     f"📌 市场结构监控 · {date_str}",
        "contentType": 2,
        "uids":        uids,
        "url":         "",
    }

    try:
        resp = requests.post(
            "https://wxpusher.zjiecode.com/api/send/message",
            json=payload,
            timeout=15
        )
        result = resp.json()
        if result.get("success"):
            log.info("✅ WxPusher 市场报告推送成功")
            return True
        else:
            log.error(f"❌ WxPusher 推送失败: {result}")
            return False
    except Exception as e:
        log.error(f"❌ WxPusher 请求异常: {e}")
        return False


def run_market_monitor(dry_run: bool = False) -> str:
    """
    执行每日市场结构监控主流程。
    
    Returns:
        生成的报告文本
    """
    tz_cst = timezone(timedelta(hours=8))
    now    = datetime.now(tz_cst)
    date_str = now.strftime("%Y年%m月%d日")

    log.info("=" * 60)
    log.info("📌 市场结构监控任务启动")
    log.info(f"   时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log.info("=" * 60)

    # Step 1: 调用 Claude API 生成报告
    log.info("\n🤖 Step 1/2: 调用 Claude API 搜索数据并生成报告...")
    report = call_claude_with_search(date_str)

    log.info(f"\n📄 报告预览 (前500字):\n{report[:500]}...")

    if dry_run:
        log.info("\n🔍 [Dry Run] 跳过推送，完整报告已生成")
        log.info("\n" + "=" * 60)
        log.info(report)
        log.info("=" * 60)
        return report

    # Step 2: 推送到微信
    log.info("\n📲 Step 2/2: 推送到微信...")
    results = {}

    if Config.SERVERCHAN_SENDKEY:
        results['serverchan'] = push_market_report_serverchan(report, date_str)

    if Config.WECOM_WEBHOOK_URL:
        results['wecom'] = push_market_report_wecom(report)

    if Config.WXPUSHER_APP_TOKEN:
        results['wxpusher'] = push_market_report_wxpusher(report, date_str)

    if not results:
        log.warning("⚠️  未配置任何推送渠道！请在 GitHub Secrets 中设置")

    # 报告结果
    log.info("\n" + "=" * 60)
    log.info("📊 市场监控任务完成")
    for channel, ok in results.items():
        status = "✅ 成功" if ok else "❌ 失败"
        log.info(f"   {channel}: {status}")
    log.info("=" * 60)

    return report


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    dry = "--dry-run" in sys.argv
    run_market_monitor(dry_run=dry)
