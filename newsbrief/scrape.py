"""'page' sources: scrape headline links from a section page (robots.txt respected)."""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

from .config import Source
from .http import polite_get
from .models import Article
from .text import clean


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((self.href, clean(" ".join(self.buf))))
            self.href = None

    def handle_data(self, data):
        if self.href is not None:
            self.buf.append(data)


def headline_links(html: str, base_url: str, limit: int = 30) -> list[tuple[str, str]]:
    """Same-site links whose anchor text looks like a headline."""
    p = _Links()
    p.feed(html)
    host = urlsplit(base_url).netloc
    seen, out = set(), []
    for href, text in p.links:
        url = urldefrag(urljoin(base_url, href))[0]
        if urlsplit(url).netloc != host or not url.startswith("http") or url in seen:
            continue
        if len(text) < 25 or len(text.split()) < 4:
            continue
        seen.add(url)
        out.append((url, text))
        if len(out) >= limit:
            break
    return out


def fetch_page(source: Source) -> list[Article]:
    html = polite_get(source.url).decode("utf-8", "replace")
    return [
        Article(title=t, url=u, source=source.name, weight=source.weight)
        for u, t in headline_links(html, source.url, source.limit)
    ]
