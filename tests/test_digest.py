from datetime import datetime, timezone

import pytest

from newsbrief.config import parse_config
from newsbrief.digest import run_digest, weekly
from newsbrief.models import Article, Brief, Story
from newsbrief.state import State



def story(headline, url, source="bbc", summary=""):
    return Story([Article(headline, url, source, summary=summary)], headline=headline, summary=summary or headline + ".")


def week():
    pope = [("2026-09-23", story("Pope Leo to visit France for first papal visit in 18 years", "https://g/1", "guardian")),
            ("2026-09-24", story("Pope Leo arrives in France for first papal visit in 18 years", "https://b/2")),
            ("2026-09-25", story("Pope Leo holds Mass in Paris on France papal visit", "https://aj/3", "aljazeera"))]
    once = [("2026-09-25", story("Volcano erupts in Iceland", "https://b/4"))]
    # unrelated one-day stories, so names like "Pope" are rare (idf) as on a real week
    fill = [(f"2026-09-2{i % 3 + 3}", story(f"Filler{i} topic{i} update{i}", f"https://f/{i}", f"f{i}")) for i in range(16)]
    return pope + once + fill


def test_weekly_threads_multi_day_stories_first():
    top = weekly(week(), n=3)
    assert top[0].headline == "Pope Leo holds Mass in Paris on France papal visit"  # latest take on the thread
    assert (top[0].since, top[0].day) == ("2026-09-23", 3)
    assert top[0].previously.startswith("Pope Leo to visit France")
    assert all(s.day == 1 for s in top[1:])


@pytest.fixture
def cfg(tmp_path):
    return parse_config({
        "state_db": str(tmp_path / "s.db"), "outbox": str(tmp_path / "out"),
        "sources": {"bbc": {"url": "https://b/rss", "topics": ["world"]}},
        "subscribers": [{"email": "ann@example.com", "name": "Ann", "weekly": True},
                        {"email": "bob@example.com"}],
    })


def test_digest_dry_run_only_for_weekly_subscribers(cfg):
    st = State(cfg.state_db)
    for d, s in week():
        rows = [x for x in st.briefs("ann@example.com") if x[0] == d]
        stories = (rows[0][2].stories if rows else []) + [s]
        st.save_brief("ann@example.com", d, Brief("ann@example.com", stories))
    st.close()
    now = datetime(2026, 9, 25, 18, tzinfo=timezone.utc)
    (out,) = run_digest(cfg, dry_run=True, now=now)
    email, n, transport, page = out
    assert (email, transport) == ("ann@example.com", "outbox") and n == 10
    html = page.read_text()
    assert "The Weekly Brief" in html and "Day 3</span>" in html and "Following since Sep 23" in html
    eml = page.with_suffix(".eml").read_text()
    assert "Subject: Weekly Brief, Sep 19-Sep 25" in eml
    assert run_digest(cfg, dry_run=True, now=now, subscriber="bob@example.com")[0][1] == 0  # nothing stored


def test_real_digest_needs_secret(cfg, monkeypatch):
    monkeypatch.delenv("NEWSBRIEF_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="NEWSBRIEF_SECRET"):
        run_digest(cfg, dry_run=False)
