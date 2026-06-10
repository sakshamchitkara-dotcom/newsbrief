"""Per-feed health: does each source answer, how fresh is it, can we fetch its articles?"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from . import http
from .config import Source
from .http import FetchError


@dataclass
class FeedHealth:
    source: str
    items: int = 0
    newest: datetime | None = None
    error: str = ""
    text: str = ""  # article-page fetch: "ok", "off", "n/a" or the error

    def status(self, now: datetime, stale_hours: float) -> str:
        if self.error:
            return "FAIL"
        if not self.items:
            return "EMPTY"
        if self.newest and (now - self.newest).total_seconds() > stale_hours * 3600:
            return "STALE"
        return "OK"

    def age(self, now: datetime) -> str:
        if not self.newest:
            return "undated"
        h = (now - self.newest).total_seconds() / 3600
        return f"{h * 60:.0f}m" if h < 1 else f"{h:.1f}h" if h < 48 else f"{h / 24:.0f}d"


def check_source(src: Source, probe_text: bool = True) -> FeedHealth:
    from .pipeline import FETCHERS  # late import: pipeline imports most of the package

    h = FeedHealth(src.name)
    try:
        arts = FETCHERS[src.type](src)
    except FetchError as e:
        h.error = str(e)
        return h
    h.items = len(arts)
    dates = [a.published for a in arts if a.published]
    h.newest = max(dates) if dates else None
    if src.type == "hackernews" or not arts:
        h.text = "n/a"  # HN links to arbitrary sites
    elif not src.fetch_text:
        h.text = "off"
    elif probe_text:
        try:
            http.polite_get(arts[0].url)
            h.text = "ok"
        except FetchError as e:
            h.text = str(e).split(": ", 1)[-1]
    return h


def check_feeds(sources: list[Source], probe_text: bool = True) -> list[FeedHealth]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda s: check_source(s, probe_text), sources))


def report(results: list[FeedHealth], now: datetime | None = None, stale_hours: float = 24) -> tuple[str, bool]:
    """Table of results and whether every feed is healthy."""
    now = now or datetime.now(timezone.utc)
    lines = [f"{'source':<14} {'status':<6} {'items':>5} {'newest':>8}  article text"]
    ok = True
    for h in results:
        st = h.status(now, stale_hours)
        ok = ok and st == "OK"
        detail = h.error or h.text
        lines.append(f"{h.source:<14} {st:<6} {h.items:>5} {h.age(now) if h.items else '-':>8}  {detail}")
    return "\n".join(lines), ok
