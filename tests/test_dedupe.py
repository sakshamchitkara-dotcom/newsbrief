from newsbrief.config import Source
from newsbrief.dedupe import cluster, dedupe_urls, jaccard, normalize_url, shingles
from newsbrief.feeds import parse_feed
from newsbrief.models import Article


def test_normalize_url_strips_tracking_and_www():
    assert normalize_url("http://www.Ex.com/a/?utm_source=x&id=3#frag") == "https://ex.com/a?id=3"


def test_shingles_and_jaccard():
    a, b = shingles("the quick brown fox jumps"), shingles("the quick brown fox sleeps")
    assert jaccard(a, b) == 0.5
    assert jaccard(set(), a) == 0.0


def test_dedupe_urls_keeps_longest_body():
    x = Article("t", "https://ex.com/a?utm_medium=rss", "s1", summary="short")
    y = Article("t", "https://www.ex.com/a", "s2", summary="a much longer summary")
    assert dedupe_urls([x, y]) == [y]


def test_cross_outlet_stories_cluster(fixture_bytes):
    arts = parse_feed(fixture_bytes("rss2.xml"), Source("wire", "rss", url="x", weight=2))
    arts += parse_feed(fixture_bytes("atom.xml"), Source("atom", "rss", url="x"))
    arts += parse_feed(fixture_bytes("rdf.xml"), Source("rdf", "rss", url="x"))
    stories = cluster(arts)
    assert len(stories) == 4  # rates (2 outlets), storm, compiler, ocean
    rates = next(s for s in stories if len(s.articles) == 2)
    assert rates.sources == ["atom", "wire"]
    assert rates.lead.source == "wire"  # heavier source leads


def test_unrelated_stories_stay_apart():
    a = Article("Apple unveils new iPhone with faster chip", "https://a.com/1", "a")
    b = Article("Floods hit northern Italy after record rain", "https://b.com/1", "b")
    assert len(cluster([a, b])) == 2


def test_rewritten_headlines_of_same_event_cluster():
    # real pair from a live run: no shared phrasing, but the rare words line up
    a = Article("Pope Leo visits France for first papal visit in 18 years", "https://g.com/1", "guardian",
                summary="Pope Leo will visit France this weekend, the first papal state visit to the country in 18 years.")
    b = Article("Pope Leo heads to France amid assisted dying, abuse debates", "https://aj.com/1", "aljazeera",
                summary="Pope Leo XIV is heading to France for the first official papal visit to the country in 18 years.")
    fillers = [Article(f"Unrelated story number {i} about {w}", f"https://f.com/{i}", "f", summary=f"Details on {w}.")
               for i, w in enumerate(["markets", "football", "weather", "chips", "elections", "music"])]
    stories = cluster([a, b, *fillers])
    assert any({x.url for x in s.articles} == {a.url, b.url} for s in stories)


def test_outlet_boilerplate_does_not_merge_its_stories():
    tail = " Follow our Australia news live blog for latest updates Get our breaking news email, free app or daily news podcast"
    arts = [
        Article(t, f"https://gu.com/{i}", "guardian", summary=t + "." + tail)
        for i, t in enumerate([
            "Police officer killed after car crashes into tree in Redfern",
            "Court hears murder accused asked friend a chilling question",
            "Senator calls for AI safety act after Medicare breach",
        ])
    ]
    assert len(cluster(arts)) == 3


def test_strip_tracking_keeps_real_params():
    from newsbrief.dedupe import strip_tracking

    assert strip_tracking("https://www.bbc.co.uk/news/a?at_medium=RSS&at_campaign=rss") == "https://www.bbc.co.uk/news/a"
    assert strip_tracking("https://aj.com/x?traffic_source=rss&page=2") == "https://aj.com/x?page=2"
    assert strip_tracking("https://news.ycombinator.com/item?id=42") == "https://news.ycombinator.com/item?id=42"


def test_live_blogs_never_lead_a_story():
    live = Article("Pope Leo visits France for first papal visit – Europe live",
                   "https://g.com/world/live/2026/sep/25/pope", "guardian", weight=1.3,
                   summary="Pope Leo visits France for the first papal visit in 18 years.")
    news = Article("Pope Leo visits France in first papal visit in 18 years", "https://aj.com/pope", "aljazeera",
                   weight=1.0, summary="Pope Leo visits France, the first papal visit in 18 years.")
    (story,) = cluster([live, news])
    assert story.lead is news


FILLER_TITLES = ["Floods hit northern Italy after record rain", "Central bank holds interest rates",
                 "Chip maker unveils faster laptop processor", "Football club names new manager"]


def test_one_shared_word_does_not_merge_hn_posts():
    # real false merge from the 2026-09-25 run: two unrelated Rails posts, no blurbs
    a = Article("What About Rails?", "https://hn.example/1", "hn")
    b = Article("Rails World 2026 Opening Keynote [video]", "https://hn.example/2", "hn")
    fillers = [Article(t, f"https://f.com/{i}", "f") for i, t in enumerate(FILLER_TITLES)]
    assert not any(len(s.articles) > 1 for s in cluster([a, b, *fillers]))


def test_eval_set_known_pairs():
    """Regression guard on the labeled real-feed set (see `newsbrief eval`)."""
    from newsbrief.evaluate import evaluate, load_set

    r = evaluate(load_set())
    merged = {frozenset(a.title for a in p) for p in r.false_merges}
    assert frozenset({"What About Rails?", "Rails World 2026 Opening Keynote [video]"}) not in merged
    missed = {frozenset(a.title for a in p) for p in r.misses}
    assert not any("F-Droid 2.0" in p for p in missed)  # thin title still matched across outlets
    medicare = [p for p in missed if all("Medicare" in t for t in p)]
    assert medicare == []  # the Guardian live blog + news piece on the OpenAI Medicare hack
    assert r.precision >= 0.9


def test_terms_find_names_but_not_sentence_starts_or_title_case():
    from newsbrief.dedupe import terms

    t = terms(Article("PM rejects claim he delayed revealing OpenAI Medicare hack", "u", "g",
                      summary="Experts say Australia's laws need work. The CDC and NYC weighed in."))
    assert {"openai", "medicare", "australia", "cdc", "nyc"} <= t.entities
    assert "expert" not in t.entities and "the" not in t.keywords  # sentence-initial, stopword
    hn = terms(Article("Show HN: Make Cursed Fonts Like Times New Bastard", "u", "hn"))
    assert hn.entities == set()  # Title Case capitalises everything; only acronyms would count
