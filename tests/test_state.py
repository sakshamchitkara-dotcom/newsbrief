from newsbrief.models import Article, Story
from newsbrief.state import State


def story(url):
    return Story([Article("t", url, "s")])


def test_sent_stories_are_not_repeated(tmp_path):
    st = State(str(tmp_path / "s.db"))
    a, b = story("https://ex.com/a"), story("https://ex.com/b")
    st.record("Me@x.com", "2026-09-24", [a])
    assert st.unseen("me@x.com", [a, b]) == [b]
    # tracking params / www don't sneak a repeat through
    assert st.unseen("me@x.com", [story("https://www.ex.com/a?utm_source=rss")]) == []
    assert st.unseen("other@x.com", [a]) == [a]


def test_developing_story_returns_with_only_new_articles(tmp_path):
    st = State(str(tmp_path / "s.db"))
    st.record("me@x.com", "2026-09-24", [story("https://ex.com/day1")])
    today = Story([Article("t", "https://ex.com/day1", "bbc"), Article("t", "https://ex.com/day2", "npr")])
    (got,) = st.unseen("me@x.com", [today])
    assert got.urls == ["https://ex.com/day2"] and got.lead.source == "npr"


def test_deliveries_and_unsubscribe_persist(tmp_path):
    path = str(tmp_path / "s.db")
    st = State(path)
    st.record("me@x.com", "2026-09-24", [])
    st.unsubscribe("ME@x.com")
    st.close()
    st = State(path)
    assert st.delivered("me@x.com", "2026-09-24") and not st.delivered("me@x.com", "2026-09-25")
    assert st.is_unsubscribed("me@x.com")


def test_briefs_round_trip_for_the_archive(tmp_path):
    from datetime import datetime, timezone

    from newsbrief.models import Article, Brief, Story

    st = State(str(tmp_path / "s.db"))
    pub = datetime(2026, 9, 25, 6, tzinfo=timezone.utc)
    s = Story([Article("T", "https://a/1", "bbc", published=pub, text="w " * 500, score=3)],
              topic="world", headline="H", summary="S", why_it_matters="W", rank=1.5)
    st.save_brief("Me@X.com", "2026-09-25", Brief("me@x.com", [s], intro="i", generated_at=pub, summarizer="extractive"))
    st.save_brief("me@x.com", "2026-09-25", Brief("me@x.com", [s, s], intro="again", generated_at=pub))  # replaces
    st.save_brief("you@x.com", "2026-09-24", Brief("you@x.com", [], intro="quiet"))
    rows = st.briefs()
    assert [(d, sub, len(b.stories)) for d, sub, b in rows] == [("2026-09-24", "you@x.com", 0), ("2026-09-25", "me@x.com", 2)]
    b = st.briefs("ME@x.com")[0][2]
    assert b.intro == "again" and b.generated_at == pub
    got = b.stories[0]
    assert (got.headline, got.why_it_matters, got.lead.published, got.reading_minutes) == ("H", "W", pub, 2)
