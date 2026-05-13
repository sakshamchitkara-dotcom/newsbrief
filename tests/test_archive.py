from datetime import datetime, timezone

from newsbrief.archive import build_site
from newsbrief.models import Article, Brief, Story
from newsbrief.state import State


def brief(email, *headlines):
    stories = [Story([Article(h, f"https://n.example/{i}", "bbc", published=datetime(2026, 9, 25, tzinfo=timezone.utc))],
                     topic="world", headline=h, summary=f"{h} summary.") for i, h in enumerate(headlines)]
    return Brief(email, stories, intro=f"{len(stories)} stories today.")


def test_build_site_writes_index_and_day_pages_without_personal_data(tmp_path):
    st = State(str(tmp_path / "s.db"))
    st.save_brief("ann@example.com", "2026-09-24", brief("ann@example.com", "Rates rise"))
    st.save_brief("ann@example.com", "2026-09-25", brief("ann@example.com", "Pope visits France"))
    st.save_brief("bob@example.com", "2026-09-25", brief("bob@example.com", "Pope visits France", "F-Droid 2.0"))
    paths = build_site(st, tmp_path / "site")
    site = tmp_path / "site"
    assert sorted(p.name for p in paths) == ["2026-09-24.html", "2026-09-25.html", "index.html"]
    assert (site / ".nojekyll").exists()
    index = (site / "index.html").read_text()
    assert index.index('href="2026-09-25.html"') < index.index('href="2026-09-24.html"')  # newest first
    day = (site / "2026-09-25.html").read_text()
    assert "F-Droid 2.0" in day  # bob's fuller brief wins the day
    assert 'href="index.html"' in day and "Friday, September 25, 2026" in day
    for page in site.glob("*.html"):
        text = page.read_text()
        assert "@example.com" not in text and "nsubscribe" not in text


def test_build_site_for_one_subscriber(tmp_path):
    st = State(str(tmp_path / "s.db"))
    st.save_brief("ann@example.com", "2026-09-25", brief("ann@example.com", "Only for Ann"))
    st.save_brief("bob@example.com", "2026-09-25", brief("bob@example.com", "For Bob", "Bob again"))
    build_site(st, tmp_path / "site", subscriber="ann@example.com")
    assert "Only for Ann" in (tmp_path / "site" / "2026-09-25.html").read_text()


def test_empty_archive(tmp_path):
    build_site(State(str(tmp_path / "s.db")), tmp_path / "site")
    assert "No briefs yet." in (tmp_path / "site" / "index.html").read_text()
