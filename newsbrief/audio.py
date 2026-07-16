"""Podcast-style audio brief: a spoken script of a stored brief, voiced by macOS `say`."""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from .models import Brief
from .render import group_by_topic

_URL = re.compile(r"https?://[^\s)\]]+")


def script(brief: Brief, day: date, title: str = "The Daily Brief") -> str:
    """What to read aloud: intro, then each story's headline, summary and why it matters.
    Links and source lists are left out; they don't work as speech."""
    parts = [f"{title}, {day:%A, %B} {day.day}.", brief.intro]
    for topic, stories in group_by_topic(brief.stories):
        parts.append(f"In {topic}.")
        for s in stories:
            parts.append(f"{(s.headline or s.lead.title).rstrip('.')}.")
            if s.day > 1:
                parts.append(f"Day {s.day} of this story.")
            parts.append(s.summary)
            if s.why_it_matters:
                parts.append(f"Why it matters: {s.why_it_matters}")
    parts.append("That's the brief. Links to every story are in your email.")
    return "\n\n".join(_URL.sub("", p).strip() for p in parts if p.strip()) + "\n"


def synthesize(text: str, out: Path, voice: str = "", rate: int = 0) -> Path:
    """Voice `text` into `out` (.m4a -> AAC, .aiff -> AIFF) with macOS `say`."""
    say = shutil.which("say")
    if not say:
        raise RuntimeError("`say` not found (macOS only); use --script-only and a TTS tool of your choice")
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = out.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    cmd = [say, "-f", str(txt), "-o", str(out)]
    if out.suffix == ".m4a":
        cmd += ["--file-format=m4af", "--data-format=aac"]
    if voice:
        cmd += ["-v", voice]
    if rate:
        cmd += ["-r", str(rate)]
    subprocess.run(cmd, check=True, timeout=600)
    return out
