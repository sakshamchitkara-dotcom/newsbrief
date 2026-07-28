"""Small text helpers shared by feeds, extraction and summarization."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_WS = re.compile(r"\s+")
_INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff\u00ad]")  # zero-width chars, soft hyphen
_SENT = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"'\u201d)\]]))\s+(?=[A-Z0-9\"'\u201c(])")


_BREAK = "\x00"  # paragraph boundary marker inside _Stripper output
_ENDS_SENTENCE = tuple(".!?:;…\"'\u201d\u2019)")


class _Stripper(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}
    BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "tr", "td", "figcaption"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append(_BREAK)

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append(_BREAK)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def strip_html(s: str) -> str:
    if "<" not in s:
        return clean(html.unescape(s))
    p = _Stripper()
    p.feed(s)
    p.close()
    # A standfirst in its own <p> has no full stop ("<p>Fighting escalates</p><p>There are...");
    # joined bare it runs into the next sentence and the summarizer can't split them.
    # inline tags join without a space ("<a>London Stock Exchange</a>." stays one word + ".")
    blocks = [b for b in (clean(x) for x in "".join(p.parts).split(_BREAK)) if b]
    return " ".join(b if b.endswith(_ENDS_SENTENCE) or i == len(blocks) - 1 else b + "." for i, b in enumerate(blocks))


def clean(s: str) -> str:
    return _WS.sub(" ", _INVISIBLE.sub("", s)).strip()


def sentences(s: str) -> list[str]:
    return [x.strip() for x in _SENT.split(clean(s)) if x.strip()]


def truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:-") + "…"
