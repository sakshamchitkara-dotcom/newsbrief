from datetime import date
from pathlib import Path

import pytest

from newsbrief import audio
from newsbrief.cli import main
from newsbrief.models import Article, Brief, Story


def brief():
    s1 = Story([Article("Rates", "https://a/1", "wire")], topic="world", headline="Bank lifts rates",
               summary="It rose to 5% (see https://a/1).", why_it_matters="Loans cost more.", day=2, since="2026-09-24")
    s2 = Story([Article("Chip", "https://c/1", "hn")], topic="tech", headline="New chip.", summary="Fast.")
    return Brief("me@x.com", [s1, s2], intro="Two stories today.")


def test_script_reads_stories_without_links():
    text = audio.script(brief(), date(2026, 9, 25))
    assert text.startswith("The Daily Brief, Friday, September 25.\n\nTwo stories today.")
    assert "In world.\n\nBank lifts rates.\n\nDay 2 of this story.\n\nIt rose to 5% (see )." in text
    assert "Why it matters: Loans cost more." in text and "New chip.\n" in text and "New chip.." not in text
    assert "https://" not in text


def test_synthesize_calls_say(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/say")
    monkeypatch.setattr(audio.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    out = audio.synthesize("Hello.", tmp_path / "b.m4a", voice="Samantha", rate=190)
    assert calls == [["/usr/bin/say", "-f", str(tmp_path / "b.txt"), "-o", str(out),
                      "--file-format=m4af", "--data-format=aac", "-v", "Samantha", "-r", "190"]]
    assert (tmp_path / "b.txt").read_text() == "Hello."


def test_synthesize_without_say(monkeypatch, tmp_path):
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="script-only"):
        audio.synthesize("Hi", tmp_path / "b.m4a")


def test_audio_command_script_only(tmp_path, capsys):
    from newsbrief.state import State

    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"state_db: {tmp_path / 's.db'}\noutbox: {tmp_path / 'out'}\nsources:\n  a: {{url: x}}\n")
    assert main(["-c", str(cfg), "audio", "--script-only"]) == 1  # nothing stored yet
    st = State(str(tmp_path / "s.db"))
    st.save_brief("me@x.com", "2026-09-25", brief())
    st.close()
    assert main(["-c", str(cfg), "audio", "--script-only"]) == 0
    assert "Bank lifts rates." in Path(tmp_path / "out" / "brief-2026-09-25.txt").read_text()
    assert "-> " in capsys.readouterr().out
