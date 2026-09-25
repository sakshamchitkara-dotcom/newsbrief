"""Summarize ranked stories into a brief.

Uses Claude when ANTHROPIC_API_KEY (or another Anthropic credential) is available,
otherwise an extractive summarizer that picks the most central sentences.
"""
from __future__ import annotations

import logging
from collections import Counter

from .dedupe import keywords
from .models import Brief, Story
from .text import sentences, truncate

log = logging.getLogger(__name__)


def extractive_summary(story: Story, n: int = 2) -> str:
    """Pick the n sentences most representative of the whole cluster, in original order."""
    centroid = Counter(w for a in story.articles for w in keywords(a.title + " " + a.body[:1500]))
    for a in story.articles:  # titles are the best signal of what the story is about
        for w in keywords(a.title):
            centroid[w] += 2
    body = story.lead.body or next((a.body for a in story.articles if a.body), "")
    sents = [s for s in sentences(body[:5000]) if 30 <= len(s) <= 400]
    if not sents:
        return truncate(body, 280)

    def score(s: str) -> float:
        kw = keywords(s)
        return sum(centroid[w] for w in kw) / (len(kw) ** 0.5 or 1)

    top = sorted(sorted(range(len(sents)), key=lambda i: -score(sents[i]))[:n])
    # early sentences in news copy are usually the lede; bias towards the first one
    if 0 not in top and score(sents[0]) > 0:
        top = sorted([0] + top[: n - 1])
    return truncate(" ".join(sents[i] for i in top), 480)


def summarize_extractive(brief: Brief) -> Brief:
    for s in brief.stories:
        s.headline = s.lead.title
        s.summary = extractive_summary(s)
    topics = Counter(s.topic for s in brief.stories)
    n = len(brief.stories)
    brief.intro = f"{n} {'story' if n == 1 else 'stories'} today" + (
        " across " + ", ".join(t for t, _ in topics.most_common(3)) + "." if topics else "."
    )
    brief.summarizer = "extractive"
    return brief
