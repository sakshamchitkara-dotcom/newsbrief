from datetime import timedelta
from pathlib import Path

import pytest

from newsbrief import http, pipeline
from newsbrief.config import Source
from newsbrief.feeds import parse_feed
from newsbrief.health import check_feeds, report

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def fake_net(monkeypatch):
    def rss(src):
        if src.url == "down":
            raise http.FetchError("https://down.example/rss: HTTP 503")
        return parse_feed((FIX / src.url).read_bytes(), src)

    def page(url):
        if url.endswith("/rates"):  # like NPR: some article pages load, others answer 402
            return b"<p>ok</p>"
        raise http.FetchError(f"{url}: HTTP 402")

    monkeypatch.setitem(pipeline.FETCHERS, "rss", rss)
    monkeypatch.setattr(http, "polite_get", page)


def test_feed_health_statuses(fake_net):
    srcs = [Source("wire", "rss", url="rss2.xml"), Source("npr", "rss", url="atom.xml", fetch_text=False),
            Source("dead", "rss", url="down")]
    results = check_feeds(srcs)
    wire, npr, dead = results
    assert wire.items and wire.text == "1/2 ok (HTTP 402)" and npr.text == "off"
    assert dead.error.endswith("HTTP 503")
    table, ok = report(results, now=wire.newest + timedelta(hours=1), stale_hours=24)
    assert not ok
    rows = {line.split()[0]: line.split()[1] for line in table.splitlines()[1:]}
    assert rows == {"wire": "OK", "npr": rows["npr"], "dead": "FAIL"}
    assert report([wire], now=wire.newest + timedelta(hours=1))[1]
    _, ok = report([wire], now=wire.newest + timedelta(days=3), stale_hours=24)
    assert not ok and "STALE" in report([wire], now=wire.newest + timedelta(days=3))[0]


def test_check_feeds_cli_exit_code(fake_net, tmp_path, capsys):
    from newsbrief.cli import main

    p = tmp_path / "c.yaml"
    p.write_text(f"state_db: {tmp_path / 's.db'}\nsources:\n  dead: {{url: down}}\n")
    assert main(["-c", str(p), "check"]) == 0  # config-only check never touches the network
    assert main(["-c", str(p), "check", "--feeds"]) == 3
    assert "dead           FAIL" in capsys.readouterr().out


def test_probe_count(fake_net):
    (one,) = check_feeds([Source("wire", "rss", url="rss2.xml")], probes=1)
    assert one.text == "ok"  # the first item alone would have hidden the 402s


def test_probe_zero_skips_article_fetches(fake_net, tmp_path, capsys):
    from newsbrief.cli import main

    p = tmp_path / "c.yaml"
    p.write_text(f"state_db: {tmp_path / 's.db'}\nsources:\n  wire: {{url: rss2.xml}}\n")
    main(["-c", str(p), "check", "--feeds", "--probe", "0"])  # fixture dates are old: STALE
    assert "HTTP 402" not in capsys.readouterr().out
