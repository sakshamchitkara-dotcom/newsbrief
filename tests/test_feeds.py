from datetime import datetime, timezone

from newsbrief.config import Source
from newsbrief.feeds import parse_date, parse_feed


def test_rss2(fixture_bytes):
    arts = parse_feed(fixture_bytes("rss2.xml"), Source("wire", "rss", url="x", weight=1.5))
    assert [a.url for a in arts] == ["https://wire.example.com/rates", "https://wire.example.com/storm"]
    assert arts[0].published == datetime(2026, 9, 24, 8, tzinfo=timezone.utc)
    assert arts[0].summary.startswith("The central bank raised")
    assert "<p>" not in arts[0].summary
    assert arts[1].title == "Storm & floods close coastal highways"
    assert arts[1].published == datetime(2026, 9, 24, 6, 30, tzinfo=timezone.utc)
    assert arts[0].weight == 1.5 and arts[0].source == "wire"


def test_atom_prefers_alternate_link_and_normalises_tz(fixture_bytes):
    arts = parse_feed(fixture_bytes("atom.xml"), Source("atom", "rss", url="x"))
    assert arts[0].url == "https://atom.example.org/rates"
    assert arts[0].published == datetime(2026, 9, 24, 8, 15, tzinfo=timezone.utc)
    assert arts[1].url == "https://atom.example.org/compiler"
    assert "embedded" in arts[1].summary


def test_rdf(fixture_bytes):
    arts = parse_feed(fixture_bytes("rdf.xml"), Source("rdf", "rss", url="x"))
    assert len(arts) == 1 and arts[0].title == "Researchers map deep ocean currents"


def test_limit(fixture_bytes):
    assert len(parse_feed(fixture_bytes("rss2.xml"), Source("w", "rss", url="x", limit=1))) == 1


def test_parse_date_garbage():
    assert parse_date("not a date") is None
    assert parse_date("") is None
