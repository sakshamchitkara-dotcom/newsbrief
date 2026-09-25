"""Hacker News via the official Firebase API."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .config import Source
from .http import FetchError, get
from .models import Article
from .text import strip_html

log = logging.getLogger(__name__)
API = "https://hacker-news.firebaseio.com/v0"


def item_to_article(item: dict, source: Source) -> Article | None:
    if not item or item.get("type") != "story" or item.get("dead") or item.get("deleted"):
        return None
    url = item.get("url") or f"https://news.ycombinator.com/item?id={item['id']}"
    return Article(
        title=item.get("title", "").strip(),
        url=url,
        source=source.name,
        published=datetime.fromtimestamp(item.get("time", 0), tz=timezone.utc),
        summary=strip_html(item.get("text", "")),
        weight=source.weight,
        score=int(item.get("score", 0)),
    )


def _item(i: int) -> dict | None:
    try:
        return json.loads(get(f"{API}/item/{i}.json"))
    except (FetchError, ValueError) as e:
        log.warning("hn item %s: %s", i, e)
        return None


def fetch_hn(source: Source) -> list[Article]:
    feed = source.url or "topstories"  # topstories | beststories | newstories
    ids = json.loads(get(f"{API}/{feed}.json"))[: source.limit]
    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(_item, ids))
    return [a for it in items if (a := item_to_article(it, source)) and a.title]
