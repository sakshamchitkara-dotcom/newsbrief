"""Rank stories by recency, source weight and cross-source coverage."""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone

from .config import Source
from .models import Story

HALF_LIFE_HOURS = 12.0


def newest(story: Story) -> datetime | None:
    dates = [a.published for a in story.articles if a.published]
    return max(dates) if dates else None


def score(story: Story, now: datetime) -> float:
    ts = newest(story)
    age_h = max((now - ts).total_seconds() / 3600, 0) if ts else 24.0  # undated = a day old
    recency = 0.5 ** (age_h / HALF_LIFE_HOURS)
    weight = max(a.weight for a in story.articles)
    coverage = 1 + math.log2(len(story.sources))  # 1 outlet -> 1, 2 -> 2, 4 -> 3
    points = max(a.score for a in story.articles)
    popularity = 1 + math.log10(1 + points) / 3  # HN 1000 pts -> 2x
    return recency * weight * coverage * popularity


def assign_topic(story: Story, sources: dict[str, Source]) -> str:
    c = Counter(t for a in story.articles for t in (sources[a.source].topics if a.source in sources else []))
    return c.most_common(1)[0][0] if c else "news"


def rank(stories: list[Story], sources: dict[str, Source], now: datetime | None = None) -> list[Story]:
    now = now or datetime.now(timezone.utc)
    for s in stories:
        s.rank = score(s, now)
        s.topic = assign_topic(s, sources)
    return sorted(stories, key=lambda s: s.rank, reverse=True)


def within(story: Story, now: datetime, hours: float) -> bool:
    ts = newest(story)
    return ts is None or (now - ts).total_seconds() <= hours * 3600


def diversify(stories: list[Story], n: int, per_topic: int) -> list[Story]:
    """Top n in rank order, but no topic takes more than per_topic slots unless nothing else is left."""
    picked, counts, overflow = [], Counter(), []
    for s in stories:
        if counts[s.topic] < per_topic:
            picked.append(s)
            counts[s.topic] += 1
        else:
            overflow.append(s)
        if len(picked) == n:
            return picked
    picked += overflow[: n - len(picked)]
    return sorted(picked, key=lambda s: s.rank, reverse=True)
