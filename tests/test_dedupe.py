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
