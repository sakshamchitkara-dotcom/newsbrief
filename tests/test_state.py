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


def test_deliveries_and_unsubscribe_persist(tmp_path):
    path = str(tmp_path / "s.db")
    st = State(path)
    st.record("me@x.com", "2026-09-24", [])
    st.unsubscribe("ME@x.com")
    st.close()
    st = State(path)
    assert st.delivered("me@x.com", "2026-09-24") and not st.delivered("me@x.com", "2026-09-25")
    assert st.is_unsubscribed("me@x.com")
