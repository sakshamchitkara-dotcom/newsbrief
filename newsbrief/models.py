"""Core data types shared across the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    title: str
    url: str
    source: str  # source name from config
    published: datetime | None = None  # timezone-aware UTC when known
    summary: str = ""  # feed-provided blurb, HTML stripped
    text: str = ""  # extracted main text, filled by extract step
    weight: float = 1.0  # source weight from config
    score: int = 0  # e.g. HN points

    @property
    def body(self) -> str:
        """Best available text for dedupe/summarization."""
        return self.text or self.summary


@dataclass
class Story:
    """A cluster of articles covering the same event."""

    articles: list[Article]
    rank: float = 0.0
    topic: str = ""
    headline: str = ""
    summary: str = ""
    why_it_matters: str = ""

    @property
    def lead(self) -> Article:
        return self.articles[0]

    @property
    def sources(self) -> list[str]:
        return sorted({a.source for a in self.articles})

    @property
    def urls(self) -> list[str]:
        return [a.url for a in self.articles]


@dataclass
class Brief:
    subscriber_email: str
    stories: list[Story] = field(default_factory=list)
    intro: str = ""
    generated_at: datetime | None = None
    summarizer: str = "extractive"
