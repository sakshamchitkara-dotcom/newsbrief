"""Near-duplicate detection and story clustering (shingling + Jaccard)."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Article, Story

STOPWORDS = frozenset(
    """a an and are as at be been but by for from has have he her his how in into is it its
    of on or our over says said she than that the their them they this to up was were what
    when where which who will with would you your after about amid new more over out not no
    just can could may might should do does did now also""".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")
TRACKING = ("utm_", "fbclid", "gclid", "ocid", "cmpid", "at_medium", "at_campaign")


def normalize_url(url: str) -> str:
    s = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(s.query) if not k.lower().startswith(TRACKING)]
    host = s.netloc.lower().removeprefix("www.")
    return urlunsplit(("https", host, s.path.rstrip("/") or "/", urlencode(q), ""))


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _stem(w: str) -> str:
    # ponytail: crude plural/verb stripping; swap in a real stemmer if recall matters
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def keywords(text: str) -> set[str]:
    return {_stem(t) for t in tokens(text) if t not in STOPWORDS and len(t) > 2}


def shingles(text: str, k: int = 3) -> set[tuple[str, ...]]:
    t = tokens(text)
    return {tuple(t[i : i + k]) for i in range(max(len(t) - k + 1, 0))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def similar(a: Article, b: Article, body_threshold: float = 0.4, title_threshold: float = 0.3) -> bool:
    # Body shingles catch syndicated copies; keyword overlap catches rewrites of the same event.
    ta = a.title + " " + (a.body[:300] if a.body else "")
    tb = b.title + " " + (b.body[:300] if b.body else "")
    if jaccard(shingles(a.body[:2000]), shingles(b.body[:2000])) >= body_threshold:
        return True
    return jaccard(keywords(ta), keywords(tb)) >= title_threshold


def dedupe_urls(articles: list[Article]) -> list[Article]:
    seen: dict[str, Article] = {}
    for a in articles:
        key = normalize_url(a.url)
        if key not in seen or len(a.body) > len(seen[key].body):
            seen[key] = a
    return list(seen.values())


def cluster(articles: list[Article]) -> list[Story]:
    """Group articles covering the same event. Union-find over pairwise similarity."""
    articles = dedupe_urls(articles)
    parent = list(range(len(articles)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # ponytail: O(n^2) pairwise scan, fine for a few hundred items/day; use MinHash LSH beyond that
    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            if find(i) != find(j) and similar(articles[i], articles[j]):
                parent[find(j)] = find(i)

    groups: dict[int, list[Article]] = {}
    for i, a in enumerate(articles):
        groups.setdefault(find(i), []).append(a)
    stories = []
    for arts in groups.values():
        # lead = highest-weight source, then the longest text
        arts.sort(key=lambda a: (-a.weight, -len(a.body)))
        stories.append(Story(articles=arts))
    return stories
