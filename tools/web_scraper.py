import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests


MAX_URLS = 3
MAX_BYTES = 1_000_000
MAX_TEXT_CHARS = 6000
URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)


class _ReadableTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth:
            return

        text = " ".join(data.split())
        if text:
            self._parts.append(text)

    def text(self):
        return " ".join(self._parts)


def extract_urls(text):
    urls = []
    for match in URL_RE.findall(text or ""):
        url = match.rstrip(".,;:!?)]}")
        if url not in urls:
            urls.append(url)
        if len(urls) >= MAX_URLS:
            break

    return urls


def _validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only http and https URLs are supported.")


def _html_to_text(html):
    parser = _ReadableTextParser()
    parser.feed(html)
    text = parser.text()
    return " ".join(text.split())


def scrape_url(url, timeout=15):
    _validate_url(url)
    response = requests.get(
        url,
        headers={
            "User-Agent": "BigShot-Guy-Bot/1.0",
            "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5",
        },
        timeout=timeout,
        stream=True,
    )
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=16384):
        if not chunk:
            continue

        total += len(chunk)
        if total > MAX_BYTES:
            break
        chunks.append(chunk)

    raw = b"".join(chunks)
    encoding = response.encoding or "utf-8"
    body = raw.decode(encoding, errors="replace")

    if "html" in content_type.lower() or "<html" in body[:500].lower():
        text = _html_to_text(body)
    else:
        text = " ".join(body.split())

    return {
        "url": url,
        "status_code": response.status_code,
        "content_type": content_type or "unknown",
        "text": text[:MAX_TEXT_CHARS],
        "truncated": len(text) > MAX_TEXT_CHARS or total > MAX_BYTES,
    }


def scrape_urls_from_text(text):
    pages = []
    errors = []

    for url in extract_urls(text):
        try:
            pages.append(scrape_url(url))
        except Exception as exc:
            errors.append({
                "url": url,
                "error": str(exc),
            })

    return {
        "pages": pages,
        "errors": errors,
    }
