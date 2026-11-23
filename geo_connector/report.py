"""Validate Skill output against its input evidence and export the question list."""
import argparse
import csv
import json
from pathlib import Path
import re
import unicodedata

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
    by_url = {}
    for raw in payload["evidence"]:
        source, url = raw["source"], raw["url"]
        key = identity(source, url)
        title, excerpt = clean(raw.get("title")), clean(raw.get("excerpt"))
        if key and raw.get("method") in METHODS[source] and title and excerpt:
            by_url[url] = {"id": key, "source": source, "url": url, "title": title,
                           "excerpt": excerpt, "method": raw["method"],
                           "query": raw.get("query", ""),
                           "evidence_kind": raw.get("evidence_kind", "")}
    grouped = {}
    rejected = []
    for candidate in payload["questions"]:
        question, category = clean(candidate["question"]), clean(candidate["category"])
        origin = candidate["origin"]
        matches = {}
        for url in candidate["evidence_urls"]:
            evidence = by_url.get(url)
            if evidence:
                matches.setdefault(evidence["id"], evidence)
        normalized = comparable(question)
        if origin not in ("inferred", "explicit") or not normalized or not category or not matches:
            rejected.append({"question": question, "reason": "invalid_or_missing_evidence"})
            continue
        if origin == "explicit" and not any(
            normalized in comparable(item[field])
            for item in matches.values() for field in ("title", "excerpt")
        ):
            rejected.append({"question": question, "reason": "explicit_text_not_found"})
            continue
        key = comparable(category), normalized
        entry = grouped.setdefault(key, {"question": question, "category": category,
                                         "origin": origin, "evidence": {}})
        if origin == "explicit":
            entry["origin"] = origin
        entry["evidence"].update(matches)
    questions = [
        {**entry, "evidence": list(entry["evidence"].values())}
        for entry in grouped.values()
    ]
    questions.sort(key=lambda row: -len(row["evidence"]))
    questions = questions[:30]
    counts = {}
    for item in by_url.values():
        counts.setdefault(item["source"], set()).add(item["id"])
    return {"industry": industry, "sources": payload["sources"],
            "evidence_counts": {key: len(ids) for key, ids in counts.items()},
            "question_count": len(questions), "questions": questions, "rejected": rejected}


def export(payload, destination):
    report = build_report(payload)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (destination / "questions.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["问题", "品类", "提取方式", "平台", "来源链接", "证据片段"])
        for row in report["questions"]:
            evidence = row["evidence"]
            values = [
                row["question"], row["category"], {"explicit": "原题", "inferred": "归纳"}[row["origin"]],
                " / ".join(sorted({item["source"] for item in evidence})),
                "\n".join(item["url"] for item in evidence),
                "\n".join(item["excerpt"] for item in evidence),
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
