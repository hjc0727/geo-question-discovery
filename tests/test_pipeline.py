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
        self.assertEqual(normalize("zhihu", rows[0], "冲锋衣")["question_id"], "1234")
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

    def test_brand_and_competitor_mentions_are_in_the_question(self):
        url = f"https://www.xiaohongshu.com/explore/{NOTE}"
        evidence = [{"url": url, "source": "xiaohongshu", "method": "xhs_browser",
                     "title": "甲牌体验", "excerpt": "我买了甲牌。",
                     "comments": ["哪里买这个？", "甲牌和乙牌怎么选？"]}]
        questions = [
            {"question": q, "category": "比较", "origin": "explicit",
             "origin_location": "comment", "evidence_urls": [url]}
            for q in ["哪里买这个？", "甲牌和乙牌怎么选？", "甲牌哪里买？"]
        ]
        with tempfile.TemporaryDirectory() as directory:
            report = export({"industry": "甲牌", "sources": {}, "evidence": evidence,
                             "entities": {"brand": "甲牌", "competitors": ["乙牌"]},
                             "questions": questions, "max_questions": 50}, Path(directory))
        self.assertEqual(report["question_count"], 2)
        self.assertEqual(report["questions"][0]["mention_tags"], ["未点名"])
        self.assertEqual(report["questions"][1]["mention_tags"], ["品牌点名", "竞品点名：乙牌"])
        self.assertEqual(report["rejected"][0]["reason"], "explicit_text_not_found")

    def test_seed_expansion_excludes_seed_and_combines_zhihu_answers(self):
        from geo_connector.report import build_report

        first = "https://www.zhihu.com/question/1234/answer/9527"
        second = "https://www.zhihu.com/question/1234/answer/9528"
        seed = "团队协作工具怎么选？"
        question = "团队协作工具怎么迁移历史任务？"
        article = "https://zhuanlan.zhihu.com/p/1235"
        evidence = [
            {"url": url, "source": "zhihu", "method": "zhihu_api", "title": title}
            for url, title in [(first, question + " - 知乎"), (second, question), (article, "文章标题是问句吗？")]
        ]
        candidates = [
            {"question": title, "category": category, "origin": "explicit",
             "origin_location": "title", "evidence_urls": [url], "seed_ids": [seed_id]}
            for title, category, url, seed_id in [
                (question, "迁移", first, "S01"), (question, "部署", second, "S02"),
                (seed, "选型", first, "S01"), ("文章标题是问句吗？", "选型", article, "S01"),
            ]
        ]
        report = build_report({
            "industry": "协作软件", "sources": {}, "evidence": evidence, "questions": candidates,
            "discovery": {"mode": "seed_expansion", "seeds": {"S01": seed, "S02": "怎么设置权限？"}},
        })
        row, = report["questions"]
        self.assertEqual(row["seed_ids"], ["S01", "S02"])
        self.assertEqual(row["original_question_url"], "https://www.zhihu.com/question/1234")
        self.assertEqual(report["new_questions_by_seed"], {"S01": 1, "S02": 1})
        self.assertEqual([item["reason"] for item in report["rejected"]],
                         ["seed_question", "zhihu_original_question_not_verified"])
