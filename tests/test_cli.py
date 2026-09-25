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
