"""Local MCP server for GEO question discovery."""
import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
import os
import time
from typing import Any, Literal
from uuid import UUID

import httpx
from mcp.server.fastmcp import FastMCP

from .core import normalize

mcp = FastMCP("geo_research")
limits = OrderedDict()
ZHIHU = "https://developer.zhihu.com/api/v1/content/zhihu_search"
BOCHA = "https://api.bochaai.com/v1/web-search"
KEYS = {"zhihu": "ZHIHU_ACCESS_SECRET", "xiaohongshu": "BOCHA_API_KEY"}


async def request(client, source, query, count, key):
    headers = {"Authorization": f"Bearer {key}"}
    if source == "zhihu":
        headers["X-Request-Timestamp"] = str(int(time.time()))
        headers["Content-Type"] = "application/json"
        return await client.get(ZHIHU, params={"Query": query, "Count": count}, headers=headers)
    payload = {"query": f"{query} site:xiaohongshu.com", "count": count, "summary": True}
    return await client.post(BOCHA, json=payload, headers=headers)


def unpack(source, response):
    if response.status_code in (401, 403):
        return "auth_error", []
    if response.status_code == 429:
        return "rate_limit", []
    if response.status_code >= 500:
        return "provider_error", []
    if not response.is_success:
        return "request_error", []
    try:
        body = response.json()
        code, field = ("Code", "Data") if source == "zhihu" else ("code", "data")
        status = str(body.get(code, ""))
        if source == "zhihu" and status in ("20001", "30001", "90001"):
            return {"20001": "auth_error", "30001": "rate_limit",
                    "90001": "provider_error"}[status], []
        if status != ("0" if source == "zhihu" else "200"):
            return "provider_error", []
        data = body[field]
        rows = data["Items"] if source == "zhihu" else data.get("webPages", {}).get("value", [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            return "invalid_response", []
        return "ok", rows
    except (ValueError, TypeError, AttributeError, KeyError):
        return "invalid_response", []


async def search_one(client, source, query, count, key, counters):
    status, rows = "budget_exhausted", []
    requests = 0
    for attempt in range(2):
        if counters[1] >= 30:
            break
        counters[1] += 1
        requests += 1
        try:
            response = await request(client, source, query, count, key)
            status, rows = unpack(source, response)
        except httpx.TimeoutException:
            status = "timeout"
        except httpx.RequestError:
            status = "network_error"
        if status not in ("timeout", "network_error", "provider_error"):
            break
        if attempt == 0:
            await asyncio.sleep(0.3)
    items = {}
    for row in rows:
        item = normalize(source, row, query)
        if item:
            item["fetched_at"] = datetime.now(timezone.utc).isoformat()
            items.setdefault(item["id"], item)
    if status == "ok" and not items:
        status = "empty"
    return {"query": query, "status": status, "count": min(len(items), count),
            "requests": requests}, list(items.values())[:count]


@mcp.tool(structured_output=True)
async def search_sources(run_id: UUID, source: Literal["zhihu", "xiaohongshu"],
                         queries: list[str], per_query_limit: int = 8) -> dict[str, Any]:
    """Search one source for up to four queries. Use the same UUID for one industry run."""
    words = list(dict.fromkeys(query.strip() for query in queries))
    if not 1 <= len(queries) <= 4 or any(not word or len(word) > 240 for word in words):
        raise ValueError("Provide 1–4 nonempty search queries of at most 240 characters.")
    if not 1 <= per_query_limit <= 8:
        raise ValueError("per_query_limit must be between 1 and 8.")
    key = os.environ.get(KEYS[source])
    if not key:
        return {"source": source, "status": "missing_credential", "items": [],
                "query_stats": [{"query": word, "status": "missing_credential",
                                 "count": 0, "requests": 0} for word in words]}
    counters = limits.setdefault(run_id, [0, 0])
    limits.move_to_end(run_id)
    if len(limits) > 256:
        limits.popitem(last=False)
    if counters[0] + len(words) > 24:
        return {"source": source, "status": "budget_exhausted", "items": [], "query_stats": []}
    counters[0] += len(words)
    async with httpx.AsyncClient(timeout=8) as client:
        # At most two in flight per batch.
        pairs = []
        for index in range(0, len(words), 2):
            pairs.extend(await asyncio.gather(*(
                search_one(client, source, word, per_query_limit, key, counters)
                for word in words[index:index + 2]
            )))
    query_stats = [stats for stats, _ in pairs]
    items = {item["id"]: item for _, found in pairs for item in found}
    states = {stats["status"] for stats in query_stats}
    return {"source": source, "status": next(iter(states)) if len(states) == 1 else "partial",
            "items": list(items.values()), "query_stats": query_stats}


@mcp.tool(structured_output=True)
async def search_xiaohongshu_browser(queries: list[str], per_query_limit: int = 5) -> dict[str, Any]:
    """Read visible Xiaohongshu notes in the project's local Chrome session."""
    from .xhs_browser import browser_search, validate_queries

    return await browser_search(validate_queries(queries, per_query_limit), per_query_limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
