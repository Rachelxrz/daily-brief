#!/usr/bin/env python3
"""
网页数据写入器 - 把每日报告保存到 docs/data.json
包含 AI 洞察生成
"""

import json
import os
import requests
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

DOCS_DIR  = Path(__file__).parent / "docs"
DATA_FILE = DOCS_DIR / "data.json"
MAX_DAYS  = 30

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL   = "claude-sonnet-4-6"

CATEGORY_CN = {
    "finance":    "📈 金融财经",
    "social":     "📱 自媒体精选",
    "health":     "🏥 健康医疗",
    "philosophy": "🧠 心理·哲学",
    "wellness":   "🧠 健康·心理·美学",  # 旧格式兼容
}
CATEGORY_EN = {
    "finance":    "📈 Finance & Markets",
    "social":     "📱 Tech & Media",
    "health":     "🏥 Health & Medicine",
    "philosophy": "🧠 Psychology & Philosophy",
    "wellness":   "🧠 Health & Wellness",
}

_ALL_CAT_ORDER = ["finance", "health", "philosophy", "social", "wellness"]


def _today_et() -> str:
    """用美东时间（ET）确定数据日期键，与 signal_advisor 保持一致。
    避免 UTC 16:00 后运行的 job 按 CST 跨到次日，产生只有部分数据的新日期键。"""
    try:
        import pytz
        return datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")

def _fetch_lambda_ai_news() -> list[dict]:
    """静默拉取 Lambda Finance AI 新闻，失败返回空列表。"""
    try:
        from lambda_news import fetch_ai_news
        return fetch_ai_news(top_n=15)
    except Exception as e:
        log.warning(f"⚠️ Lambda 新闻拉取失败，跳过: {e}")
        return []


def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_data(data: dict):
    DOCS_DIR.mkdir(exist_ok=True)
    if len(data) > MAX_DAYS:
        keys = sorted(data.keys())
        for old_key in keys[:len(data) - MAX_DAYS]:
            del data[old_key]
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log.info(f"✅ 已写入 {DATA_FILE}，共 {len(data)} 天数据")


# ─── 近 N 天去重 ───────────────────────────────────────────
import re as _re_dd


def _norm_url(u: str) -> str:
    """URL 归一化：去掉 query/fragment/末尾斜杠，小写。"""
    u = (u or "").strip()
    if not u:
        return ""
    u = u.split("#")[0].split("?")[0].rstrip("/")
    return u.lower()


def _norm_title(t: str) -> str:
    """标题归一化：仅保留字母数字和中日韩字符，小写，取前 80 字符。"""
    return _re_dd.sub(r"[^0-9a-z一-鿿]", "", (t or "").lower())[:80]


def _recent_seen_keys(days: int = 3) -> set:
    """收集之前 days 天（严格早于今天 ET）已出现过的新闻 key（url + 标题）。"""
    data = load_data()
    try:
        today = _today_et()
    except Exception:
        today = datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")
    prev_dates = [d for d in sorted(data.keys(), reverse=True) if d < today][:days]
    seen = set()
    for d in prev_dates:
        for cat, items in (data[d].get("news_cards", {}) or {}).items():
            for it in (items or []):
                nu = _norm_url(it.get("url"))
                if nu:
                    seen.add("u:" + nu)
                nt = _norm_title(it.get("title") or it.get("title_cn"))
                if nt:
                    seen.add("t:" + nt)
    log.info(f"🧹 近{days}天去重：参考日期 {prev_dates}，已知 {len(seen)} 个 key")
    return seen


def filter_recent_duplicates(news_data: dict, days: int = 3) -> dict:
    """剔除今天抓取中、在之前 days 天已出现过的新闻（url 或标题命中即视为重复）。
    同时去掉本次抓取内部的跨类别重复。"""
    seen = _recent_seen_keys(days)
    run_seen: set = set()
    out: dict = {}
    removed = 0
    for cat, items in news_data.items():
        kept = []
        for it in (items or []):
            keys = set()
            nu = _norm_url(it.get("url"))
            if nu:
                keys.add("u:" + nu)
            nt = _norm_title(it.get("title"))
            if nt:
                keys.add("t:" + nt)
            if (keys & seen) or (keys & run_seen):
                removed += 1
                continue
            run_seen |= keys
            kept.append(it)
        out[cat] = kept
    total = sum(len(v) for v in out.values())
    log.info(f"🧹 近{days}天去重完成：移除 {removed} 条重复，保留 {total} 条")
    return out


