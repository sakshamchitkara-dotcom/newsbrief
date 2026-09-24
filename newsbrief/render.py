"""Render a Brief as a responsive, inline-styled HTML email plus plain text."""
from __future__ import annotations

import textwrap
from datetime import date, datetime
from html import escape
from urllib.parse import urlsplit

from .models import Brief, Story

ACCENT = "#b4432b"
INK = "#1d1d1f"
MUTED = "#6e6e73"
RULE = "#e5e5ea"
BG = "#f4f1ea"
SERIF = "Georgia,'Times New Roman',serif"
SANS = "-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"

# Dark mode: inline styles carry the light palette (clients that ignore <style> get a light
# email); clients that honour prefers-color-scheme (Apple Mail, iOS, Outlook for Mac,
# Thunderbird) swap to these via the nb-* classes. Gmail ignores the query and applies its own.
DARK_CSS = (
    "@media (prefers-color-scheme:dark){"
    ".nb-bg{background:#1c1b19!important}"
    ".nb-card{background:#262522!important}"
    ".nb-ink{color:#ecebe7!important;border-color:#ecebe7!important}"
    ".nb-muted{color:#a8a7a1!important}"
    ".nb-rule{border-color:#3a3935!important}"
    ".nb-accent{color:#ec8a72!important}"
    ".nb-pill{background:#1c1b19!important;color:#ec8a72!important}"
    ".nb-day{background:#ec8a72!important;color:#1c1b19!important}}"
)


def _domain(url: str) -> str:
    return urlsplit(url).netloc.removeprefix("www.")


def group_by_topic(stories: list[Story]) -> list[tuple[str, list[Story]]]:
    """Keep rank order: sections appear in the order of their best story."""
    order: dict[str, list[Story]] = {}
    for s in stories:
        order.setdefault(s.topic or "news", []).append(s)
    return list(order.items())


def _since(s: Story) -> str:
    d = date.fromisoformat(s.since)
    return f"{d:%b} {d.day}"


def _story_html(s: Story, home_url: str = "") -> str:
    link = lambda url, label: f'<a class="nb-muted" href="{escape(url)}" style="color:{MUTED};text-decoration:underline;">{escape(label)}</a>'  # noqa: E731
    links = " &middot; ".join(
        link(a.url, a.source) + (f" ({link(a.comments_url, f'{a.score} pts, discuss')})" if a.comments_url else "")
        for a in s.articles[:5]
    )
    more = f" +{len(s.articles) - 5} more" if len(s.articles) > 5 else ""
    why = (
        f'<p class="nb-ink" style="margin:8px 0 0;font:italic 15px/1.5 {SERIF};color:{INK};">'
        f'<span class="nb-accent" style="color:{ACCENT};font-style:normal;font-weight:bold;">Why it matters:</span> '
        f"{escape(s.why_it_matters)}</p>"
        if s.why_it_matters
        else ""
    )
    coverage = (
        f'<span class="nb-pill" style="display:inline-block;margin-left:6px;padding:1px 6px;border-radius:9px;'
        f'background:{BG};color:{ACCENT};font:bold 11px/1.6 {SANS};">{len(s.sources)} outlets</span>'
        if len(s.sources) > 1
        else ""
    )
    if s.day > 1:
        coverage += (
            f'<span class="nb-day" style="display:inline-block;margin-left:6px;padding:1px 6px;border-radius:9px;'
            f'background:{ACCENT};color:#fff;font:bold 11px/1.6 {SANS};">Day {s.day}</span>'
        )
        # on archive pages the start date links to that day's brief
        since = (f'<a class="nb-muted" href="{escape(s.since)}.html" style="color:{MUTED};">{_since(s)}</a>' if home_url
                 else _since(s))
        why += (f'<p class="nb-muted" style="margin:8px 0 0;font:13px/1.5 {SANS};color:{MUTED};">Following since {since}. '
                f"Previously: {escape(s.previously)}</p>")
    minutes = f" &middot; {s.reading_minutes} min read" if s.reading_minutes else ""
    return f"""
<tr><td class="nb-rule" style="padding:18px 0;border-top:1px solid {RULE};">
  <a class="nb-ink" href="{escape(s.lead.url)}" style="color:{INK};text-decoration:none;font:bold 20px/1.3 {SERIF};">{escape(s.headline or s.lead.title)}</a>{coverage}
  <p class="nb-ink" style="margin:8px 0 0;font:16px/1.55 {SERIF};color:{INK};">{escape(s.summary)}</p>{why}
  <p class="nb-muted" style="margin:10px 0 0;font:13px/1.5 {SANS};color:{MUTED};">{links}{more}{minutes}</p>
</td></tr>"""


