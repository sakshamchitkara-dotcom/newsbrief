"""Near-duplicate detection and story clustering (shingling + Jaccard)."""
from __future__ import annotations

import math
import re
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Article, Story

STOPWORDS = frozenset(
    """a an and are as at be been but by for from has have he her his how in into is it its
    of on or our over says said she than that the their them they this to up was were what
    when where which who will with would you your after about amid new more over out not no
    just can could may might should do does did now also""".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")
TRACKING = ("utm_", "fbclid", "gclid", "ocid", "cmpid", "at_medium", "at_campaign", "traffic_source")


def strip_tracking(url: str) -> str:
    """Drop utm_*/campaign params so links in the email are clean."""
    s = urlsplit(url.strip())
    if not s.query:
        return url.strip()
    q = [(k, v) for k, v in parse_qsl(s.query, keep_blank_values=True) if not k.lower().startswith(TRACKING)]
    return urlunsplit((s.scheme, s.netloc, s.path, urlencode(q), s.fragment))


def normalize_url(url: str) -> str:
    """Identity key for a URL: tracking-free, scheme/www/trailing-slash insensitive."""
    s = urlsplit(strip_tracking(url))
    host = s.netloc.lower().removeprefix("www.")
    return urlunsplit(("https", host, s.path.rstrip("/") or "/", s.query, ""))


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


def weighted_jaccard(a: set[str], b: set[str], idf: dict[str, float]) -> float:
    inter = sum(idf.get(w, 1.0) for w in a & b)
    union = sum(idf.get(w, 1.0) for w in a | b)
    return inter / union if union else 0.0


def overlap(a: set[str], b: set[str], idf: dict[str, float]) -> float:
    """Weighted overlap coefficient: how much of the smaller set the other covers."""
    small = min(sum(idf.get(w, 1.0) for w in a), sum(idf.get(w, 1.0) for w in b))
    return sum(idf.get(w, 1.0) for w in a & b) / small if small else 0.0


def idf_weights(docs: list[set[str]]) -> dict[str, float]:
    df = Counter(w for d in docs for w in d)
    n = len(docs)
    return {w: math.log(1 + n / c) for w, c in df.items()}


# Tuned on a real day of BBC/NPR/Guardian/Al Jazeera/Verge/Ars/HN headlines.
BODY_THRESHOLD = 0.4  # shingle Jaccard: syndicated / lightly edited copies
KEYWORD_THRESHOLD = 0.11  # idf-weighted keyword Jaccard over title + lede
TITLE_OVERLAP = 0.75  # near-identical titles with thin ledes ("F-Droid 2.0")


def _lede(a: Article) -> str:
    return a.title + " " + a.body[:300]


def _doc(a: Article, boiler: set[tuple[str, ...]] = frozenset()) -> set[str]:
    """Keywords of title + lede, minus any phrase that is the outlet's boilerplate."""
    toks = tokens(_lede(a))
    if boiler:
        drop = set()
        for i in range(len(toks) - 3):
            if tuple(toks[i : i + 4]) in boiler:
                drop.update(range(i, i + 4))
        toks = [t for i, t in enumerate(toks) if i not in drop]
    return {_stem(t) for t in toks if t not in STOPWORDS and len(t) > 2}


def source_boilerplate(articles: list[Article], min_repeats: int = 3) -> dict[str, set[tuple[str, ...]]]:
    """4-word phrases repeated across several items of one outlet ("Get our breaking news email")."""
    counts: dict[str, Counter] = {}
    for a in articles:
        counts.setdefault(a.source, Counter()).update(shingles(_lede(a), 4))
    return {src: {sh for sh, n in c.items() if n >= min_repeats} for src, c in counts.items()}


def similar(
    a: Article, b: Article, idf: dict[str, float] | None = None, boiler: dict[str, set[tuple[str, ...]]] | None = None
) -> bool:
    idf, boiler = idf or {}, boiler or {}
    # Shingle overlap only across outlets: within one outlet it mostly measures shared
    # boilerplate ("Get our breaking news email..."), and same-outlet dupes share a URL.
    if a.source != b.source and jaccard(shingles(a.body[:2000]), shingles(b.body[:2000])) >= BODY_THRESHOLD:
        return True
    da, db = _doc(a, boiler.get(a.source, set())), _doc(b, boiler.get(b.source, set()))
    kw = weighted_jaccard(da, db, idf)
    if kw >= KEYWORD_THRESHOLD:
        return True
    return kw >= 0.07 and overlap(keywords(a.title), keywords(b.title), idf) >= TITLE_OVERLAP


def dedupe_urls(articles: list[Article]) -> list[Article]:
    seen: dict[str, Article] = {}
    for a in articles:
        key = normalize_url(a.url)
        if key not in seen or len(a.body) > len(seen[key].body):
            seen[key] = a
    return list(seen.values())


def cluster(articles: list[Article]) -> list[Story]:
    """Group articles covering the same event.

    Leader clustering: an article joins the first cluster whose leader it resembles.
    Unlike union-find this doesn't chain unrelated stories through a live blog that
    mentions everything.
    """
    articles = sorted(dedupe_urls(articles), key=lambda a: (-a.weight, -len(a.body)))
    # Rare words (names, places) say far more about "same event" than common ones.
    boiler = source_boilerplate(articles)
    idf = idf_weights([_doc(a, boiler.get(a.source, set())) for a in articles])
    groups: list[list[Article]] = []
    # ponytail: O(n * clusters) scan, fine for a few hundred items/day; MinHash LSH beyond that
    for a in articles:
        for g in groups:
            if similar(g[0], a, idf, boiler):
                g.append(a)
                break
        else:
            groups.append([a])
    return [Story(articles=g) for g in groups]
