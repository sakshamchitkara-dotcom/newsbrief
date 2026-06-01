"""Load YAML/JSON config describing sources and subscribers."""
from __future__ import annotations

import json
import re
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
    fetch_text: bool = True  # false for sites that block scripted article fetches (NPR: HTTP 402)


@dataclass
class Subscriber:
    email: str
    name: str = ""
    timezone: str = "UTC"
    send_at: str = "07:00"  # HH:MM local time
    topics: list[str] = field(default_factory=list)  # empty = all
    sources: list[str] = field(default_factory=list)  # empty = all
    max_stories: int | None = None
    topic_weights: dict[str, float] = field(default_factory=dict)  # {tech: 1.5, business: 0.5}
    boost: list[str] = field(default_factory=list)  # words/phrases that lift a story
    mute: list[str] = field(default_factory=list)  # words/phrases that drop a story


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

    known_topics = {t for s in sources.values() for t in s.topics} | {"news"}  # "news": untagged sources
    subs, emails = [], set()
    for raw in data.get("subscribers") or []:
        try:
            sub = Subscriber(**raw)
        except TypeError as e:
            raise ConfigError(f"subscriber {raw.get('email', raw)!r}: {e}") from e
        if sub.email.lower() in emails:
            raise ConfigError(f"duplicate subscriber {sub.email!r}")
        emails.add(sub.email.lower())
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
        if not isinstance(sub.topic_weights, dict) or not all(
            isinstance(w, (int, float)) and w >= 0 for w in sub.topic_weights.values()
        ):
            raise ConfigError(f"{sub.email}: topic_weights must map topics to numbers >= 0")
        typos = (set(sub.topics) | set(sub.topic_weights or {})) - known_topics
        if typos:
            raise ConfigError(f"{sub.email}: unknown topics {sorted(typos)}; sources cover {sorted(known_topics)}")
        subs.append(sub)

    top = {k: v for k, v in data.items() if k not in ("sources", "subscribers")}
    return Config(sources=sources, subscribers=subs, **top)


def load_config(path: str | Path) -> Config:
    return parse_config(load_raw(path))


def load_raw(path: str | Path) -> dict:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return (json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)) or {}


def save_subscribers(path: str | Path, subscribers: list[dict]) -> None:
    """Validate, then rewrite only the config's `subscribers:` section.

    The rest of a YAML file (comments included) is left as is; comments inside the
    subscribers section itself are not preserved.
    """
    path = Path(path)
    data = {**load_raw(path), "subscribers": subscribers}
    parse_config(data)  # never write a config that won't load
    if path.suffix == ".json":
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    block = yaml.safe_dump({"subscribers": subscribers}, sort_keys=False, allow_unicode=True, width=100)
    # the section runs to the next top-level key ("- item" lines at column 0 still belong to it)
    m = re.search(r"^subscribers:.*?(?=^[A-Za-z_][\w-]*\s*:|\Z)", text, re.M | re.S)
    text = text[: m.start()] + block + text[m.end() :] if m else text.rstrip("\n") + "\n\n" + block
    path.write_text(text, encoding="utf-8")