def _call_claude(prompt: str, max_tokens: int = 3000) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.error("❌ ANTHROPIC_API_KEY 未设置，跳过 Claude 调用")
        return ""
    log.info(f"   → Claude 调用 model={ANTHROPIC_MODEL} max_tokens={max_tokens} prompt_len={len(prompt)}")
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    for attempt in range(1, 4):
        try:
            resp = requests.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=90)
            log.info(f"   ← HTTP {resp.status_code}")
            if resp.status_code not in (200, 201):
                log.warning(f"   ⚠️ 非200响应: {resp.text[:300]}")
            resp.raise_for_status()
            data = resp.json()
            text = "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text")
            if text.strip():
                log.info(f"   ✅ Claude 返回 {len(text)} 字符")
                return text.strip()
            log.warning("   ⚠️ Claude 返回空内容")
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            log.warning(f"   ⚠️ Claude 调用第{attempt}次 HTTP {status} 错误: {e}")
        except Exception as e:
            log.warning(f"   ⚠️ Claude 调用第{attempt}次失败: {e}")
        if attempt < 3:
            wait = 60 if attempt == 1 else 90  # 速率限制需要足够等待时间
            log.info(f"   等待 {wait}s 后重试...")
            time.sleep(wait)
    return ""


def _parse_json(text: str):
    """健壮的 JSON 解析，处理 markdown 代码块和多余文字。"""
    clean = text.strip()
    if "```" in clean:
        parts = clean.split("```")
        for p in parts:
            p2 = p.strip()
            if p2.startswith("json"):
                p2 = p2[4:].strip()
            if p2.startswith("{"):
                clean = p2
                break
    start = clean.find("{")
    end   = clean.rfind("}")
    if start != -1 and end != -1:
        clean = clean[start:end+1]
    return json.loads(clean)


def _parse_json_array(text: str) -> list:
    """从 Claude 返回中提取 JSON 数组。"""
    raw = text.strip() if text else ""
    if "```" in raw:
        for part in raw.split("```"):
            p = part.strip().lstrip("json").strip()
            if p.startswith("["):
                raw = p
                break
    start = raw.find("[")
    end   = raw.rfind("]")
    if start != -1 and end != -1:
        return json.loads(raw[start:end+1])
    return []