def render_html(
    brief: Brief, *, date: datetime, name: str = "", unsubscribe_url: str = "", home_url: str = "",
    title: str = "The Daily Brief",
) -> str:
    """home_url: link back to an archive index (web archive pages only)."""
    sections = []
    for topic, stories in group_by_topic(brief.stories):
        sections.append(
            f'<tr><td class="nb-accent" style="padding:26px 0 4px;font:bold 12px/1 {SANS};letter-spacing:.12em;'
            f'text-transform:uppercase;color:{ACCENT};">{escape(topic)}</td></tr>'
            + "".join(_story_html(s, home_url) for s in stories)
        )
    body = "".join(sections) or (
        f'<tr><td class="nb-muted" style="padding:24px 0;font:16px/1.5 {SERIF};color:{MUTED};">'
        "Nothing new since your last brief. Enjoy the quiet.</td></tr>"
    )
    greeting = f"Good morning{', ' + escape(name) if name else ''}."
    unsub = (
        f'<a class="nb-muted" href="{escape(unsubscribe_url)}" style="color:{MUTED};">Unsubscribe</a> &middot; '
        if unsubscribe_url
        else ""
    )
    datestr = f"{date:%A, %B} {date.day}, {date.year}"
    home = (
        f'<div style="margin-bottom:12px;font:13px/1.4 {SANS};"><a href="{escape(home_url)}" '
        f'class="nb-accent" style="color:{ACCENT};">&larr; All briefs</a></div>'
        if home_url
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<title>{escape(title)} &middot; {escape(datestr)}</title>
<style>@media (max-width:620px){{.wrap{{padding:20px 16px!important}}}}{DARK_CSS}</style>
</head>
<body class="nb-bg" style="margin:0;padding:0;background:{BG};">
<div style="display:none;max-height:0;overflow:hidden;">{escape(brief.intro)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="nb-bg" style="background:{BG};">
<tr><td align="center" style="padding:24px 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="wrap nb-card"
 style="max-width:640px;background:#ffffff;border-radius:6px;padding:32px 36px;">
<tr><td class="nb-ink" style="border-bottom:3px double {INK};padding-bottom:14px;">
  {home}<div class="nb-ink" style="font:bold 34px/1.1 {SERIF};color:{INK};">{escape(title)}</div>
  <div class="nb-muted" style="margin-top:6px;font:13px/1.4 {SANS};color:{MUTED};">{escape(datestr)} &middot; {len(brief.stories)} stories</div>
</td></tr>
<tr><td class="nb-ink" style="padding:18px 0 0;font:17px/1.55 {SERIF};color:{INK};">
  <strong>{greeting}</strong> {escape(brief.intro)}
</td></tr>
{body}
<tr><td class="nb-muted nb-rule" style="padding:22px 0 0;border-top:1px solid {RULE};font:12px/1.6 {SANS};color:{MUTED};">
  {unsub}Summaries by {escape(brief.summarizer)}. Headlines link to the original reporting.
</td></tr>
</table></td></tr></table>
</body></html>"""


def render_text(brief: Brief, *, date: datetime, name: str = "", unsubscribe_url: str = "",
                title: str = "The Daily Brief") -> str:
    wrap = lambda s, indent="": textwrap.fill(s, 76, initial_indent=indent, subsequent_indent=indent)  # noqa: E731
    lines = [f"{title.upper()} - {date:%A, %B} {date.day}, {date.year}", "=" * 44, ""]
    lines += [wrap(f"Good morning{', ' + name if name else ''}. {brief.intro}"), ""]
    if not brief.stories:
        lines += ["Nothing new since your last brief.", ""]
    for topic, stories in group_by_topic(brief.stories):
        lines += [f"## {topic.upper()}", ""]
        for s in stories:
            minutes = f" ({s.reading_minutes} min read)" if s.reading_minutes else ""
            lines += [wrap(f"* {s.headline or s.lead.title}{minutes}"), wrap(s.summary, "  ")]
            if s.why_it_matters:
                lines.append(wrap(f"Why it matters: {s.why_it_matters}", "  "))
            if s.day > 1:
                lines.append(wrap(f"Day {s.day}, following since {_since(s)}. Previously: {s.previously}", "  "))
            for a in s.articles[:5]:
                lines.append(f"  - {a.source}: {a.url}")
                if a.comments_url:
                    lines.append(f"    discussion ({a.score} pts): {a.comments_url}")
            lines.append("")
    lines.append("--")
    if unsubscribe_url:
        lines.append(f"Unsubscribe: {unsubscribe_url}")
    lines.append(f"Summaries by {brief.summarizer}.")
    return "\n".join(lines) + "\n"
