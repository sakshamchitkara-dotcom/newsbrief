"""Near-duplicate detection and story clustering (shingling + Jaccard)."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
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
ENTITY_MIN, ENTITY_WEIGHT = 3, 8.0  # shared names, and their summed idf
TITLE_NAMES_WEIGHT = 5.0  # summed idf of two+ names both headlines carry ("Trump", "Xi")


def _lede(a: Article) -> str:
    return a.title + " " + a.body[:300]


_WORD = re.compile(r"[A-Za-z0-9]+")
# Anything between two words that ends a sentence or clause: a capital after it is not a name.
_BREAK = re.compile(r"[.!?:;|\u2013\u2014\"\u201c\u2018']|\s-\s")


@dataclass
class Terms:
    keywords: set[str]  # stemmed title + lede words, outlet boilerplate removed
    entities: set[str]  # the subset written as names: "OpenAI", "Medicare", "NYC"
    capitalized: set[str] = field(default_factory=set)  # capitalised anywhere, sentence starts included
    lowercase: set[str] = field(default_factory=set)  # seen lowercase mid-sentence
    title: set[str] = field(default_factory=set)  # keywords of the headline alone

    @property
    def title_names(self) -> set[str]:
        return self.entities & self.title


def terms(a: Article, boiler: set[tuple[str, ...]] = frozenset()) -> Terms:
    """Keywords of title + lede, minus the outlet's boilerplate, plus which of them are names.

    A name is a word capitalised mid-sentence, or an acronym. Title Case headlines (HN,
    The Verge) capitalise everything, so there only acronyms count.
    """
    kws, ents, caps, lower, title = set(), set(), set(), set(), set()
    for n_seg, seg in enumerate((a.title, a.body[:300])):
        words = list(_WORD.finditer(seg))
        low = [m.group().lower() for m in words]
        drop = set()
        if boiler:
            for i in range(len(low) - 3):
                if tuple(low[i : i + 4]) in boiler:
                    drop.update(range(i, i + 4))
        title_case = sum(m.group()[0].isupper() for m in words) > 0.6 * len(words)
        prev_end = 0
        for i, m in enumerate(words):
            w, lw, gap, prev_end = m.group(), low[i], seg[prev_end : m.start()], m.end()
            # two-letter words count only as names like "Xi"; "UN", "UK" and "US" merge too much
            short = len(lw) < 2 or (len(lw) == 2 and not (w[0].isupper() and w[1].islower()))
            if i in drop or lw in STOPWORDS or short:
                continue
            stem = _stem(lw)
            kws.add(stem)
            if n_seg == 0:
                title.add(stem)
            acronym = sum(c.isupper() for c in w) >= 2
            mid_sentence = i > 0 and not _BREAK.search(gap)
            if acronym or (w[0].isupper() and mid_sentence and not title_case):
                ents.add(stem)
            if w[0].isupper():
                caps.add(stem)
            elif mid_sentence:
                lower.add(stem)
    return Terms(kws, ents, caps, lower, title)


def promote_names(ts: list[Terms]) -> None:
    """A word more articles write as a name mid-sentence than in lowercase is a name
    everywhere: "Trump and Xi exchange..." starts with one, and Title Case headlines (HN)
    capitalise every word, so their names are only found this way. Counting, rather than
    "never lowercase", keeps "Trump" a name on a day someone's performance "trumped" others."""
    as_name = Counter(w for t in ts for w in t.entities)
    as_word = Counter(w for t in ts for w in t.lowercase)
    names = {w for w, n in as_name.items() if n > as_word[w]}
    for t in ts:
        t.entities |= t.capitalized & names


def source_boilerplate(articles: list[Article], min_repeats: int = 3) -> dict[str, set[tuple[str, ...]]]:
    """4-word phrases repeated across several items of one outlet ("Get our breaking news email")."""
    counts: dict[str, Counter] = {}
    for a in articles:
        counts.setdefault(a.source, Counter()).update(shingles(_lede(a), 4))
    return {src: {sh for sh, n in c.items() if n >= min_repeats} for src, c in counts.items()}


def similar(a: Article, b: Article, ta: Terms, tb: Terms, idf: dict[str, float], n_docs: int = 0) -> bool:
    # Shingle overlap only across outlets: within one outlet it mostly measures shared
    # boilerplate ("Get our breaking news email..."), and same-outlet dupes share a URL.
    if a.source != b.source and jaccard(shingles(a.body[:2000]), shingles(b.body[:2000])) >= BODY_THRESHOLD:
        return True
    shared = ta.keywords & tb.keywords
    kw = weighted_jaccard(ta.keywords, tb.keywords, idf)
    # One shared rare word is not a story ("What About Rails?" vs "Rails World keynote"):
    # a one-keyword title makes any match look like a big Jaccard score.
    if kw >= KEYWORD_THRESHOLD and len(shared) >= 2:
        return True
    # Names are the strongest same-event signal and survive rewording that dilutes Jaccard:
    # three shared names that aren't everywhere today ("Susan Sarandon", "Netanyahu") ...
    names = ta.entities & tb.entities
    if len(names) >= ENTITY_MIN and sum(idf.get(w, 1.0) for w in names) >= ENTITY_WEIGHT:
        return True
    # ... or two names in both headlines that are rare enough between them: a headline names
    # its story's actors ("Trump ... Xi", "OpenAI ... Australia") even when the rest is reworded.
    both = ta.title_names & tb.title_names
    if len(both) >= 2 and sum(idf.get(w, 1.0) for w in both) >= TITLE_NAMES_WEIGHT:
        return True
    # ... or two, one of which no other article mentions ("Medicare" + "Australia").
    only_here = math.log(1 + n_docs / 2) if n_docs else math.inf
    if len(names) >= 2 and kw >= 0.07 and max(idf.get(w, 0.0) for w in names) >= only_here:
        return True
    # Thin-lede title match is for the same launch/post seen by two outlets ("F-Droid 2.0");
    # within one feed, two short titles sharing a word are two different items.
    if a.source == b.source:
        return False
    return kw >= 0.07 and overlap(keywords(a.title), keywords(b.title), idf) >= TITLE_OVERLAP


def is_live(a: Article) -> bool:
    t = a.title.lower()
    return "/live/" in a.url or t.endswith((" – live", " - live", "as it happened")) or t.startswith("live:")


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
    # Leaders (and so story leads) are the heaviest sources; live blogs go last since
    # their feed blurb and headline wander across many events.
    articles = sorted(dedupe_urls(articles), key=lambda a: (is_live(a), -a.weight, -len(a.body)))
    # Rare words (names, places) say far more about "same event" than common ones.
    boiler = source_boilerplate(articles)
    t = [terms(a, boiler.get(a.source, set())) for a in articles]
    promote_names(t)
    idf = idf_weights([x.keywords for x in t])
    groups: list[list[int]] = []
    # ponytail: O(n * clusters) scan, fine for a few hundred items/day; MinHash LSH beyond that
    for i, a in enumerate(articles):
        for g in groups:
            if similar(articles[g[0]], a, t[g[0]], t[i], idf, len(articles)):
                g.append(i)
                break
        else:
            groups.append([i])
    return [Story(articles=[articles[i] for i in g]) for g in groups]
