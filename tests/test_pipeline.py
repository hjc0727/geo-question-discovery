import csv
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from geo_connector.__main__ import unpack
from geo_connector.core import identity, normalize
from geo_connector.report import export

NOTE = "6a1234561234561234561234"
QUESTION = "https://www.zhihu.com/question/1234/answer/9527?utm_source=demo"


class PipelineTests(unittest.TestCase):
    def test_provider_formats_and_error_status(self):
        response = httpx.Response(200, json={"Code": 0, "Data": {"Items": [
            {"Title": "冲锋衣怎么选？", "ContentText": "雨天短途徒步", "Url": QUESTION}
        ]}})
        status, rows = unpack("zhihu", response)
        self.assertEqual(status, "ok")
        self.assertEqual(normalize("zhihu", rows[0], "冲锋衣")["url"], QUESTION)
        response = httpx.Response(200, json={"code": 200, "data": {"webPages": {"value": [
            {"name": "试穿体验", "snippet": "腰刚好但大腿紧", "url": f"https://www.xiaohongshu.com/explore/{NOTE}"}
        ]}}})
        status, rows = unpack("xiaohongshu", response)
        self.assertEqual(status, "ok")
        self.assertEqual(normalize("xiaohongshu", rows[0], "牛仔裤")["excerpt"], "腰刚好但大腿紧")
        self.assertEqual(unpack("zhihu", httpx.Response(200, json={"Code": 30001})), ("rate_limit", []))
        self.assertEqual(unpack("zhihu", httpx.Response(200, json={"Code": 0})), ("invalid_response", []))

    def test_note_validation_and_canonical_ids(self):
        first = f"https://www.xiaohongshu.com/explore/{NOTE}"
        second = f"https://www.xiaohongshu.com/discovery/item/{NOTE}?a=1"
        self.assertEqual(identity("xiaohongshu", first), identity("xiaohongshu", second))
        self.assertIsNone(identity("xiaohongshu", first.replace(".com/", ".com.evil.test/")))
        self.assertIsNone(identity("xiaohongshu", "https://school.xiaohongshu.com/guide/123"))
        self.assertEqual(identity("zhihu", QUESTION),
                         identity("zhihu", "https://www.zhihu.com/tardis/bd/ans/9527"))

    def test_fixed_output_drops_unfounded_and_duplicate_records(self):
        questions = [
            {"question": "冲锋衣怎么选？", "category": "户外服", "origin": "explicit", "evidence_urls": [QUESTION]},
            {"question": "冲锋衣怎么选?", "category": "户外服", "origin": "explicit", "evidence_urls": [QUESTION]},
            {"question": "羽绒服怎么选？", "category": "户外服", "origin": "explicit", "evidence_urls": [QUESTION]},
            {"question": "高腰裤怎么选？", "category": "裤装", "origin": "inferred", "evidence_urls": ["no-url"]},
        ]
        payload = {"industry": "服装", "sources": {"xiaohongshu": {"status": "timeout"}},
                   "evidence": [{"url": QUESTION, "source": "zhihu", "method": "zhihu_api",
                                 "title": "冲锋衣怎么选？", "excerpt": "雨天短途徒步"}],
                   "questions": questions}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            export(payload, path)
            report = json.loads((path / "report.json").read_text())
            self.assertEqual(report["question_count"], 1)
            self.assertEqual(len(report["rejected"]), 2)
            self.assertEqual(report["sources"]["xiaohongshu"]["status"], "timeout")
            with (path / "questions.csv").open(encoding="utf-8-sig", newline="") as stream:
                row, = list(csv.DictReader(stream))
            self.assertEqual(row["来源链接"], QUESTION)
