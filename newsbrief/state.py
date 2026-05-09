"""SQLite state: which stories each subscriber already got, deliveries, unsubscribes."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .dedupe import normalize_url
from .models import Brief, Story

SCHEMA = """
CREATE TABLE IF NOT EXISTS sent_urls (
    subscriber TEXT NOT NULL,
    url TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (subscriber, url)
);
CREATE TABLE IF NOT EXISTS deliveries (
    subscriber TEXT NOT NULL,
    local_date TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    story_count INTEGER NOT NULL,
    PRIMARY KEY (subscriber, local_date)
);
CREATE TABLE IF NOT EXISTS briefs (
    subscriber TEXT NOT NULL,
    local_date TEXT NOT NULL,
    saved_at TEXT NOT NULL,
    brief TEXT NOT NULL,  -- Brief.to_json()
    PRIMARY KEY (subscriber, local_date)
);
CREATE TABLE IF NOT EXISTS unsubscribed (
    subscriber TEXT PRIMARY KEY,
    at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class State:
    def __init__(self, path: str) -> None:
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def unseen(self, subscriber: str, stories: list[Story]) -> list[Story]:
        seen = {r[0] for r in self.db.execute("SELECT url FROM sent_urls WHERE subscriber=?", (subscriber.lower(),))}
        return [s for s in stories if not any(normalize_url(u) in seen for u in s.urls)]

    def record(self, subscriber: str, local_date: str, stories: list[Story]) -> None:
        sub, now = subscriber.lower(), _now()
        with self.db:
            self.db.executemany(
                "INSERT OR IGNORE INTO sent_urls VALUES (?,?,?)",
                [(sub, normalize_url(u), now) for s in stories for u in s.urls],
            )
            self.db.execute(
                "INSERT OR REPLACE INTO deliveries VALUES (?,?,?,?)", (sub, local_date, now, len(stories))
            )

    def delivered(self, subscriber: str, local_date: str) -> bool:
        q = "SELECT 1 FROM deliveries WHERE subscriber=? AND local_date=?"
        return self.db.execute(q, (subscriber.lower(), local_date)).fetchone() is not None

    def unsubscribe(self, subscriber: str) -> None:
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO unsubscribed VALUES (?,?)", (subscriber.lower(), _now()))

    def is_unsubscribed(self, subscriber: str) -> bool:
        q = "SELECT 1 FROM unsubscribed WHERE subscriber=?"
        return self.db.execute(q, (subscriber.lower(),)).fetchone() is not None

    def save_brief(self, subscriber: str, local_date: str, brief: Brief) -> None:
        """Keep the day's brief for the web archive; a later run the same day replaces it."""
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO briefs VALUES (?,?,?,?)", (subscriber.lower(), local_date, _now(), brief.to_json())
            )

    def briefs(self, subscriber: str | None = None) -> list[tuple[str, str, Brief]]:
        """(local_date, subscriber, brief), oldest first."""
        q, args = "SELECT local_date, subscriber, brief FROM briefs", ()
        if subscriber:
            q, args = q + " WHERE subscriber=?", (subscriber.lower(),)
        return [(d, s, Brief.from_json(b)) for d, s, b in self.db.execute(q + " ORDER BY local_date, subscriber", args)]