def generate_news_with_insights(news_data: dict) -> tuple:
    """
    拆成两次轻量 Claude 调用：
    1. 标题翻译 → 简单字符串数组（小输出，几乎不会失败）
    2. 全局洞察 → 独立调用（可选，失败不影响标题）
    返回 (cn_report, en_report)
    """
    tz_cst  = timezone(timedelta(hours=8))
    date_cn = datetime.now(tz_cst).strftime("%Y年%m月%d日")
    date_en = datetime.now(tz_cst).strftime("%B %d, %Y")

    # ── 拉取 Lambda AI 新闻并预先生成区块 ──────────────────
    lambda_articles = _fetch_lambda_ai_news()[:10]  # 限定10条
    lambda_block_cn = ""
    lambda_block_en = ""
    lambda_parsed: list[dict] = []
    if lambda_articles:
        n = len(lambda_articles)
        articles_text = "\n".join(
            f"{i+1}. {a['title']}"
            + (f"\n   {a['summary'][:300]}" if a.get("summary") else "")
            for i, a in enumerate(lambda_articles)
        )
        lambda_prompt = (
            f"For each of the following {n} AI/tech news articles, write a Chinese title and a 3-5 sentence investment analysis in Chinese.\n"
            f"Output EXACTLY {n} sections separated by ---\n"
            "Section format:\n"
            "Line 1: Chinese title (≤20 chars, no quotes)\n"
            "Lines 2+: 3-5 sentences of investment analysis in Chinese (explain what happened, why it matters for investors, and any trading implications)\n"
            "No JSON, no numbering, no extra text.\n\n"
            f"Articles:\n{articles_text}"
        )
        log.info("🤖 Lambda AI 新闻中文化（3-5句综述）...")
        lambda_raw = _call_claude(lambda_prompt, max_tokens=2000)
        if lambda_raw:
            blocks = [b.strip() for b in lambda_raw.split("---") if b.strip()]
            for block in blocks:
                lines = [l.strip() for l in block.splitlines() if l.strip()]
                lambda_parsed.append({
                    "title_cn":    lines[0] if lines else "",
                    "analysis_cn": "\n".join(lines[1:]) if len(lines) > 1 else "",
                })

        cn_lines = ["\n## 🤖 AI前沿（Lambda Finance）\n"]
        en_lines = ["\n## 🤖 AI Focus (Lambda Finance)\n"]
        for i, a in enumerate(lambda_articles):
            info     = lambda_parsed[i] if i < len(lambda_parsed) else {}
            title_cn = info.get("title_cn") or a["title"][:25]
            analysis = info.get("analysis_cn", "")
            url      = a.get("url", "")
            src      = a.get("source", "")
            pub      = a.get("published", "")
            cn_lines.append(f"**[{title_cn}]({url})**")
            if analysis:
                cn_lines.append(f"\n{analysis}\n")
            cn_lines.append(f"*{src} · {pub}*\n")
            en_lines.append(f"**[{a['title']}]({url})**")
            if a.get("summary"):
                en_lines.append(f"\n{a['summary'][:350]}\n")
            en_lines.append(f"*{src} · {pub}*\n")
        lambda_block_cn = "\n".join(cn_lines)
        lambda_block_en = "\n".join(en_lines)

        # Lambda 调用完毕，等待速率窗口恢复（>60s 确保 rolling window 清空），再翻译普通新闻
        log.info("⏳ 等待 70s（速率限制缓冲，覆盖 60s rolling window）...")
        time.sleep(70)

    # ── 构建扁平新闻列表（按类别顺序）─────────────────────
    cat_order = [c for c in _ALL_CAT_ORDER if news_data.get(c)]
    flat_items = []   # [(cat, item), ...]
    for cat in cat_order:
        for item in news_data.get(cat, []):
            flat_items.append((cat, item))

    articles_text_reg = "\n".join(
        f"{i+1}. {item['title']}"
        + (f"\n   {item.get('summary','')[:200]}" if item.get("summary") else "")
        for i, (_, item) in enumerate(flat_items)
    )

    # ── 调用 1：标题翻译 + 2-3句综述 ──────────────────────────
    # 按分类分批调用：单次只翻译一个分类（≤10 条），确保 max_tokens 充足。
    # 这样即使某个分类被截断，也只影响该分类，不会像“一次翻译全部”那样
    # 在 token 用尽后把后续所有分类的中文全部丢失。
    import re as _re

    def _translate_batch(items: list) -> list:
        """翻译一批新闻，返回与 items 等长的 [{"title","summary"}, ...]。"""
        if not items:
            return []
        body = "\n".join(
            f"{i+1}. {it['title']}"
            + (f"\n   {it.get('summary','')[:200]}" if it.get("summary") else "")
            for i, it in enumerate(items)
        )
        prompt = (
            f"For each of the following {len(items)} news articles, provide a Chinese title and a 2-3 sentence Chinese summary.\n"
            f"Output EXACTLY {len(items)} sections separated by ---\n"
            "Section format:\n"
            "Line 1: concise Chinese title (≤25 chars, no quotes)\n"
            "Lines 2-4: 2-3 sentences of Chinese summary and analysis\n"
            "No JSON, no numbering, no extra text.\n\n"
            f"Articles:\n{body}"
        )
        raw = _call_claude(prompt, max_tokens=3000)
        parsed = []
        if raw:
            for block in [b.strip() for b in raw.split("---") if b.strip()]:
                lines = [l.strip() for l in block.splitlines() if l.strip()]
                title = _re.sub(r'^\d+[\.\)]\s*', '', lines[0]) if lines else ""
                summary = "\n".join(lines[1:]) if len(lines) > 1 else ""
                parsed.append({"title": title, "summary": summary})
        # 对齐 items 长度：不足补空、超出截断，保证下游按序号索引不错位
        while len(parsed) < len(items):
            parsed.append({"title": "", "summary": ""})
        return parsed[:len(items)]

    cn_sections = []  # 扁平，与 flat_items 顺序对齐
    for ci, cat in enumerate(cat_order):
        items = news_data.get(cat, [])
        log.info(f"🤖 翻译分类 {cat}（{len(items)} 条）...")
        cn_sections.extend(_translate_batch(items))
        if ci < len(cat_order) - 1:
            time.sleep(20)  # 分类之间留间隔，缓冲 API 速率限制
    got = sum(1 for s in cn_sections if s["title"] or s["summary"])
    log.info(f"   ✅ 翻译+综述完成: {got}/{len(flat_items)} 条")
    cn_titles = [s["title"] for s in cn_sections]  # backward compat fallback

    # 翻译完毕，等待速率窗口恢复
    log.info("⏳ 等待 30s（速率限制缓冲）...")
    time.sleep(30)

    # ── 调用 2：全局洞察（节标记格式，完全避开 JSON）──────
    insights_prompt = (
        f"Based on today's news ({date_en}), write actionable insights.\n"
        "Use EXACTLY this format with section markers (no JSON, no quotes):\n\n"
        "===INVESTMENT_CN===\n投资洞察1\n投资洞察2\n投资洞察3\n"
        "===INVESTMENT_EN===\nInsight 1\nInsight 2\nInsight 3\n"
        "===HEALTH_CN===\n健康洞察1\n健康洞察2\n健康洞察3\n"
        "===HEALTH_EN===\nInsight 1\nInsight 2\nInsight 3\n\n"
        f"News headlines:\n{articles_text_reg[:1500]}"
    )
    log.info("🤖 调用 Claude 生成全局洞察...")
    insights_raw = _call_claude(insights_prompt, max_tokens=600)

    def _parse_sections(text: str) -> dict:
        result = {}
        current = None
        for line in (text or "").splitlines():
            line = line.strip()
            if line.startswith("===") and line.endswith("==="):
                current = line.strip("=").strip()
                result[current] = []
            elif current and line:
                result[current].append(line)
        return result

    sections = _parse_sections(insights_raw)
    insights = {
        "investment_cn": sections.get("INVESTMENT_CN", [])[:3],
        "investment_en": sections.get("INVESTMENT_EN", [])[:3],
        "health_cn":     sections.get("HEALTH_CN", [])[:3],
        "health_en":     sections.get("HEALTH_EN", [])[:3],
    }
    log.info(f"   洞察解析: inv_cn={len(insights['investment_cn'])} health_cn={len(insights['health_cn'])}")

    # ── 生成中文版 ──────────────────────────────────────────
    cn = [f"# 📰 每日智识简报（中文）", f"### {date_cn}\n"]
    if lambda_block_cn:
        cn.append(lambda_block_cn)

    idx = 0
    for cat in cat_order:
        items = news_data.get(cat, [])
        if not items:
            continue
        cn.append(f"\n## {CATEGORY_CN.get(cat, cat)}\n")
        for item in items:
            sec = cn_sections[idx] if idx < len(cn_sections) else {}
            title_cn   = sec.get("title") or (cn_titles[idx] if idx < len(cn_titles) else item["title"])
            summary_cn = sec.get("summary", "")
            url = item.get("url", "")
            cn.append(f"**{'['+title_cn+']('+url+')' if url else title_cn}**")
            if summary_cn:
                cn.append(f"\n{summary_cn}\n")
            idx += 1

    inv_cn    = insights.get("investment_cn", [])
    health_cn = insights.get("health_cn", [])
    if inv_cn or health_cn:
        cn.append("\n---\n## 💡 今日洞察\n")
        if inv_cn:
            cn.append("**📈 投资建议**")
            for s in inv_cn[:3]:
                cn.append(f"- {s}")
            cn.append("")
        if health_cn:
            cn.append("**🧠 健康建议**")
            for s in health_cn[:3]:
                cn.append(f"- {s}")

    # ── 生成英文版 ──────────────────────────────────────────
    en = [f"# 📰 Daily Intelligence Brief", f"### {date_en}\n"]
    if lambda_block_en:
        en.append(lambda_block_en)

    for cat in cat_order:
        items = news_data.get(cat, [])
        if not items:
            continue
        en.append(f"\n## {CATEGORY_EN.get(cat, cat)}\n")
        for item in items:
            url     = item.get("url", "")
            title   = item["title"]
            summary = item.get("summary", "")
            en.append(f"**{'['+title+']('+url+')' if url else title}**")
            if summary:
                en.append(f"\n{summary[:300]}\n")

    inv_en    = insights.get("investment_en", [])
    health_en = insights.get("health_en", [])
    if inv_en or health_en:
        en.append("\n---\n## 💡 Today's Insights\n")
        if inv_en:
            en.append("**📈 Investment**")
            for s in inv_en[:3]:
                en.append(f"- {s}")
            en.append("")
        if health_en:
            en.append("**🧠 Health & Wellness**")
            for s in health_en[:3]:
                en.append(f"- {s}")

    # ── 构建结构化 news_cards（供前端卡片布局使用）──────────
    news_cards: dict = {}
    card_idx = 0
    for cat in cat_order:
        items = news_data.get(cat, [])
        if not items:
            continue
        section_items = []
        for rank, item in enumerate(items, 1):
            sec = cn_sections[card_idx] if card_idx < len(cn_sections) else {}
            section_items.append({
                "rank":        rank,
                "title":       item.get("title", ""),
                "title_cn":    sec.get("title", ""),
                "url":         item.get("url", ""),
                "source":      item.get("source", ""),
                "time":        item.get("time", ""),
                "analysis_cn": sec.get("summary", ""),
                "analysis_en": item.get("summary", ""),
            })
            card_idx += 1
        news_cards[cat] = section_items

    # Lambda AI 新闻独立卡片区（key = "ai"）
    if lambda_articles:
        ai_cards = []
        for i, a in enumerate(lambda_articles, 1):
            info = lambda_parsed[i - 1] if i - 1 < len(lambda_parsed) else {}
            ai_cards.append({
                "rank":        i,
                "title":       a.get("title", ""),
                "title_cn":    info.get("title_cn", ""),
                "url":         a.get("url", ""),
                "source":      a.get("source", "Lambda Finance"),
                "time":        a.get("published", ""),
                "analysis_cn": info.get("analysis_cn", ""),
                "analysis_en": a.get("summary", ""),
            })
        news_cards["ai"] = ai_cards

    return "\n".join(cn), "\n".join(en), news_cards


