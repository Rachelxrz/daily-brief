#!/usr/bin/env python3
"""
📌 每日市场结构监控 - 中英文双语版
Market Structure Monitor - Bilingual (CN + EN)

流程：
  1. 调用 Claude API + Web Search 搜索当天数据，生成中文报告
  2. 基于中文报告数据，生成英文版（不再重复搜索）
  3. 先推送中文，再推送英文（各自独立消息）
"""

import os
import re
import logging
import requests
import time
from datetime import datetime, timezone, timedelta
from config      import Config
from save_to_web import save_monitor

log = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL   = "claude-sonnet-4-20250514"

# ─────────────────────────────────────────────────────────────
#  PROMPT: 中文版
# ─────────────────────────────────────────────────────────────
PROMPT_CN = """你是一位专业的宏观市场结构分析师。请使用 web_search 工具搜索今天最新的市场数据，然后生成一份完整的【📌 结构监控 标准版】报告。

今天的日期是：{date}

请按以下格式输出报告（使用中文，数据要精确）：

---
# 📌 结构监控 标准版（中文）
### {date} · [当前主要市场事件]

---

## 1) 🌪️ 波动性结构
- VIX 当前水平：XX.XX
- 风险区判定：[正常区 <20 / 警戒区 20-30 / 危险区 30-40 / 极度恐慌 >40]
- 近期趋势：[连续上升/下降/横盘] X天
- WTI 原油隐含波动率（如有）：XX%

---

## 2) 🧠 信用风险结构
- 高收益债利差（HY Spread）：X.XX%（参考：正常<4%，警戒4-6%，危机>6%）
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
⏰ {date} 北京时间 · 🤖 AI自动生成
"""

# ─────────────────────────────────────────────────────────────
#  PROMPT: 英文版（基于中文报告翻译，不再搜索）
# ─────────────────────────────────────────────────────────────
PROMPT_EN = """You are a professional macro market structure analyst.

Below is today's market structure report in Chinese, generated using live market data. 
Translate and reformat it into the English version using the EXACT same data and figures.
Do NOT search the web again — just translate and reformat.

Chinese report:
{cn_report}

Output the English report in this exact format:

---
# 📌 Market Structure Monitor (English)
### {date} · [Current Major Market Event]

---

## 1) 🌪️ Volatility Structure
- VIX Current Level: XX.XX
- Risk Zone: [Normal <20 / Caution 20-30 / Danger 30-40 / Extreme Fear >40]
- Recent Trend: [Rising / Falling / Flat] for X days
- WTI Implied Volatility (if available): XX%

---

## 2) 🧠 Credit Risk Structure
- High Yield Spread: X.XX% (Reference: Normal <4%, Caution 4-6%, Crisis >6%)
- Trend: [Widening / Narrowing / Flat]
- Key Level Breakout: [Yes / No — explain]
- Credit Sentiment: [Risk-On / Neutral / Risk-Off]

---

## 3) 💰 Capital Flow Structure

**Major Outflows:**
- Tech/Growth: QQQ [today %], Nasdaq [today %]
- Other sectors under pressure: [details]

**Major Inflows:**
| Asset | Today's Performance | Signal |
|-------|-------------------|--------|
| 🛢️ Energy XLE/XOM | [%] | [✅/⚠️/❌] |
| 🥇 Gold GLD | [%] | [✅/⚠️/❌] |
| 🔌 Utilities XLU | [%] | [✅/⚠️/❌] |
| 🏦 Treasuries TLT | [%] | [✅/⚠️/❌] |
| 🛡️ Defense LMT/RTX | [%] | [✅/⚠️/❌] |

---

## 4) 💵 Dollar & Rates Structure

**US Dollar Index (DXY):**
- Current Level: XXX.XX
- Structure: [Bullish / Bearish / Neutral]
- Key Level Break: [Yes / No]

**US 10Y Treasury:**
- Current Yield: X.XX%
- Direction: [Rising / Falling / Flat]
- Dominant Driver: [Safe-Haven Demand / Inflation Expectations / Mixed]

---

## 5) 📊 Sector Rotation

| Sector vs Market | Today | Relative Strength |
|------------------|-------|------------------|
| ⚡ Energy vs SPY | +/-X% vs +/-X% | [Outperform / Underperform / Neutral] |
| 🛡️ Defense vs SPY | [data] | [judgment] |
| 🥇 Gold Miners GDX vs SPY | [data] | [judgment] |
| 🔌 Utilities XLU vs SPY | [data] | [judgment] |
| 💻 Tech QQQ vs SPY | [data] | [judgment] |
| 📦 Small Cap IWM vs SPY | [data] | [judgment] |

---

## 6) 🧭 Structure Rating & Action Bias

**Overall Rating: [🟢 Stable / 🟡 Low Risk / 🟠 Moderate Risk / 🔴 Systemic Risk]**

**Rationale:**
[2-3 sentences explaining the core logic]

**Tactical Positioning:**
| Action | Recommendation | Rationale |
|--------|---------------|-----------|
| Reduce Tech (QQQ) | ✅Yes / ❌No / 🟡Watch | [reason] |
| Increase Real Assets (Energy/LNG) | ✅Yes / ❌No / 🟡Watch | [reason] |
| Add Gold (GLD) | ✅Yes / ❌No / 🟡Watch | [reason] |
| Add Defensives (XLU/Bonds) | ✅Yes / ❌No / 🟡Watch | [reason] |
| Reduce Risk Exposure | ✅Yes / ❌No / 🟡Watch | [reason] |
| USD / Cash Position | [specific advice] | [reason] |

---

**🔔 Re-evaluation Triggers:**
[List 2-3 key events that would require reassessment]

---
⏰ {date} Beijing Time · 🤖 AI Auto-Generated
"""


