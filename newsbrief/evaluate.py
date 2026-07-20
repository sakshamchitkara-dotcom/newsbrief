"""Clustering eval: pairwise precision/recall of `cluster()` against labeled items."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations
from pathlib import Path

from .dedupe import cluster, dedupe_urls
from .models import Article

DEFAULT_SET = Path(__file__).parent / "data" / "cluster_eval.json"


@dataclass
class EvalResult:
    items: int
    gold_pairs: int
    predicted_pairs: int
    correct_pairs: int
    false_merges: list[tuple[Article, Article]] = field(default_factory=list)
    misses: list[tuple[Article, Article]] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.correct_pairs / self.predicted_pairs if self.predicted_pairs else 1.0

    @property
    def recall(self) -> float:
        return self.correct_pairs / self.gold_pairs if self.gold_pairs else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def load_set(path: str | Path = DEFAULT_SET) -> list[tuple[Article, str | None]]:
    """Items as (article, story label); label None means the item stands alone."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for it in data["items"]:
        pub = datetime.fromisoformat(it["published"]) if it.get("published") else None
        a = Article(it["title"], it["url"], it["source"], published=pub, summary=it.get("summary", ""),
                    weight=it.get("weight", 1.0), score=it.get("score", 0))
        out.append((a, it.get("story")))
    return out


def _pairs(groups: list[list[str]]) -> set[frozenset[str]]:
    return {frozenset(p) for g in groups for p in combinations(g, 2)}


def evaluate(labeled: list[tuple[Article, str | None]]) -> EvalResult:
    """Pairwise scores: a pair is positive when both articles land in one cluster."""
    by_url = {a.url: a for a, _ in labeled}
    gold: dict[str, list[str]] = {}
    for a, story in labeled:
        if story:
            gold.setdefault(story, []).append(a.url)
    predicted = [[a.url for a in s.articles] for s in cluster([a for a, _ in labeled])]
    g, p = _pairs(list(gold.values())), _pairs(predicted)
    pair = lambda fs: tuple(sorted((by_url[u] for u in fs), key=lambda a: a.url))  # noqa: E731
    return EvalResult(
        items=len(labeled),
        gold_pairs=len(g),
        predicted_pairs=len(p),
        correct_pairs=len(g & p),
        false_merges=[pair(x) for x in sorted(p - g, key=sorted)],
        misses=[pair(x) for x in sorted(g - p, key=sorted)],
    )


def snapshot(articles: list[Article], captured: str) -> dict:
    """A new labeled set to hand-correct: today's items, URL-deduplicated, with each
    multi-article cluster pre-labeled "c1", "c2", ... so labeling starts from the
    current clustering instead of from scratch."""
    labels = {}
    for n, s in enumerate((s for s in cluster(articles) if len(s.articles) > 1), 1):
        labels.update({a.url: f"c{n}" for a in s.articles})
    items = [
        {"story": labels.get(a.url), "source": a.source, "title": a.title, "url": a.url, "summary": a.summary,
         "published": a.published.isoformat() if a.published else None, "weight": a.weight, "score": a.score}
        for a in sorted(dedupe_urls(articles), key=lambda a: (labels.get(a.url) or "~", a.source, a.title))
    ]
    return {"captured": captured, "description": "Pre-labeled by newsbrief's own clustering: fix the "
            "labels by hand (same label = same event, null = stands alone) before using it with `eval --set`.",
            "items": items}