def translate_for_wechat(news_data: dict) -> dict:
    """
    调用 Claude 把新闻标题和摘要翻译成中文，返回结构化数据供微信推送使用。
    格式与原始 news_data 相同，但 title/summary 替换为中文。

    按分类分批调用，并改用 --- 分节文本（不再用一次性 JSON）：
    旧实现把全部 ~40 条打包进一次 max_tokens=3000 的 JSON 调用，token 一旦用尽
    JSON 就被截断 → 解析整体失败 → main.py 捕获后跳过“整个”微信新闻推送。
    分批 + 分节文本后，单批 ≤10 条不会截断，且即使某段缺失也只影响该条，
    不会让整条新闻推送流程失败。
    """
    import re as _re

    def _translate_cat(items: list) -> list:
        """翻译一个分类，返回与 items 等长的 [{"title","summary"}, ...]。"""
        if not items:
            return []
        body = "\n".join(
            f"{i+1}. [{it.get('source','')}] {it['title']}"
            + (f"\n   摘要原文: {it['summary'][:150]}" if it.get('summary') else "")
            for i, it in enumerate(items)
        )
        prompt = (
            f"将以下 {len(items)} 条新闻翻译成简洁专业的中文。\n"
            f"严格输出 {len(items)} 段，用 --- 分隔，顺序与输入完全一致。\n"
            "每段格式：\n"
            "第一行：中文标题（不加引号、不加编号）\n"
            "后续行：中文摘要，2-3句话\n"
            "只输出翻译，不要 JSON、不要编号、不要多余说明。\n\n"
            f"新闻列表：\n{body}"
        )
        raw = _call_claude(prompt, max_tokens=3000)
        out = []
        if raw:
            for block in [b.strip() for b in raw.split("---") if b.strip()]:
                lines = [l.strip() for l in block.splitlines() if l.strip()]
                title = _re.sub(r'^\d+[\.\)]\s*', '', lines[0]) if lines else ""
                summary = "\n".join(lines[1:]) if len(lines) > 1 else ""
                out.append({"title": title, "summary": summary})
        # 对齐长度，保证按序号合并回原数据时不错位
        while len(out) < len(items):
            out.append({"title": "", "summary": ""})
        return out[:len(items)]

    cats = list(news_data.keys())
    translated = {}
    any_cn = False
    for ci, cat in enumerate(cats):
        orig_items = news_data.get(cat, [])
        log.info(f"🤖 翻译微信推送分类 {cat}（{len(orig_items)} 条）...")
        tr = _translate_cat(orig_items)
        merged = []
        for i, orig in enumerate(orig_items):
            item = orig.copy()
            t = tr[i] if i < len(tr) else {}
            if t.get("title"):
                item['title'] = t['title']
                any_cn = True
            if t.get("summary"):
                item['summary'] = t['summary']
            merged.append(item)
        translated[cat] = merged
        if ci < len(cats) - 1:
            time.sleep(20)  # 分类之间留间隔，缓冲 API 速率限制

    # 只有当“全部”分类都翻译失败时才报错（拒绝发送纯英文原文）；
    # 正常情况下分批后每条都能拿到中文，微信推送不会再被整体跳过。
    if not any_cn:
        raise RuntimeError("Claude 翻译全部失败（返回空内容），请检查 ANTHROPIC_API_KEY 是否已在 GitHub Secrets 中配置")

    log.info("✅ 微信推送新闻翻译完成")
    return translated


