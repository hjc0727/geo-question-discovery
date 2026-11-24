"""Validate content links and normalize provider records."""
from html import unescape
import re
from urllib.parse import urlsplit

SOURCES = ("zhihu", "xiaohongshu")
PATHS = {
    "zhihu": r"/(?:question/\d+(?:/answer/\d+)?|p/\d+|tardis/(?:bd|zm)/(?:ans|art)/\d+)/?",
    "xiaohongshu": r"/(?:explore|discovery/item)/[0-9a-fA-F]{24}/?",
}
DOMAINS = {"zhihu": "zhihu.com", "xiaohongshu": "xiaohongshu.com"}


def clean(value):
    return " ".join(unescape(re.sub(r"<[^>]+>", "", str(value or ""))).split())


def identity(source, url):
    """Canonical key for deduplication. Keep the original URL when exporting."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        domain = DOMAINS[source]
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
            return None
    except (ValueError, TypeError, KeyError):
        return None
    also_allowed = source == "xiaohongshu" and host in {"rednote.com", "www.rednote.com"}
    if not also_allowed and host != domain and not host.endswith("." + domain):
        return None
    path = parsed.path.rstrip("/")
    if not re.fullmatch(PATHS[source], path):
        return None
    number = path.rsplit("/", 1)[-1]
    if source == "xiaohongshu":
        return f"{source}:note:{number.lower()}"
    kind = "answer" if "/answer/" in path or "/ans/" in path else (
        "article" if path.startswith("/p/") or "/art/" in path else "question"
    )
    return f"{source}:{kind}:{number}"


def normalize(source, item, query):
    if source == "zhihu":
        url = item.get("Url", "")
        title, excerpt = clean(item.get("Title")), clean(item.get("ContentText"))
        content_type = clean(item.get("ContentType"))
        method = "zhihu_api"
    else:
        url = item.get("url", "")
        title = clean(item.get("name"))
        excerpt = clean(item.get("summary") or item.get("snippet"))
        content_type, method = "note", "bocha_index"
    key = identity(source, url)
    if not key or not title:
        return None
    record = {"id": key, "source": source, "url": url, "title": title[:300],
              "excerpt": excerpt[:450], "content_type": content_type, "query": query,
              "method": method}
    if source == "zhihu":
        parent = re.match(r"/question/(\d+)(?:/|$)", urlsplit(url).path)
        if parent:
            record["question_id"] = parent[1]
    return record
