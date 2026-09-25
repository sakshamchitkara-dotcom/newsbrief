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
