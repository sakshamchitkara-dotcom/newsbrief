from newsbrief.config import Source
from newsbrief.hn import item_to_article

SRC = Source("hn", "hackernews", weight=0.9)


def test_story_maps_to_article():
    a = item_to_article(
        {"id": 1, "type": "story", "title": "Show HN: X", "url": "https://x.dev", "time": 1790000000, "score": 250},
        SRC,
    )
    assert a.url == "https://x.dev" and a.score == 250 and a.weight == 0.9
    assert a.comments_url == "https://news.ycombinator.com/item?id=1"
    assert a.published.tzinfo is not None


def test_ask_hn_without_url_links_to_discussion():
    a = item_to_article({"id": 42, "type": "story", "title": "Ask HN: y?", "text": "<p>hi</p>", "time": 0}, SRC)
    assert a.url == "https://news.ycombinator.com/item?id=42" and a.summary == "hi"


def test_non_stories_and_dead_items_dropped():
    assert item_to_article({"id": 2, "type": "job", "title": "Hiring"}, SRC) is None
    assert item_to_article({"id": 3, "type": "story", "title": "t", "dead": True}, SRC) is None
    assert item_to_article(None, SRC) is None
