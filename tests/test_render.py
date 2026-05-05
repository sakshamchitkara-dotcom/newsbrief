from datetime import datetime

from newsbrief.models import Article, Brief, Story
from newsbrief.render import group_by_topic, render_html, render_text

DATE = datetime(2026, 9, 25, 7)


def brief():
    s1 = Story(
        [Article("Rates <up>", "https://a.com/1?x=1&y=2", "wire"), Article("Rates", "https://b.com/1", "atom")],
        topic="world", headline="Bank lifts rates", summary="It went up & up.", why_it_matters="Loans cost more.",
    )
    s2 = Story([Article("Chip", "https://c.com/1", "hn")], topic="tech", headline="New chip", summary="Fast.")
    s3 = Story([Article("Vote", "https://d.com/1", "wire")], topic="world", headline="Vote", summary="Held.")
    return Brief("me@x.com", [s1, s2, s3], intro="Big day.")


def test_group_by_topic_preserves_rank_order():
    assert [(t, len(s)) for t, s in group_by_topic(brief().stories)] == [("world", 2), ("tech", 1)]


def test_html_escapes_and_links_sources():
    html = render_html(brief(), date=DATE, name="Ann", unsubscribe_url="https://u.example/unsubscribe?t=1")
    assert "Friday, September 25, 2026" in html
    assert "Good morning, Ann." in html
    assert 'href="https://a.com/1?x=1&amp;y=2"' in html and 'href="https://b.com/1"' in html
    assert "It went up &amp; up." in html and "<up>" not in html
    assert "2 outlets" in html and "Why it matters:" in html
    assert 'href="https://u.example/unsubscribe?t=1"' in html
    assert "<style>" in html and 'style="' in html  # inline styles, media query only as enhancement


def test_text_alternative():
    txt = render_text(brief(), date=DATE, unsubscribe_url="https://u")
    assert "## WORLD" in txt and "* Bank lifts rates" in txt
    assert "  - atom: https://b.com/1" in txt and "Unsubscribe: https://u" in txt
    assert all(len(line) <= 90 for line in txt.splitlines())


def test_empty_brief():
    b = Brief("me@x.com", [], intro="0 stories today.")
    assert "Nothing new" in render_html(b, date=DATE) and "Nothing new" in render_text(b, date=DATE)


def test_discussion_links_for_hn():
    s = Story([Article("Show HN", "https://x.dev", "hn", score=321, comments_url="https://news.ycombinator.com/item?id=7")],
              topic="tech", headline="Show HN", summary="A thing.")
    b = Brief("me@x.com", [s], intro="i")
    assert 'href="https://news.ycombinator.com/item?id=7"' in render_html(b, date=DATE)
    assert "321 pts, discuss" in render_html(b, date=DATE)
    assert "discussion (321 pts): https://news.ycombinator.com/item?id=7" in render_text(b, date=DATE)


def test_reading_time_only_when_article_text_was_fetched():
    long = Story([Article("Deep dive", "https://e.com/1", "wire", text="word " * 1000)], topic="world",
                 headline="Deep dive", summary="Long read.")
    blurb = Story([Article("Blurb", "https://e.com/2", "wire", summary="Only a blurb.")], topic="world",
                  headline="Blurb", summary="Short.")
    assert (long.reading_minutes, blurb.reading_minutes) == (4, 0)
    assert Story([Article("t", "u", "s", text="just a few words")]).reading_minutes == 1
    b = Brief("me@x.com", [long, blurb], intro="i")
    html, txt = render_html(b, date=DATE), render_text(b, date=DATE)
    assert html.count("min read") == 1 and "4 min read" in html
    assert "* Deep dive (4 min read)" in txt and "* Blurb\n" in txt