def _format_plain_cn(news_data: dict, date_cn: str) -> str:
    lines = [f"# 📰 每日智识简报（中文）", f"### {date_cn}\n"]
    for cat, items in news_data.items():
        lines.append(f"\n## {CATEGORY_CN.get(cat, cat)}\n")
        for item in items:
            lines.append(f"- 【{item['source']}】{item['title']}")
    return "\n".join(lines)


def _format_plain_en(news_data: dict, date_en: str) -> str:
    lines = [f"# 📰 Daily Intelligence Brief", f"### {date_en}\n"]
    for cat, items in news_data.items():
        lines.append(f"\n## {CATEGORY_EN.get(cat, cat)}\n")
        for item in items:
            lines.append(f"- [{item['source']}] {item['title']}")
    return "\n".join(lines)


def save_news(news_data: dict = None, news_cn: str = None, news_en: str = None):
    tz_cst = timezone(timedelta(hours=8))
    today  = _today_et()

    news_cards: dict = {}
    if news_data is not None:
        news_cn, news_en, news_cards = generate_news_with_insights(news_data)

    data = load_data()
    if today not in data:
        data[today] = {}
    data[today]["updated"] = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M CST")
    existing = data[today].get("news", {})
    data[today]["news"] = {
        "cn": news_cn if news_cn else existing.get("cn", ""),
        "en": news_en if news_en else existing.get("en", ""),
    }
    if news_cards:
        data[today]["news_cards"] = news_cards
    save_data(data)
    log.info(f"📰 新闻简报已保存: {today}")


def save_monitor(monitor_cn: str, monitor_en: str):
    tz_cst = timezone(timedelta(hours=8))
    today  = _today_et()
    data = load_data()
    if today not in data:
        data[today] = {}
    data[today]["updated"] = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M CST")
    data[today]["monitor"] = {"cn": monitor_cn, "en": monitor_en}
    save_data(data)
    log.info(f"📌 市场监控已保存: {today}")


def save_congress(congress_data: dict):
    tz_cst = timezone(timedelta(hours=8))
    today  = _today_et()
    data = load_data()
    if today not in data:
        data[today] = {}
    data[today]["updated"] = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M CST")
    data[today]["congress"] = congress_data
    save_data(data)
    log.info(f"🏛 国会信号已保存: {today}")


def save_wheel(wheel_data: dict):
    tz_cst = timezone(timedelta(hours=8))
    today  = _today_et()
    data = load_data()
    if today not in data:
        data[today] = {}
    data[today]["updated"] = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M CST")
    data[today]["wheel"] = wheel_data
    save_data(data)
    log.info(f"🎡 Wheel 数据已保存: {today}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    save_monitor("# 测试中文", "# Test English")
