#!/usr/bin/env python3
"""
Lambda Finance MCP 客户端 — AI 新闻拉取
每次调用流程：initialize → get session_id → tool calls
"""

import json
import os
import logging
import requests
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

_URL   = "https://www.lambdafin.com/mcp/"
_TOKEN = os.environ.get("LAMBDA_FINANCE_TOKEN", "")

# 重点关注的 AI / 半导体 / 科技持仓 ticker
_AI_TICKERS = ["NVDA", "GOOG", "MSFT", "META", "PLTR", "ASML", "AMD", "AVGO", "COHR", "NBIS", "ANET"]

# 标题关键词打分（大写匹配）
_AI_KEYWORDS = [
    ("artificial intelligence", 4), ("ai model", 4), ("large language model", 4),
    ("llm", 3), ("gpu", 3), ("nvidia", 3), ("semiconductor", 3), ("chips act", 3),
    ("generative ai", 4), ("openai", 3), ("anthropic", 3), ("data center", 2),
    ("machine learning", 2), ("ai chip", 4), ("inference", 2), ("training", 2),
    ("transformer", 2), ("foundation model", 3), ("ai spending", 3), ("capex", 2),
]


# ─── MCP 客户端 ─────────────────────────────────────────────────────────────

_HEADERS_BASE = {
    "Content-Type": "application/json",
    "Accept":       "application/json, text/event-stream",
}


def _post(body: dict, session_id: str | None = None, token: str = "") -> tuple[dict | None, str | None]:
    headers = dict(_HEADERS_BASE)
    headers["Authorization"] = f"Bearer {token}"
    if session_id:
        headers["mcp-session-id"] = session_id
    try:
        r = requests.post(_URL, json=body, headers=headers, timeout=8)
        sid = r.headers.get("mcp-session-id")
        for line in r.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:]), sid
    except Exception as e:
        log.debug(f"Lambda POST error: {e}")
    return None, None


def _init(token: str) -> str | None:
    resp, sid = _post({
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "daily-brief", "version": "1.0"},
        }
    }, token=token)
    return sid


def _tool(name: str, args: dict, sid: str, token: str) -> str:
    resp, _ = _post(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": name, "arguments": args}},
        session_id=sid, token=token
    )
    if not resp:
        return ""
    content = resp.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        return content[0]["text"]
    return ""


# ─── 新闻拉取与过滤 ──────────────────────────────────────────────────────────

def _ai_score(title: str) -> int:
    t = title.lower()
    score = 0
    for kw, pts in _AI_KEYWORDS:
        if kw in t:
            score += pts
    return score


def _parse_articles(raw: str) -> list[dict]:
    """从 Lambda 返回的 JSON 字符串解析文章列表。"""
    if not raw or raw.startswith("{") and "error" in raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # search_news returns {"results": [...]} or just a list
            for key in ("results", "articles", "news", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
    except Exception:
        pass
    return []


def fetch_ai_news(top_n: int = 10) -> list[dict]:
    """
    从 Lambda Finance 拉取 AI 相关新闻，筛选出最重要的 top_n 条。
    返回 list of {"title": str, "url": str, "source": str, "published": str}
    """
    token = _TOKEN
    if not token:
        log.error("❌ LAMBDA_FINANCE_TOKEN 未设置，跳过 Lambda 新闻")
        return []
    log.info(f"   LAMBDA_FINANCE_TOKEN 已设置（前8位: {token[:8]}...）")

    sid = _init(token)
    if not sid:
        log.error("❌ Lambda Finance 初始化失败（_init 返回 None），检查 token 或网络")
        return []
    log.info(f"   session_id: {sid[:16]}...")

    log.info("🔗 Lambda Finance 会话已建立，拉取 AI 新闻...")
    all_articles: list[dict] = []
    seen_urls: set[str] = set()

    # 1. 搜索 AI 关键词
    for query in ["artificial intelligence semiconductor", "AI chip GPU datacenter"]:
        raw = _tool("search_news", {"query": query, "limit": 20}, sid, token)
        for a in _parse_articles(raw):
            url = a.get("url") or a.get("link", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_articles.append(a)

    # 2. 按持仓 ticker 拉最新新闻
    for ticker in _AI_TICKERS:
        raw = _tool("get_news", {"symbol": ticker, "limit": 3, "latest": True}, sid, token)
        for a in _parse_articles(raw):
            url = a.get("url") or a.get("link", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_articles.append(a)

    # 3. 通用市场新闻（过滤 AI 相关）
    raw = _tool("get_news", {"limit": 20, "latest": True}, sid, token)
    for a in _parse_articles(raw):
        url = a.get("url") or a.get("link", "")
        title = a.get("title", "")
        if url and url not in seen_urls and _ai_score(title) >= 2:
            seen_urls.add(url)
            all_articles.append(a)

    log.info(f"   Lambda 原始文章: {len(all_articles)} 条")

    if not all_articles:
        return []

    # 4. 打分排序
    def sort_key(a):
        title = a.get("title", "")
        score = _ai_score(title)
        # 优先今日文章
        pub = a.get("publishedDate") or a.get("date") or ""
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        if pub.startswith(today):
            score += 2
        return score

    ranked = sorted(all_articles, key=sort_key, reverse=True)

    # 5. 标准化输出格式，只取正分文章
    result = []
    for a in ranked:
        title  = a.get("title", "").strip()
        url    = a.get("url") or a.get("link", "")
        source = a.get("site") or a.get("source") or a.get("publisher", "Lambda")
        pub    = a.get("publishedDate") or a.get("date") or ""
        if not title or not url:
            continue
        if _ai_score(title) < 1:  # 过滤完全无关文章
            continue
        result.append({"title": title, "url": url, "source": source, "published": pub[:10]})
        if len(result) >= top_n:
            break

    log.info(f"   ✅ 筛选后 AI 新闻: {len(result)} 条")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    articles = fetch_ai_news(10)
    for i, a in enumerate(articles, 1):
        print(f"{i:2d}. [{a['source']}] {a['title'][:80]}")
        print(f"    {a['url'][:70]}")
