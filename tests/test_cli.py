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


def test_subscribers_add_list_remove(cfg_path, capsys):
    from pathlib import Path

    header = "# my config\n"
    p = Path(cfg_path)
    p.write_text(header + p.read_text())
    assert main(["-c", cfg_path, "subscribers", "add", "new@example.com", "--tz", "Europe/Berlin",
                 "--send-at", "06:15", "--topics", "tech", "--name", "Neu"]) == 0
    assert main(["-c", cfg_path, "subscribers", "list"]) == 0
    out = capsys.readouterr().out
    assert "new@example.com" in out and "06:15 Europe/Berlin" in out and "topics=tech" in out and "2 subscribers" in out
    assert p.read_text().startswith(header)  # the rest of the file, comments included, is kept
    assert main(["-c", cfg_path, "subscribers", "remove", "NEW@example.com"]) == 0
    assert "new@example.com" not in p.read_text() and "me@example.com" in p.read_text()


@pytest.mark.parametrize("extra,err", [
    (["--tz", "Mars/Olympus"], "unknown timezone"),
    (["--send-at", "7pm"], "HH:MM"),
    (["--topics", "sport"], "unknown topics"),
])
def test_subscribers_add_validates_before_writing(cfg_path, capsys, extra, err):
    from pathlib import Path

    before = Path(cfg_path).read_text()
    assert main(["-c", cfg_path, "subscribers", "add", "x@example.com", *extra]) == 1
    assert err in capsys.readouterr().err and Path(cfg_path).read_text() == before


def test_subscribers_rejects_duplicates_and_unknown(cfg_path, capsys):
    assert main(["-c", cfg_path, "subscribers", "add", "ME@example.com"]) == 1
    assert main(["-c", cfg_path, "subscribers", "remove", "ghost@example.com"]) == 1
    err = capsys.readouterr().err
    assert "already subscribed" in err and "no subscriber ghost@example.com" in err


@pytest.mark.parametrize("cmd", [["run"], ["digest"], ["serve"]])
def test_real_sends_and_serve_need_the_secret(cfg_path, capsys, monkeypatch, cmd):
    monkeypatch.delenv("NEWSBRIEF_SECRET", raising=False)
    assert main(["-c", cfg_path, *cmd]) == 1
    assert "NEWSBRIEF_SECRET must be set" in capsys.readouterr().err


def test_serve_binds_to_the_configured_db(cfg_path, capsys, monkeypatch):
    from newsbrief import server

    monkeypatch.setenv("NEWSBRIEF_SECRET", "s")
    calls = []
    monkeypatch.setattr(server, "serve", lambda *a: calls.append(a))
    assert main(["-c", cfg_path, "serve", "--port", "9999"]) == 0
    assert calls[0][1:] == ("127.0.0.1", 9999) and calls[0][0].endswith("s.db")


def test_delivery_errors_exit_2(cfg_path, caplog, monkeypatch):
    for var in ("NEWSBRIEF_TRANSPORT", "SMTP_HOST", "RESEND_API_KEY", "SENDGRID_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NEWSBRIEF_SECRET", "s")
    assert main(["-c", cfg_path, "run"]) == 2
    assert main(["-c", cfg_path, "digest"]) == 2
    assert caplog.text.count("no transport configured") == 2


def test_digest_and_audio_commands(cfg_path, tmp_path, capsys, monkeypatch):
    from newsbrief.config import load_config
    from newsbrief.models import Article, Brief, Story
    from newsbrief.state import State

    monkeypatch.chdir(tmp_path)
    assert main(["-c", cfg_path, "digest", "--dry-run"]) == 0
    assert "no subscribers with weekly: true" in capsys.readouterr().out
    assert main(["-c", cfg_path, "audio", "--script-only"]) == 1
    assert "no stored brief for any day" in capsys.readouterr().err

    story = Story([Article("Rates rise", "https://a/1", "hn")], headline="Rates rise", summary="Up again.", topic="tech")
    st = State(load_config(cfg_path).state_db)
    st.save_brief("me@example.com", "2026-09-24", Brief("me@example.com", [story], intro="One story."))
    st.close()
    assert main(["-c", cfg_path, "audio", "--date", "2026-09-23"]) == 1
    assert main(["-c", cfg_path, "audio", "--script-only"]) == 0
    assert "-> outbox/brief-2026-09-24.txt" in capsys.readouterr().out
    assert "Rates rise" in (tmp_path / "outbox/brief-2026-09-24.txt").read_text()
    assert main(["-c", cfg_path, "digest", "--dry-run", "--subscriber", "me@example.com"]) == 0
    assert "me@example.com: 1 stories via outbox -> outbox/" in capsys.readouterr().out
