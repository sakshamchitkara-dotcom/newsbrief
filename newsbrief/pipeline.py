"""End-to-end: collect -> cluster -> rank -> summarize -> render -> deliver."""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Config, Source, Subscriber
from .dedupe import cluster
from .deliver import build_message, send, write_outbox
from .extract import enrich
from .feeds import fetch_feed
from .hn import fetch_hn
from .http import FetchError
from .models import Article, Brief
from .rank import diversify, rank, within
from .render import render_html, render_text
from .scrape import fetch_page
from .state import State
from .summarize import summarize
from .unsubscribe import list_unsubscribe_headers, require_secret, unsubscribe_url

log = logging.getLogger(__name__)
FETCHERS = {"rss": fetch_feed, "hackernews": fetch_hn, "page": fetch_page}


def collect(sources: list[Source]) -> dict[str, list[Article]]:
    """Fetch every source in parallel; a failing source is logged and skipped."""

    def one(src: Source) -> tuple[str, list[Article]]:
        try:
            arts = FETCHERS[src.type](src)
            log.info("%-14s %3d items", src.name, len(arts))
            return src.name, arts
        except FetchError as e:
            log.warning("source %s failed: %s", src.name, e)
            return src.name, []

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(one, sources))


def build_brief(
    cfg: Config,
    sub: Subscriber,
    articles: dict[str, list[Article]],
    state: State,
    now: datetime,
    *,
    fetch_text: bool = True,
    use_claude: bool | None = None,
) -> Brief:
    mine = [a for s in cfg.sources_for(sub) for a in articles.get(s.name, [])]
    stories = [s for s in rank(cluster(mine), cfg.sources, now) if within(s, now, cfg.lookback_hours)]
    stories = diversify(state.unseen(sub.email, stories), sub.max_stories or cfg.max_stories, cfg.max_per_topic)
    if fetch_text:
        feed_only = {name for name, src in cfg.sources.items() if not src.fetch_text}
        enrich([s.lead for s in stories if s.lead.source not in feed_only])
    brief = Brief(sub.email, stories, generated_at=now)
    return summarize(brief, use_claude=use_claude)


@dataclass
class Outcome:
    subscriber: str
    stories: int
    transport: str
    paths: tuple[Path, Path] | None = None


def deliver_brief(
    cfg: Config, sub: Subscriber, brief: Brief, state: State, now: datetime, *, dry_run: bool
) -> Outcome:
    local = now.astimezone(ZoneInfo(sub.timezone))
    unsub = unsubscribe_url(cfg.base_url, sub.email)
    html = render_html(brief, date=local, name=sub.name, unsubscribe_url=unsub)
    text = render_text(brief, date=local, name=sub.name, unsubscribe_url=unsub)
    lead = brief.stories[0].headline if brief.stories else "a quiet news day"
    msg = build_message(
        from_email=cfg.from_email,
        to=sub.email,
        subject=f"Daily Brief, {local:%b} {local.day}: {lead}",
        html=html,
        text=text,
        headers=list_unsubscribe_headers(cfg.base_url, cfg.from_email, sub.email),
    )
    if dry_run:
        paths = write_outbox(msg, html, cfg.outbox, f"{sub.email} {local:%Y-%m-%d}")
        return Outcome(sub.email, len(brief.stories), "outbox", paths)
    transport = send(msg, html, text, dict(os.environ))
    state.record(sub.email, local.date().isoformat(), brief.stories)
    return Outcome(sub.email, len(brief.stories), transport)


def is_due(sub: Subscriber, now: datetime, state: State) -> bool:
    """True once the subscriber's local send time has passed and today's brief hasn't gone out."""
    local = now.astimezone(ZoneInfo(sub.timezone))
    h, m = (int(x) for x in sub.send_at.split(":"))
    return (local.hour, local.minute) >= (h, m) and not state.delivered(sub.email, local.date().isoformat())


def run(
    cfg: Config,
    *,
    dry_run: bool,
    only_due: bool = False,
    subscriber: str | None = None,
    now: datetime | None = None,
    fetch_text: bool | None = None,
    dry_run_log: set[tuple[str, str]] | None = None,
) -> list[Outcome]:
    """dry_run_log: (email, local date) pairs already written to the outbox by a
    long-running scheduler, since dry runs deliberately leave the state db untouched."""
    if not dry_run:
        require_secret()
    now = now or datetime.now(timezone.utc)
    dry_run_log = set() if dry_run_log is None else dry_run_log

    def local_day(s: Subscriber) -> tuple[str, str]:
        return s.email.lower(), now.astimezone(ZoneInfo(s.timezone)).date().isoformat()

    state = State(cfg.state_db)
    try:
        subs = [
            s
            for s in cfg.subscribers
            if (subscriber is None or s.email.lower() == subscriber.lower())
            and not state.is_unsubscribed(s.email)
            and (not only_due or (is_due(s, now, state) and local_day(s) not in dry_run_log))
        ]
        if not subs:
            log.info("no subscribers to deliver to")
            return []
        needed = {src.name: src for s in subs for src in cfg.sources_for(s)}
        articles = collect(list(needed.values()))
        outcomes = []
        for sub in subs:
            brief = build_brief(
                cfg, sub, articles, state, now,
                fetch_text=cfg.fetch_articles if fetch_text is None else fetch_text,
            )
            out = deliver_brief(cfg, sub, brief, state, now, dry_run=dry_run)
            if dry_run:
                dry_run_log.add(local_day(sub))
            log.info("%s: %d stories via %s", out.subscriber, out.stories, out.transport)
            outcomes.append(out)
        return outcomes
    finally:
        state.close()
