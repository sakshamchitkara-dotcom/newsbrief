"""Render a Brief as a responsive, inline-styled HTML email plus plain text."""
from __future__ import annotations

import textwrap
from datetime import datetime
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


def _domain(url: str) -> str:
    return urlsplit(url).netloc.removeprefix("www.")


def group_by_topic(stories: list[Story]) -> list[tuple[str, list[Story]]]:
    """Keep rank order: sections appear in the order of their best story."""
    order: dict[str, list[Story]] = {}
    for s in stories:
        order.setdefault(s.topic or "news", []).append(s)
    return list(order.items())


def _story_html(s: Story) -> str:
    link = lambda url, label: f'<a href="{escape(url)}" style="color:{MUTED};text-decoration:underline;">{escape(label)}</a>'  # noqa: E731
    links = " &middot; ".join(
        link(a.url, a.source) + (f" ({link(a.comments_url, f'{a.score} pts, discuss')})" if a.comments_url else "")
        for a in s.articles[:5]
    )
    more = f" +{len(s.articles) - 5} more" if len(s.articles) > 5 else ""
    why = (
        f'<p style="margin:8px 0 0;font:italic 15px/1.5 {SERIF};color:{INK};">'
        f'<span style="color:{ACCENT};font-style:normal;font-weight:bold;">Why it matters:</span> '
        f"{escape(s.why_it_matters)}</p>"
        if s.why_it_matters
        else ""
    )
    coverage = (
        f'<span style="display:inline-block;margin-left:6px;padding:1px 6px;border-radius:9px;'
        f'background:{BG};color:{ACCENT};font:bold 11px/1.6 {SANS};">{len(s.sources)} outlets</span>'
        if len(s.sources) > 1
        else ""
    )
    minutes = f" &middot; {s.reading_minutes} min read" if s.reading_minutes else ""
    return f"""
<tr><td style="padding:18px 0;border-top:1px solid {RULE};">
  <a href="{escape(s.lead.url)}" style="color:{INK};text-decoration:none;font:bold 20px/1.3 {SERIF};">{escape(s.headline or s.lead.title)}</a>{coverage}
  <p style="margin:8px 0 0;font:16px/1.55 {SERIF};color:{INK};">{escape(s.summary)}</p>{why}
  <p style="margin:10px 0 0;font:13px/1.5 {SANS};color:{MUTED};">{links}{more}{minutes}</p>
</td></tr>"""


def render_html(brief: Brief, *, date: datetime, name: str = "", unsubscribe_url: str = "") -> str:
    sections = []
    for topic, stories in group_by_topic(brief.stories):
        sections.append(
            f'<tr><td style="padding:26px 0 4px;font:bold 12px/1 {SANS};letter-spacing:.12em;'
            f'text-transform:uppercase;color:{ACCENT};">{escape(topic)}</td></tr>'
            + "".join(_story_html(s) for s in stories)
        )
    body = "".join(sections) or (
        f'<tr><td style="padding:24px 0;font:16px/1.5 {SERIF};color:{MUTED};">'
        "Nothing new since your last brief. Enjoy the quiet.</td></tr>"
    )
    greeting = f"Good morning{', ' + escape(name) if name else ''}."
    unsub = (
        f'<a href="{escape(unsubscribe_url)}" style="color:{MUTED};">Unsubscribe</a> &middot; '
        if unsubscribe_url
        else ""
    )
    datestr = f"{date:%A, %B} {date.day}, {date.year}"
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
<title>Your news brief &middot; {escape(datestr)}</title>
<style>@media (max-width:620px){{.wrap{{padding:20px 16px!important}}}}</style>
</head>
<body style="margin:0;padding:0;background:{BG};">
<div style="display:none;max-height:0;overflow:hidden;">{escape(brief.intro)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};">
<tr><td align="center" style="padding:24px 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="wrap"
 style="max-width:640px;background:#ffffff;border-radius:6px;padding:32px 36px;">
<tr><td style="border-bottom:3px double {INK};padding-bottom:14px;">
  <div style="font:bold 34px/1.1 {SERIF};color:{INK};">The Daily Brief</div>
  <div style="margin-top:6px;font:13px/1.4 {SANS};color:{MUTED};">{escape(datestr)} &middot; {len(brief.stories)} stories</div>
</td></tr>
<tr><td style="padding:18px 0 0;font:17px/1.55 {SERIF};color:{INK};">
  <strong>{greeting}</strong> {escape(brief.intro)}
</td></tr>
{body}
<tr><td style="padding:22px 0 0;border-top:1px solid {RULE};font:12px/1.6 {SANS};color:{MUTED};">
  {unsub}Summaries by {escape(brief.summarizer)}. Headlines link to the original reporting.
</td></tr>
</table></td></tr></table>
</body></html>"""


def render_text(brief: Brief, *, date: datetime, name: str = "", unsubscribe_url: str = "") -> str:
    wrap = lambda s, indent="": textwrap.fill(s, 76, initial_indent=indent, subsequent_indent=indent)  # noqa: E731
    lines = [f"THE DAILY BRIEF - {date:%A, %B} {date.day}, {date.year}", "=" * 44, ""]
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
