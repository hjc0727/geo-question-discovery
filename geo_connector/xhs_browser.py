"""Read Xiaohongshu's visible search results in a dedicated local browser."""
import argparse
import asyncio
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Error, TimeoutError, async_playwright

from .core import clean, identity

HOME = "https://www.xiaohongshu.com/explore"
PROFILE = Path(__file__).resolve().parents[1] / ".xhs-browser"
SOURCE = "xiaohongshu"
METHOD = "xhs_browser"
ALLOWED_HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com", "rednote.com", "www.rednote.com"}
LINKS = 'a[href*="/explore/"], a[href*="/discovery/item/"], a[href*="/search_result/"]'
SEARCH = '#search-input-in-feeds, input[placeholder*="搜索"], input[type="search"], #search-input'
LOGIN = '.login-container:visible, .login-modal:visible, [role="dialog"]:has-text("扫码登录"):visible'
BLOCK = 'text=/访问受限|请求过于频繁|完成安全验证|请完成验证|Please verify/'
EMPTY = 'text=/没有找到相关|没有搜索结果|暂无搜索结果|未找到相关|No results found/'
DETAIL = '#detail-desc:visible, .note-content .desc:visible, .note-detail-mask .desc:visible'


def is_site(url):
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS


async def visible(page, selector):
    return await page.locator(selector).first.is_visible()


async def gate(page):
    path = urlsplit(page.url).path
    if path.startswith(("/captcha", "/verify")) or await visible(page, BLOCK):
        return "verification_required"
    if path.startswith("/login") or await visible(page, LOGIN):
        return "login_required"
    if not is_site(page.url):
        return "unexpected_page"
    return None


async def launch(chromium, profile):
    return await chromium.launch_persistent_context(
        profile, channel="chrome", headless=False, locale="zh-CN", timeout=10_000
    )


async def wait_for_search(page):
    try:
        await page.locator(SEARCH).filter(visible=True).first.wait_for(state="visible", timeout=7_000)
    except TimeoutError:
        return await gate(page) or "search_ui_unavailable"
    return await gate(page)


async def cards(page, selector, limit):
    # Read only visible DOM nodes. Search cards often contain a title but no body.
    return await page.locator(selector).evaluate_all(
        """(anchors, limit) => anchors.filter(a => a.getClientRects().length).slice(0, limit).map(a => {
            const card = a.closest('section, article, [class*="note-item"]') || a.parentElement;
            const title = card?.querySelector('.title, [class*="note-title"], h2, h3');
            const excerpt = card?.querySelector('.desc, [class*="description"]');
            return {href: a.href, title: title?.innerText || a.innerText || a.getAttribute('title') || '',
                    excerpt: excerpt?.innerText || ''};
        })""", limit
    )


def note_link(url):
    """Validate the site and note path, removing query data from the export."""
    if not is_site(url):
        return None
    parts = urlsplit(url)
    path = parts.path.replace("/search_result/", "/explore/", 1)
    public_url = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    key = identity(SOURCE, public_url)
    return (key, public_url) if key else None


async def read_detail(tab, href):
    try:
        response = await tab.goto(href, wait_until="domcontentloaded", timeout=5_000)
        if response and response.status in (403, 429):
            return "access_limited", "", ""
        status = await gate(tab)
        if status:
            return status, "", ""
        body = tab.locator(DETAIL).first
        await body.wait_for(state="visible", timeout=2_000)
        title = tab.locator('#detail-title:visible').first
        return None, clean(await title.inner_text()) if await title.is_visible() else "", clean(await body.inner_text())
    except TimeoutError:
        return await gate(tab), "", ""