# ─────────────────────────────────────────────────────────────
#  API 调用（通用）
# ─────────────────────────────────────────────────────────────
def call_claude(messages: list, use_search: bool = False, max_retries: int = 3) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("未设置 ANTHROPIC_API_KEY 环境变量")

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "messages": messages,
    }
    if use_search:
        payload["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    if use_search:
        headers["anthropic-beta"] = "web-search-2025-03-05"

    for attempt in range(1, max_retries + 1):
        try:
            log.info(f"   🔍 API 调用 第 {attempt} 次...")
            resp = requests.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            full_text = "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
            if full_text.strip():
                log.info(f"   ✅ 返回成功，字符数: {len(full_text)}")
                return full_text
            log.warning(f"   ⚠️ 第 {attempt} 次：返回内容为空")
        except requests.exceptions.Timeout:
            log.warning(f"   ⚠️ 第 {attempt} 次：请求超时")
        except Exception as e:
            log.error(f"   ❌ 第 {attempt} 次：{e}")

        if attempt < max_retries:
            wait = 2 ** attempt * 30
            log.info(f"   等待 {wait}s 后重试...")
            time.sleep(wait)

    raise RuntimeError(f"Claude API 调用失败，已重试 {max_retries} 次")


def generate_cn_report(date_str: str) -> str:
    log.info("🇨🇳 生成中文报告（带实时搜索）...")
    return call_claude(
        messages=[{"role": "user", "content": PROMPT_CN.format(date=date_str)}],
        use_search=True
    )


def generate_en_report(date_str: str, cn_report: str) -> str:
    log.info("🇺🇸 生成英文报告（翻译中文数据，不再搜索）...")
    return call_claude(
        messages=[{"role": "user", "content": PROMPT_EN.format(date=date_str, cn_report=cn_report)}],
        use_search=False
    )


# ─────────────────────────────────────────────────────────────
#  推送函数
# ─────────────────────────────────────────────────────────────
def _split_chunks(report: str) -> list:
    sections = re.split(r'\n---+\n', report)
    chunks, current = [], ""
    for s in sections:
        if len(current) + len(s) + 5 < 3800:
            current += s + "\n---\n"
        else:
            if current.strip():
                chunks.append(current.strip())
            current = s + "\n---\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks or [report[:3800]]


def push_serverchan(title: str, content: str) -> bool:
    send_key = Config.SERVERCHAN_SENDKEY
    if not send_key:
        return False
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{send_key}.send",
            data={"title": title, "desp": content},
            timeout=15
        )
        ok = resp.json().get("code") == 0
        log.info(f"   Server酱: {'✅' if ok else '❌'} {title[:30]}")
        return ok
    except Exception as e:
        log.error(f"   Server酱异常: {e}")
        return False


