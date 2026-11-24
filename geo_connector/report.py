"""Validate Skill output against its input evidence and export the question list."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

from .core import clean, identity

METHODS = {
    "zhihu": {"zhihu_api", "host_web_search"},
    "xiaohongshu": {"bocha_index", "host_web_search", "xhs_browser"},
}


def comparable(value):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", value)).casefold()


def csv_cell(value):
    # Prevent spreadsheet formulas when opening search-derived text.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def build_report(payload):
    industry = clean(payload["industry"])
    if not industry:
        raise ValueError("industry is required")
    maximum = payload.get("max_questions", 30)
    if type(maximum) is not int or maximum < 1:
        raise ValueError("max_questions must be a positive integer")
    entities = payload.get("entities", {})
    brand = clean(entities.get("brand"))
    competitors = [clean(value) for value in entities.get("competitors", []) if clean(value)]
    named_entities = [(brand, "品牌点名")]
    named_entities.extend((name, "竞品点名：" + name) for name in competitors)
    by_url = {}
    for raw in payload["evidence"]:
        source, url = raw["source"], raw["url"]
        key = identity(source, url)
        title, excerpt = clean(raw.get("title")), clean(raw.get("excerpt"))
        if key and raw.get("method") in METHODS[source] and title and excerpt:
            by_url[url] = {"id": key, "source": source, "url": url, "title": title,
                           "excerpt": excerpt, "method": raw["method"],
                           "query": raw.get("query", ""),
                           "evidence_kind": raw.get("evidence_kind", ""),
                           "comments": [clean(value) for value in raw.get("comments", [])]
                           if source == "xiaohongshu" and raw["method"] == "xhs_browser" else []}
    grouped = {}
    rejected = []
    for candidate in payload["questions"]:
        question, category = clean(candidate["question"]), clean(candidate["category"])
        context = clean(candidate.get("context"))
        origin = candidate["origin"]
        matches = {}
        for url in candidate["evidence_urls"]:
            evidence = by_url.get(url)
            if evidence:
                matches.setdefault(evidence["id"], evidence)
        normalized = comparable(question)
        location = candidate.get("origin_location", "legacy")
        if origin not in ("inferred", "explicit") or not normalized or not category or not matches:
            rejected.append({"question": question, "reason": "invalid_or_missing_evidence"})
            continue
        texts = {
            "legacy": ("title", "excerpt"), "title": ("title",),
            "body": ("excerpt",), "comment": (),
        }
        matching_texts = [
            item[field] for item in matches.values() for field in texts.get(location, ())
            if location != "body" or (item["source"] == "xiaohongshu" and item["evidence_kind"] == "body")
        ]
        if location == "comment":
            matching_texts = [comment for item in matches.values() for comment in item["comments"]]
        matched_text = next((value for value in matching_texts if normalized in comparable(value)), "")
        if origin == "explicit" and not matched_text:
            rejected.append({"question": question, "reason": "explicit_text_not_found"})
            continue
        key = comparable(category), normalized, comparable(context)
        entry = grouped.setdefault(key, {"question": question, "category": category,
                                         "origin": origin, "context": context, "evidence": {}})
        if origin == "explicit":
            entry["origin"] = origin
            entry["origin_location"] = location
            entry["question_evidence"] = matched_text
        entry["evidence"].update(matches)
    questions = [
        {**entry, "evidence": list(entry["evidence"].values())}
        for entry in grouped.values()
    ]
    questions.sort(key=lambda row: -len(row["evidence"]))
    questions = questions[:maximum]
    for row in questions:
        question_text = unicodedata.normalize("NFKC", row["question"]).casefold()
        row["mention_tags"] = [
            label for name, label in named_entities
            if name and unicodedata.normalize("NFKC", name).casefold() in
            question_text
        ]
        if not row["mention_tags"]:
            row["mention_tags"] = ["未点名"]
        if row.get("origin_location") == "title":
            for item in row["evidence"]:
                if item["source"] == "zhihu" and comparable(row["question"]) in comparable(item["title"]):
                    parent = re.match(r"/question/(\d+)(?:/|$)", urlsplit(item["url"]).path)
                    if parent:
                        row["original_question_url"] = f"https://www.zhihu.com/question/{parent[1]}"
                        break
    counts = {}
    for item in by_url.values():
        counts.setdefault(item["source"], set()).add(item["id"])
    explicit_rows = [row for row in questions if row["origin"] == "explicit"]
    return {"industry": industry, "sources": payload["sources"],
            "evidence_counts": {key: len(ids) for key, ids in counts.items()},
            "question_count": len(questions), "questions": questions, "rejected": rejected,
            "entities": entities, "question_counts_by_origin": dict(Counter(row["origin"] for row in questions)),
            "explicit_mention_counts": dict(Counter(tag for row in explicit_rows for tag in row["mention_tags"]))}


def export(payload, destination):
    report = build_report(payload)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (destination / "questions.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["问题", "品类", "提取方式", "平台", "来源链接", "证据片段",
                         "原问位置", "点名标签", "原问证据", "原提问链接", "对象上下文"])
        for row in report["questions"]:
            evidence = row["evidence"]
            values = [
                row["question"], row["category"], {"explicit": "原题", "inferred": "归纳"}[row["origin"]],
                " / ".join(sorted({item["source"] for item in evidence})),
                "\n".join(item["url"] for item in evidence),
                "\n".join(item["excerpt"] for item in evidence),
                {"title": "标题", "body": "正文", "comment": "评论"}.get(row.get("origin_location"), ""),
                " / ".join(row["mention_tags"]),
                row.get("question_evidence", ""),
                row.get("original_question_url", ""),
                row["context"],
            ]
            writer.writerow(map(csv_cell, values))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = export(json.loads(args.input.read_text(encoding="utf-8")), args.destination)
    print(json.dumps({key: result[key] for key in ("question_count", "evidence_counts", "rejected")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
