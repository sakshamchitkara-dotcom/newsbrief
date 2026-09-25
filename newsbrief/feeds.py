"""RSS 2.0 / RSS 1.0 (RDF) / Atom parsing with the stdlib XML parser."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .config import Source
from .dedupe import strip_tracking
from .http import FetchError, get
from .models import Article
from .text import clean, strip_html

log = logging.getLogger(__name__)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child(el: ET.Element, *names: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def _text(el: ET.Element, *names: str) -> str:
    c = _child(el, *names)
    return (c.text or "").strip() if c is not None else ""


def parse_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    dt = None
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _atom_link(entry: ET.Element) -> str:
    fallback = ""
    for c in entry:
        if _local(c.tag) != "link":
            continue
        rel = c.get("rel", "alternate")
        if rel == "alternate" and c.get("href"):
            return c.get("href", "")
        fallback = fallback or c.get("href", "")
    return fallback


def parse_feed(data: bytes, source: Source) -> list[Article]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise FetchError(f"{source.name}: bad XML: {e}") from e

    kind = _local(root.tag)
    if kind == "feed":  # Atom
        items = [e for e in root if _local(e.tag) == "entry"]
    else:  # RSS 2.0 has channel/item, RSS 1.0 (rdf:RDF) has item at top level
        items = [e for e in root.iter() if _local(e.tag) == "item"]

    out = []
    for it in items[: source.limit]:
        title = strip_html(_text(it, "title"))
        if kind == "feed":
            link = _atom_link(it)
            date = _text(it, "published", "updated")
            blurb = _text(it, "summary", "content")
        else:
            link = _text(it, "link") or _text(it, "guid")
            date = _text(it, "pubdate", "date", "published", "updated")
            blurb = _text(it, "description", "encoded", "summary")
        if not title or not link.startswith("http"):
            continue
        out.append(
            Article(
                title=title,
                url=strip_tracking(clean(link)),
                source=source.name,
                published=parse_date(date),
                summary=strip_html(blurb),
                weight=source.weight,
            )
        )
    return out


def fetch_feed(source: Source) -> list[Article]:
    return parse_feed(get(source.url), source)
