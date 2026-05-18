import pytest

from newsbrief.cli import main
from newsbrief.unsubscribe import make_token

CFG = """
state_db: {db}
sources:
  hn: {{type: hackernews, topics: [tech]}}
subscribers:
  - {{email: me@example.com, timezone: Asia/Kolkata, send_at: "06:30"}}
"""


@pytest.fixture
def cfg_path(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(CFG.format(db=tmp_path / "s.db"))
    return str(p)


def test_check(cfg_path, capsys):
    assert main(["-c", cfg_path, "check"]) == 0
    assert "me@example.com at 06:30 Asia/Kolkata: hn" in capsys.readouterr().out


def test_unsubscribe_requires_valid_token(cfg_path, capsys):
    assert main(["-c", cfg_path, "unsubscribe", "me@example.com", "bad"]) == 1
    assert main(["-c", cfg_path, "unsubscribe", "me@example.com", make_token("me@example.com")]) == 0
    # a run now has nobody to deliver to, so no network is touched
    assert main(["-c", cfg_path, "run", "--dry-run"]) == 0


def test_bad_config_reports_error(tmp_path, capsys):
    p = tmp_path / "bad.yaml"
    p.write_text("sources: {x: {type: telepathy, url: y}}")
    assert main(["-c", str(p), "check"]) == 1
    assert "unknown type" in capsys.readouterr().err


def test_schedule_loop_survives_failures_and_reloads(cfg_path, monkeypatch):
    import newsbrief.cli as cli

    calls = []

    def fake_run(cfg, **kw):
        calls.append(kw["only_due"])
        if len(calls) == 1:
            raise RuntimeError("feed exploded")
        return []

    class Stop(Exception):
        pass

    sleeps = []

    def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) == 2:
            raise Stop

    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr(cli.time, "sleep", fake_sleep)
    with pytest.raises(Stop):
        main(["-c", cfg_path, "schedule", "--dry-run", "--interval", "7"])
    assert calls == [True, True] and sleeps == [7, 7]


def test_eval_reports_scores(tmp_path, capsys):
    import json

    items = [
        {"story": "rates", "source": "a", "title": "Central bank raises interest rates", "url": "https://a/1"},
        {"story": "rates", "source": "b", "title": "Central bank raises interest rates again", "url": "https://b/1"},
        {"story": None, "source": "c", "title": "Floods hit northern Italy", "url": "https://c/1"},
    ]
    p = tmp_path / "set.json"
    p.write_text(json.dumps({"items": items}))
    assert main(["eval", "--set", str(p)]) == 0
    out = capsys.readouterr().out
    assert "3 items, 1 labeled same-story pairs, 1 predicted" in out
    assert "precision 1.000  recall 1.000  f1 1.000" in out


def test_archive_command(cfg_path, tmp_path, capsys):
    from newsbrief.config import load_config
    from newsbrief.models import Brief
    from newsbrief.state import State

    st = State(load_config(cfg_path).state_db)
    st.save_brief("me@example.com", "2026-09-25", Brief("me@example.com", [], intro="quiet"))
    st.close()
    out = tmp_path / "site"
    assert main(["-c", cfg_path, "archive", "--out", str(out)]) == 0
    assert "wrote 1 day pages + index" in capsys.readouterr().out
    assert (out / "2026-09-25.html").exists() and (out / "index.html").exists()
