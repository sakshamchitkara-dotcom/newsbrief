"""Static web archive of past briefs: index.html plus one page per day (GitHub Pages ready)."""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from html import escape
from pathlib import Path

from .models import Brief
from .render import ACCENT, BG, INK, MUTED, RULE, SANS, SERIF, render_html
from .state import State


def pick_daily(rows: list[tuple[str, str, Brief]]) -> dict[str, Brief]:
    """One brief per day: the fullest one when several subscribers got different cuts."""
    days: dict[str, Brief] = {}
    for day, _sub, brief in rows:
        if day not in days or len(brief.stories) > len(days[day].stories):
            days[day] = brief
    return days


def render_index(days: dict[str, Brief], title: str, feed: bool = False) -> str:
    items = []
    for day in sorted(days, reverse=True):
        b, d = days[day], Date.fromisoformat(day)
        lead = escape(b.stories[0].headline or b.stories[0].lead.title) if b.stories else "A quiet news day"
        items.append(
            f'<li style="padding:14px 0;border-top:1px solid {RULE};list-style:none;">'
            f'<a href="{day}.html" style="color:{INK};text-decoration:none;font:bold 18px/1.35 {SERIF};">'
            f"{d:%A, %B} {d.day}, {d.year}</a>"
            f'<div style="margin-top:4px;font:15px/1.5 {SERIF};color:{INK};">{lead}</div>'
            f'<div style="margin-top:2px;font:13px/1.4 {SANS};color:{MUTED};">{len(b.stories)} stories</div></li>'
        )
    body = "".join(items) or f'<li style="list-style:none;color:{MUTED};">No briefs yet.</li>'
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>{'<link rel="alternate" type="application/atom+xml" href="feed.xml">' if feed else ''}
</head>
<body style="margin:0;padding:24px 16px;background:{BG};">
<main style="max-width:640px;margin:0 auto;background:#fff;border-radius:6px;padding:32px 28px;">
<h1 style="margin:0;padding-bottom:14px;border-bottom:3px double {INK};font:bold 34px/1.1 {SERIF};color:{INK};">{escape(title)}</h1>
<p style="font:14px/1.5 {SANS};color:{MUTED};">Past editions, newest first. <span style="color:{ACCENT};">{len(days)} briefs</span></p>
<ul style="margin:0;padding:0;">{body}</ul>
</main>
</body></html>"""


def render_feed(days: dict[str, Brief], title: str, site_url: str, limit: int = 30) -> str:
    """Atom feed of the newest briefs, one entry per day, linking to the day pages."""
    base = site_url.rstrip("/") + "/"
    entries = []
    for day in sorted(days, reverse=True)[:limit]:
        b = days[day]
        lead = b.stories[0].headline or b.stories[0].lead.title if b.stories else "A quiet news day"
        items = "".join(f"<li>{escape(s.headline or s.lead.title)}</li>" for s in b.stories)
        updated = (b.generated_at.isoformat() if b.generated_at else f"{day}T00:00:00+00:00")
        entries.append(
            f"<entry><id>{escape(base)}{day}.html</id><title>{escape(day)}: {escape(lead)}</title>"
            f'<link href="{escape(base)}{day}.html"/><updated>{updated}</updated>'
            f'<summary type="html">{escape(f"<p>{escape(b.intro)}</p><ul>{items}</ul>")}</summary></entry>'
        )
    newest = max(days) if days else "1970-01-01"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
        f"<id>{escape(base)}</id><title>{escape(title)}</title>"
        f'<link href="{escape(base)}"/><link rel="self" href="{escape(base)}feed.xml"/>'
        f"<updated>{newest}T00:00:00+00:00</updated>{''.join(entries)}</feed>\n"
    )


def build_site(state: State, out_dir: str | Path, *, subscriber: str | None = None,
               title: str = "The Daily Brief archive", site_url: str = "") -> list[Path]:
    """Write index.html and YYYY-MM-DD.html pages, plus feed.xml when the public site_url
    is known (Atom needs absolute links). Pages carry no subscriber names, emails or
    unsubscribe links, so the output can be published as is."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    days = pick_daily(state.briefs(subscriber))
    written = []
    for day, brief in days.items():
        d = Date.fromisoformat(day)
        page = out / f"{day}.html"
        page.write_text(render_html(brief, date=datetime(d.year, d.month, d.day), home_url="index.html"), encoding="utf-8")
        written.append(page)
    (out / "index.html").write_text(render_index(days, title, feed=bool(site_url)), encoding="utf-8")
    if site_url:
        (out / "feed.xml").write_text(render_feed(days, title, site_url), encoding="utf-8")
    (out / ".nojekyll").write_text("")  # serve files as-is on GitHub Pages
    return [out / "index.html", *written]
