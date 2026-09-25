"""Load YAML/JSON config describing sources and subscribers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

SOURCE_TYPES = {"rss", "hackernews", "page"}


class ConfigError(ValueError):
    pass


@dataclass
class Source:
    name: str
    type: str
    url: str = ""
    weight: float = 1.0
    topics: list[str] = field(default_factory=list)
    limit: int = 30


@dataclass
class Subscriber:
    email: str
    name: str = ""
    timezone: str = "UTC"
    send_at: str = "07:00"  # HH:MM local time
    topics: list[str] = field(default_factory=list)  # empty = all
    sources: list[str] = field(default_factory=list)  # empty = all
    max_stories: int | None = None


@dataclass
class Config:
    sources: dict[str, Source]
    subscribers: list[Subscriber]
    from_email: str = "News Brief <brief@localhost>"
    base_url: str = ""  # public URL serving unsubscribe endpoint, optional
    state_db: str = "newsbrief.db"
    outbox: str = "outbox"
    max_stories: int = 12
    max_per_topic: int = 5
    lookback_hours: int = 36
    fetch_articles: bool = True

    def sources_for(self, sub: Subscriber) -> list[Source]:
        out = []
        for s in self.sources.values():
            if sub.sources and s.name not in sub.sources:
                continue
            if sub.topics and not set(sub.topics) & set(s.topics):
                continue
            out.append(s)
        return out


def _parse_hhmm(v: str) -> None:
    try:
        h, m = (int(x) for x in str(v).split(":"))
        assert 0 <= h < 24 and 0 <= m < 60
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"send_at must be HH:MM, got {v!r}") from e


def parse_config(data: dict) -> Config:
    if not isinstance(data, dict):
        raise ConfigError("config must be a mapping")
    sources = {}
    for name, raw in (data.get("sources") or {}).items():
        raw = dict(raw or {})
        stype = raw.pop("type", "rss")
        if stype not in SOURCE_TYPES:
            raise ConfigError(f"source {name}: unknown type {stype!r}")
        if stype != "hackernews" and not raw.get("url"):
            raise ConfigError(f"source {name}: url is required")
        sources[name] = Source(name=name, type=stype, **raw)
    if not sources:
        raise ConfigError("at least one source is required")

    subs = []
    for raw in data.get("subscribers") or []:
        sub = Subscriber(**raw)
        if "@" not in sub.email:
            raise ConfigError(f"invalid subscriber email {sub.email!r}")
        try:
            ZoneInfo(sub.timezone)
        except Exception as e:  # noqa: BLE001
            raise ConfigError(f"{sub.email}: unknown timezone {sub.timezone!r}") from e
        _parse_hhmm(sub.send_at)
        unknown = set(sub.sources) - set(sources)
        if unknown:
            raise ConfigError(f"{sub.email}: unknown sources {sorted(unknown)}")
        subs.append(sub)

    top = {k: v for k, v in data.items() if k not in ("sources", "subscribers")}
    return Config(sources=sources, subscribers=subs, **top)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    data = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    return parse_config(data)
