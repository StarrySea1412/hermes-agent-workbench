"""Public web search tool backed by configurable external providers."""

import json
import os
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

META = {
    "source": "builtin",
    "runtime": "network",
    "notes": "Prefers Brave Search / SerpAPI when their keys are set; otherwise falls back to the keyless DuckDuckGo (ddgs) backend.",
}

SCHEMA = {
    "name": "web_search",
    "description": "Search public web information when the task needs fresh external context.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query to run.",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return. Defaults to 5.",
            },
        },
        "required": ["query"],
    },
}


def handle(args, context=None):
    del context

    query = (args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "Missing query."}

    try:
        top_k = int(args.get("top_k") or 5)
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(top_k, 10))

    brave_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    serpapi_key = os.getenv("SERPAPI_API_KEY", "").strip()

    try:
        if brave_key:
            results = _search_brave(query, top_k, brave_key)
            provider = "brave"
        elif serpapi_key:
            results = _search_serpapi(query, top_k, serpapi_key)
            provider = "serpapi"
        else:
            # 免 key 兜底：ddgs（DuckDuckGo）。未安装时报可操作的错误而不是哑失败。
            try:
                results = _search_ddgs(query, top_k)
                provider = "ddgs"
            except ImportError:
                return {
                    "ok": False,
                    "error": "No web search provider is configured. Set BRAVE_SEARCH_API_KEY or SERPAPI_API_KEY, or install the 'ddgs' package for keyless search.",
                }
    except Exception as exc:
        return {"ok": False, "error": f"Web search failed: {exc}"}

    return {
        "ok": True,
        "result": {
            "query": query,
            "provider": provider,
            "results": results,
        },
    }


def _search_ddgs(query, top_k):
    """免 key 的 DuckDuckGo 搜索，作为未配置商业 provider 时的兜底。"""
    from ddgs import DDGS

    raw = DDGS().text(query, max_results=top_k)
    return [
        {
            "title": item.get("title") or "",
            "url": item.get("href") or item.get("url") or "",
            "snippet": item.get("body") or item.get("description") or "",
        }
        for item in raw[:top_k]
    ]


def _search_brave(query, top_k, api_key):
    url = f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(query)}&count={top_k}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": "Hermes-Workbench/1.0",
        },
    )
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))

    items = payload.get("web", {}).get("results", [])
    return [
        {
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "snippet": item.get("description") or "",
        }
        for item in items[:top_k]
    ]


def _search_serpapi(query, top_k, api_key):
    url = (
        "https://serpapi.com/search.json"
        f"?engine=google&q={quote_plus(query)}&num={top_k}&api_key={quote_plus(api_key)}"
    )
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Hermes-Workbench/1.0",
        },
    )
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))

    items = payload.get("organic_results", [])
    return [
        {
            "title": item.get("title") or "",
            "url": item.get("link") or "",
            "snippet": item.get("snippet") or "",
        }
        for item in items[:top_k]
    ]