async def search_query(page, detail, query, limit):
    try:
        response = await page.goto(HOME, wait_until="domcontentloaded", timeout=8_000)
        if response and response.status in (403, 429):
            return "access_limited", []
        status = await wait_for_search(page)
        if status:
            return status, []
        search = page.locator(SEARCH).filter(visible=True).first
        await search.fill(query, timeout=3_000)
        await search.press("Enter", timeout=3_000)
        # Confirm the search view before extracting, so Explore's feed cannot pass for results.
        await page.wait_for_url(lambda value: "/search_result" in urlsplit(value).path
                                or "/login" in urlsplit(value).path,
                                timeout=8_000)
        status = await gate(page)
        if status:
            return status, []
        try:
            await page.wait_for_function(
                """selector => [...document.querySelectorAll(selector)]
                    .some(a => a.getClientRects().length)""", arg=LINKS, timeout=6_000
            )
        except TimeoutError:
            status = await gate(page)
            return status or ("empty" if await visible(page, EMPTY) else "results_unavailable"), []
        result = {}
        detail_attempts = 0
        for row in await cards(page, LINKS, 40):
            link = note_link(row["href"])
            if not link or link[0] in result:
                continue
            key, url = link
            title, excerpt = clean(row["title"]), clean(row["excerpt"])
            evidence_kind = "search_snippet" if excerpt else "title"
            if not excerpt and detail_attempts < 2:
                detail_attempts += 1
                href = urlsplit(row["href"])
                detail_url = urlunsplit((href.scheme, href.netloc, urlsplit(url).path, href.query, ""))
                blocked, detail_title, excerpt = await read_detail(detail, detail_url)
                if blocked:
                    return blocked, list(result.values())
                title = detail_title or title
                if excerpt:
                    evidence_kind = "body"
            if title:
                result[key] = {"id": key, "source": SOURCE, "method": METHOD, "query": query,
                               "url": url, "title": title[:300], "excerpt": (excerpt or title)[:450],
                               "content_type": "note", "evidence_kind": evidence_kind}
            if len(result) >= limit:
                break
        return ("ok" if result else "results_unavailable"), list(result.values())
    except TimeoutError:
        return await gate(page) or "timeout", []


def status_result(queries, error):
    return {"source": SOURCE, "method": METHOD, "status": error, "items": [],
            "query_stats": [{"query": q, "status": error, "count": 0} for q in queries]}


async def browser_search(queries, limit=5, *, profile=PROFILE):
    if not profile.is_dir():
        return status_result(queries, "setup_required")
    try:
        async with async_playwright() as playwright:
            context = await launch(playwright.chromium, profile)
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                detail = await context.new_page()
                items, stats = {}, []
                for query in queries:
                    status, notes = await search_query(page, detail, query, limit)
                    for note in notes:
                        items.setdefault(note["id"], note)
                    stats.append({"query": query, "status": status, "count": len(notes)})
                    if status in {"login_required", "verification_required", "access_limited", "unexpected_page"}:
                        break
                states = {row["status"] for row in stats}
                return {"source": SOURCE, "method": METHOD,
                        "status": next(iter(states)) if len(states) == 1 else "partial",
                        "items": list(items.values()), "query_stats": stats}
            finally:
                await context.close()
    except Error:
        return status_result(queries, "browser_unavailable")


async def login():
    PROFILE.mkdir(mode=0o700, exist_ok=True)
    async with async_playwright() as playwright:
        context = await launch(playwright.chromium, PROFILE)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(HOME, wait_until="domcontentloaded", timeout=20_000)
            print("请在打开的 Chrome 窗口完成小红书登录，确认能站内搜索后回到终端。", flush=True)
            await asyncio.to_thread(input, "按回车保存浏览器会话并退出：")
        finally:
            await context.close()


def validate_queries(queries, limit):
    if not 1 <= len(queries) <= 3 or any(not q.strip() or len(q) > 100 for q in queries):
        raise ValueError("提供 1–3 个非空关键词，每词最多 100 个字符。")
    if not 1 <= limit <= 8:
        raise ValueError("每词结果数应为 1–8。")
    return list(dict.fromkeys(q.strip() for q in queries))


def main():
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="Open Chrome for manual login and save the local session")
    search = sub.add_parser("search", help="Search using the saved browser session")
    search.add_argument("queries", nargs="+")
    search.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if args.command == "login":
        try:
            asyncio.run(login())
        except Error:
            parser.exit(1, "无法打开小红书登录页。请确认 Chrome 已安装且专用窗口已关闭。\n")
        return
    try:
        queries = validate_queries(args.queries, args.limit)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(asyncio.run(browser_search(queries, args.limit)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
