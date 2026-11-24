import unittest

from playwright.async_api import async_playwright

from geo_connector.report import build_report
from geo_connector.xhs_browser import search_query

NOTE_ID = "6a1234561234561234561234"
FORM = """
<form action="/search_result_ai">
    <input id="search-input" style="display:none">
    <textarea id="search-input-in-feeds" name="keyword" onkeydown="if(event.key==='Enter'){event.preventDefault();this.form.requestSubmit();}"></textarea>
</form>
"""


class XhsBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        playwright = await self.enterAsyncContext(async_playwright())
        self.browser = await playwright.chromium.launch(channel="chrome", headless=True)
        self.addAsyncCleanup(self.browser.close)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        self.detail = await self.context.new_page()

    async def test_search_form_visible_notes_and_report(self):
        seen = []

        async def serve(route):
            url = route.request.url
            seen.append(url)
            if "/search_result" in url:
                html = f"""<section><a href="/search_result/{NOTE_ID}?xsec_token=test">
                    <h2 class="title">梨形身材怎么挑牛仔裤？</h2></a></section>
                    <section style="display:none"><a href="/explore/1{NOTE_ID[1:]}">隐藏笔记</a></section>"""
            elif f"/explore/{NOTE_ID}" in url:
                html = '''<p id="detail-desc">试了几条牛仔裤，腰合适的款式大腿又太紧。</p>
                    <div class="comment-item"><span class="content">还有别的颜色吗？</span></div>
                    <div class="comment-item" hidden><span class="content">隐藏评论</span></div>'''
            else:
                html = FORM
            await route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)

        await self.context.route("**/*", serve)
        status, items = await search_query(
            self.page, self.detail, "梨形牛仔裤", 5, include_comments=True,
        )
        self.assertEqual(status, "ok")
        note, = items
        self.assertEqual(note["evidence_kind"], "body")
        self.assertIn("大腿又太紧", note["excerpt"])
        self.assertNotIn("?", note["url"])
        self.assertEqual(note["comments"], ["还有别的颜色吗？"])
        self.assertTrue(any("xsec_token=test" in url for url in seen))
        report = build_report({"industry": "服装", "sources": {"xiaohongshu": {"status": status}},
                               "evidence": items, "questions": [
            {"question": "腰合适但大腿紧，怎么挑牛仔裤？", "category": "裤装",
             "origin": "inferred", "evidence_urls": [note["url"]]},
        ]})
        self.assertEqual(report["evidence_counts"], {"xiaohongshu": 1})
        self.assertEqual(report["question_count"], 1)

    async def test_stop_at_login_or_access_restriction(self):
        async def login_wall(route):
            if "/login" in route.request.url:
                await route.fulfill(status=200, body="Login required")
            else:
                await route.fulfill(status=302, headers={"location": "/login"})

        await self.context.route("**/*", login_wall)
        self.assertEqual(await search_query(self.page, self.detail, "通勤白衬衫", 5),
                         ("login_required", []))
        await self.context.unroute("**/*", login_wall)

        async def limit(route):
            await route.fulfill(status=429, body="Too many requests")

        await self.context.route("**/*", limit)
        self.assertEqual(await search_query(self.page, self.detail, "通勤白衬衫", 5),
                         ("access_limited", []))
