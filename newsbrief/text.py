"""Small text helpers shared by feeds, extraction and summarization."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_WS = re.compile(r"\s+")
_SENT = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[A-Z0-9\"'(])")


class _Stripper(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def strip_html(s: str) -> str:
    if "<" not in s:
        return clean(html.unescape(s))
    p = _Stripper()
    p.feed(s)
    p.close()
    return clean(" ".join(p.parts))


def clean(s: str) -> str:
    return _WS.sub(" ", s).strip()


def sentences(s: str) -> list[str]:
    return [x.strip() for x in _SENT.split(clean(s)) if x.strip()]


def truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:-") + "…"
