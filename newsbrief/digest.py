"""Weekly digest: the week's biggest stories, rebuilt from the briefs stored each day."""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Config, Subscriber
from .dedupe import idf_weights, normalize_url, promote_names, similar, source_boilerplate, terms
from .deliver import build_message, send, write_outbox
from .models import Brief, Story
from .render import render_html, render_text
from .state import State
from .unsubscribe import list_unsubscribe_headers, require_secret, unsubscribe_url


def _threads(rows: list[tuple[str, Story]]) -> list[list[tuple[str, Story]]]:
    """Link each day's stories to earlier days' threads. Stories from one day never share a
    thread: that day's clustering, on the full feeds, already decided they differ. A story
    joins the newest thread it continues, by (1) the daily tracker's own link ("previously"
    names the thread's last headline), (2) a shared article URL, or (3) the clustering test
    over the stored articles, whose idf comes from every article of the week rather than
    one headline per story (too small a corpus: a reworded Trump/Xi story split in two)."""
    arts = [a for _, s in rows for a in s.articles[:5]]
    boiler = source_boilerplate(arts)
    t = {id(a): terms(a, boiler.get(a.source, set())) for a in arts}
    promote_names(list(t.values()))
    idf = idf_weights([x.keywords for x in t.values()])

    def continues(s: Story, prev: Story) -> bool:
        if s.previously and s.previously == prev.headline:
            return True
        if {normalize_url(u) for u in s.urls} & {normalize_url(u) for u in prev.urls}:
            return True
        return any(similar(x, y, t[id(x)], t[id(y)], idf, len(arts)) for x in s.articles[:5] for y in prev.articles[:5])

    threads: list[list[tuple[str, Story]]] = []
    for d, s in sorted(rows, key=lambda r: r[0]):
        for th in sorted(threads, key=lambda th: th[-1][0], reverse=True):  # newest thread first
            if th[-1][0] < d and continues(s, th[-1][1]):
                th.append((d, s))
                break
        else:
            threads.append([(d, s)])
    return threads


def weekly(rows: list[tuple[str, Story]], n: int = 10) -> list[Story]:
    """Group the week's stories (date, story) into threads and keep the n biggest.

    A thread is scored by how many days it ran, then how many outlets covered it. Each
    thread is shown as its latest story, with `since` set to its first day and `day`
    to the number of days it appeared."""
    out = []
    for members in _threads(rows):
        days = sorted({d for d, _ in members})
        outlets = {src for _, s in members for src in s.sources}
        latest = members[-1][1]
        out.append(replace(latest, since=days[0], day=len(days), rank=len(days) + len(outlets) / 10,
                           previously=members[0][1].headline if len(days) > 1 else ""))
    return sorted(out, key=lambda s: s.rank, reverse=True)[:n]


def build_digest(state: State, sub: Subscriber, today: date, days: int = 7, n: int = 10) -> Brief:
    start = (today - timedelta(days=days - 1)).isoformat()
    rows = [(d, s) for d, _, b in state.briefs(sub.email) if start <= d <= today.isoformat() for s in b.stories]
    stories = weekly(rows, n)
    ran = len({d for d, _ in rows})
    intro = (f"The {len(stories)} biggest stories from your last {ran} briefs." if stories
             else "No briefs were stored this week.")
    return Brief(sub.email, stories, intro=intro, generated_at=datetime.now(timezone.utc), summarizer="your daily briefs")


def run_digest(cfg: Config, *, dry_run: bool, subscriber: str | None = None, days: int = 7,
               now: datetime | None = None) -> list[tuple[str, int, str, Path | None]]:
    """Send the digest to subscribers with `weekly: true` (or just `subscriber`).
    Returns (email, stories, transport, outbox html path)."""
    if not dry_run:
        require_secret()
    now = now or datetime.now(timezone.utc)
    state = State(cfg.state_db)
    out = []
    try:
        for sub in cfg.subscribers:
            if (subscriber and sub.email.lower() != subscriber.lower()) or (not subscriber and not sub.weekly):
                continue
            if state.is_unsubscribed(sub.email):
                continue
            local = now.astimezone(ZoneInfo(sub.timezone))
            brief = build_digest(state, sub, local.date(), days)
            unsub = unsubscribe_url(cfg.base_url, sub.email)
            first = local - timedelta(days=days - 1)
            html = render_html(brief, date=local, name=sub.name, unsubscribe_url=unsub, title="The Weekly Brief")
            text = render_text(brief, date=local, name=sub.name, unsubscribe_url=unsub, title="The Weekly Brief")
            msg = build_message(
                from_email=cfg.from_email, to=sub.email,
                subject=f"Weekly Brief, {first:%b} {first.day}-{local:%b} {local.day}", html=html, text=text,
                headers=list_unsubscribe_headers(cfg.base_url, cfg.from_email, sub.email),
            )
            if dry_run:
                _, page = write_outbox(msg, html, cfg.outbox, f"{sub.email} weekly {local:%Y-%m-%d}")
                out.append((sub.email, len(brief.stories), "outbox", page))
            else:
                out.append((sub.email, len(brief.stories), send(msg, html, text, dict(os.environ)), None))
    finally:
        state.close()
    return out