def push_wecom(report: str) -> bool:
    webhook_url = Config.WECOM_WEBHOOK_URL
    if not webhook_url:
        return False
    chunks = _split_chunks(report)
    success = True
    for i, chunk in enumerate(chunks):
        try:
            resp = requests.post(
                webhook_url,
                json={"msgtype": "markdown", "markdown": {"content": chunk}},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            ok = resp.json().get("errcode") == 0
            log.info(f"   企业微信段落 {i+1}/{len(chunks)}: {'✅' if ok else '❌'}")
            if not ok:
                success = False
        except Exception as e:
            log.error(f"   企业微信异常: {e}")
            success = False
        time.sleep(0.5)
    return success


def push_wxpusher(title: str, content: str) -> bool:
    app_token = Config.WXPUSHER_APP_TOKEN
    uids = Config.WXPUSHER_UIDS
    if not app_token or not uids:
        return False
    try:
        resp = requests.post(
            "https://wxpusher.zjiecode.com/api/send/message",
            json={"appToken": app_token, "content": content.replace('\n', '<br>'),
                  "summary": title, "contentType": 2, "uids": uids},
            timeout=15
        )
        ok = resp.json().get("success", False)
        log.info(f"   WxPusher: {'✅' if ok else '❌'} {title[:30]}")
        return ok
    except Exception as e:
        log.error(f"   WxPusher异常: {e}")
        return False


def push_one_report(report: str, title: str, lang_label: str):
    """推送单份报告到所有已配置渠道。"""
    log.info(f"\n📲 推送 {lang_label} 版: {title}")
    if Config.SERVERCHAN_SENDKEY:
        push_serverchan(title, report)
    if Config.WECOM_WEBHOOK_URL:
        push_wecom(report)
    if Config.WXPUSHER_APP_TOKEN:
        push_wxpusher(title, report)
    time.sleep(3)  # 两条消息之间留间隔，避免顺序混乱


# ─────────────────────────────────────────────────────────────
#  主流程
# ─────────────────────────────────────────────────────────────
def run_market_monitor(dry_run: bool = False) -> dict:
    tz_cst  = timezone(timedelta(hours=8))
    now     = datetime.now(tz_cst)
    date_cn = now.strftime("%Y年%m月%d日")
    date_en = now.strftime("%B %d, %Y")

    log.info("=" * 60)
    log.info("📌 市场结构监控任务启动（中英双语版）")
    log.info(f"   时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log.info("=" * 60)

    # Step 1: 中文报告（带 Web Search）
    log.info("\n🤖 Step 1/3: 生成中文报告（实时搜索）...")
    cn_report = generate_cn_report(date_cn)
    log.info(f"   预览: {cn_report[:200]}...\n")

    # Step 2: 英文报告（基于中文翻译，不再搜索）
    log.info("\n⏳ 等待 120 秒，避免 API 速率限制...")
    time.sleep(120)
    log.info("\n🤖 Step 2/3: 生成英文报告（翻译）...")
    en_report = generate_en_report(date_en, cn_report)
    log.info(f"   预览: {en_report[:200]}...\n")

    if dry_run:
        log.info("\n🔍 [Dry Run] 完整报告如下（不推送）：")
        log.info("\n" + "━"*50 + " 中文版 " + "━"*50)
        log.info(cn_report)
        log.info("\n" + "━"*50 + " English " + "━"*50)
        log.info(en_report)
        return {"cn": cn_report, "en": en_report}

    # Step 3: 推送（先中文，再英文）
    log.info("\n📲 Step 3/3: 推送到微信...")
    push_one_report(cn_report, f"📌 市场结构监控（中文）· {date_cn}", "中文")
    push_one_report(en_report, f"📌 Market Monitor (EN) · {date_en}", "英文")

    # 保存到网页
    try:
        save_monitor(monitor_cn=cn_report, monitor_en=en_report)
        log.info("🌐 监控数据已保存到网页")
    except Exception as e:
        log.warning(f"⚠️  网页数据保存失败: {e}")

    log.info("\n" + "=" * 60)
    log.info("✅ 市场监控完成 — 中英双语已推送")
    log.info("=" * 60)

    return {"cn": cn_report, "en": en_report}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    run_market_monitor(dry_run="--dry-run" in sys.argv)
