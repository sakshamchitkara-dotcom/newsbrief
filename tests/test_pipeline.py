import email
from datetime import datetime, timezone
from email import policy
from pathlib import Path

import pytest

from newsbrief import pipeline
from newsbrief.config import parse_config
from newsbrief.feeds import parse_feed
from newsbrief.state import State

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setitem(pipeline.FETCHERS, "rss", lambda src: parse_feed((FIX / src.url).read_bytes(), src))
    return parse_config(
        {
            "from_email": "Brief <brief@example.com>",
            "base_url": "https://brief.example.com",
            "state_db": str(tmp_path / "state.db"),
            "outbox": str(tmp_path / "outbox"),
            "sources": {
                "wire": {"type": "rss", "url": "rss2.xml", "weight": 1.5, "topics": ["world"]},
                "atom": {"type": "rss", "url": "atom.xml", "topics": ["world", "tech"]},
                "rdf": {"type": "rss", "url": "rdf.xml", "topics": ["science"]},
            },
            "subscribers": [
                {"email": "ann@example.com", "name": "Ann", "timezone": "Europe/London", "send_at": "07:00"},
                {"email": "bob@example.com", "timezone": "America/Los_Angeles", "send_at": "07:00", "topics": ["tech"]},
            ],
        }
    )


def test_dry_run_writes_outbox_and_does_not_record(cfg):
    outs = pipeline.run(cfg, dry_run=True, now=NOW, fetch_text=False)
    assert [(o.subscriber, o.transport) for o in outs] == [("ann@example.com", "outbox"), ("bob@example.com", "outbox")]
    eml, html = outs[0].paths
    page = html.read_text()
    assert "Good morning, Ann." in page and "2 outlets" in page
    assert "Researchers map deep ocean" not in page  # older than lookback window
    msg = email.message_from_bytes(eml.read_bytes(), policy=policy.default)
    assert msg["List-Unsubscribe"].startswith("<https://brief.example.com/unsubscribe?email=ann%40example.com")
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert msg["Subject"].startswith("Daily Brief, Sep 24: Central bank raises interest rates")
    # bob only follows tech -> only the atom feed
    assert outs[1].stories == 2
    assert not State(cfg.state_db).delivered("ann@example.com", "2026-09-24")


def test_real_send_records_and_next_run_skips_seen(cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(pipeline, "send", lambda msg, html, text, env: sent.append(msg["To"]) or "smtp")
    first = pipeline.run(cfg, dry_run=False, now=NOW, fetch_text=False, subscriber="ann@example.com")
    assert sent == ["ann@example.com"] and first[0].stories == 3
    # only_due: ann already got today's brief, bob's 07:00 in LA hasn't arrived yet
    assert pipeline.run(cfg, dry_run=True, only_due=True, now=NOW, fetch_text=False) == []
    again = pipeline.run(cfg, dry_run=True, now=NOW, fetch_text=False, subscriber="ann@example.com")
    assert again[0].stories == 0 and "Nothing new" in again[0].paths[1].read_text()


def test_unsubscribed_are_skipped(cfg):
    st = State(cfg.state_db)
    st.unsubscribe("bob@example.com")
    st.close()
    assert [o.subscriber for o in pipeline.run(cfg, dry_run=True, now=NOW, fetch_text=False)] == ["ann@example.com"]


def test_is_due_respects_local_time(cfg, tmp_path):
    st = State(str(tmp_path / "d.db"))
    ann, bob = cfg.subscribers  # London 07:00 (06:00Z in BST), LA 07:00 (14:00Z in PDT)
    assert pipeline.is_due(ann, datetime(2026, 9, 24, 6, 5, tzinfo=timezone.utc), st)
    assert not pipeline.is_due(ann, datetime(2026, 9, 24, 5, 55, tzinfo=timezone.utc), st)
    assert not pipeline.is_due(bob, NOW, st)
    st.record("ann@example.com", "2026-09-24", [])
    assert not pipeline.is_due(ann, NOW, st)


def test_scheduler_dry_run_sends_once_per_local_day(cfg):
    log = set()
    first = pipeline.run(cfg, dry_run=True, only_due=True, now=NOW, fetch_text=False, dry_run_log=log)
    assert [o.subscriber for o in first] == ["ann@example.com"]  # London is past 07:00, LA is not
    assert pipeline.run(cfg, dry_run=True, only_due=True, now=NOW, fetch_text=False, dry_run_log=log) == []
