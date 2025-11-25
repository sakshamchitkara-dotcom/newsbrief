"""Main-text extraction from article HTML (stdlib only).

Heuristic: group <p> blocks by their parent element, drop link-heavy or short
blocks, and keep the parent whose paragraphs hold the most text. Works well on
typical news article markup without a readability dependency.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

from .http import FetchError, polite_get
from .models import Article
from .text import clean

log = logging.getLogger(__name__)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "figure", "svg", "button", "template"}
MIN_PARA = 40


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.next_id = 0
        self.skip = 0
        self.para: list[str] | None = None
        self.para_parent = -1
        self.link_chars = 0
        self.in_link = 0
        self.paras: list[tuple[int, str, int]] = []  # (parent id, text, link chars)
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            a = dict(attrs)
            key = a.get("property") or a.get("name")
            if key in ("og:description", "description") and a.get("content"):
                self.meta.setdefault(key, a["content"])
            return
        if tag in VOID:
            return
        self.next_id += 1
        self.stack.append((tag, self.next_id))
        if tag in SKIP:
            self.skip += 1
        elif tag == "p" and not self.skip:
            self.para = []
            self.para_parent = self.stack[-2][1] if len(self.stack) > 1 else 0
            self.link_chars = 0
        elif tag == "a":
            self.in_link += 1

    def handle_endtag(self, tag):
        if tag in VOID or not any(t == tag for t, _ in self.stack):
            return
        while self.stack:
            t, _ = self.stack.pop()
            if t in SKIP:
                self.skip -= 1
            elif t == "a":
                self.in_link = max(0, self.in_link - 1)
            elif t == "p" and self.para is not None:
                self.paras.append((self.para_parent, clean(" ".join(self.para)), self.link_chars))
                self.para = None
            if t == tag:
                break

    def handle_data(self, data):
        if self.para is not None and not self.skip:
            self.para.append(data)
            if self.in_link:
                self.link_chars += len(data.strip())


def extract_text(html: str) -> str:
    p = _Extractor()
    try:
        p.feed(html)
        p.close()
    except Exception as e:  # noqa: BLE001 - malformed markup must not kill the run
        log.debug("html parse error: %s", e)
    groups: dict[int, list[str]] = defaultdict(list)
    for parent, text, links in p.paras:
        if len(text) >= MIN_PARA and links / max(len(text), 1) < 0.5:
            groups[parent].append(text)
    if groups:
        best = max(groups.values(), key=lambda ps: sum(map(len, ps)))
        return "\n\n".join(best)
    return clean(p.meta.get("og:description") or p.meta.get("description") or "")


def enrich(articles: list[Article], workers: int = 8) -> None:
    """Fetch each article page (robots.txt permitting) and fill .text in place."""

    def one(a: Article) -> None:
        if "news.ycombinator.com/item" in a.url:
            return
        try:
            raw = polite_get(a.url)
        except FetchError as e:
            log.info("skip text for %s: %s", a.url, e)
            return
        text = extract_text(raw.decode("utf-8", "replace"))
        if len(text) > len(a.summary):
            a.text = text

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, articles))
