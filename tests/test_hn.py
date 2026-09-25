from newsbrief.config import Source
import json

import pytest

from newsbrief import hn
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


def fake_api(monkeypatch, responses):
    calls = []

    def get(url, **kw):
        calls.append(url.removeprefix(hn.API))
        body = responses[calls[-1]]
        if isinstance(body, Exception):
            raise body
        return body if isinstance(body, bytes) else json.dumps(body).encode()

    monkeypatch.setattr(hn, "get", get)
    return calls


def test_fetch_hn_keeps_rank_order_and_skips_failed_items(monkeypatch):
    story = lambda i: {"id": i, "type": "story", "title": f"Story {i}", "url": f"https://x.dev/{i}", "time": 0}  # noqa: E731
    calls = fake_api(monkeypatch, {
        "/beststories.json": [3, 1, 2, 4, 5],
        "/item/3.json": story(3), "/item/1.json": hn.FetchError("HTTP 500"), "/item/2.json": b"<html>oops",
        "/item/4.json": {"id": 4, "type": "story", "title": "", "time": 0},  # untitled: dropped
    })
    arts = hn.fetch_hn(hn.Source("hn", "hackernews", url="beststories", limit=4))
    assert [a.title for a in arts] == ["Story 3"]
    assert "/item/5.json" not in calls  # limit applies to the id list


def test_fetch_hn_bad_top_list_is_a_fetch_error(monkeypatch):
    fake_api(monkeypatch, {"/topstories.json": b"<html>Service Unavailable</html>"})
    with pytest.raises(hn.FetchError, match="bad response"):
        hn.fetch_hn(SRC)
    fake_api(monkeypatch, {"/topstories.json": b"null"})
    with pytest.raises(hn.FetchError):
        hn.fetch_hn(SRC)
