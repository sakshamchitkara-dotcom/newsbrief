"""Tiny HTTP layer: polite GETs with a UA, timeouts, robots.txt checks, retries
and a per-domain circuit breaker."""
from __future__ import annotations

import logging
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from functools import lru_cache
from urllib.parse import urlsplit

from . import __version__

log = logging.getLogger(__name__)
USER_AGENT = f"newsbrief/{__version__} (+https://github.com/sakshamchitkara-dotcom/newsbrief)"
TIMEOUT = 15
MAX_BYTES = 5_000_000


class FetchError(Exception):
    pass


BLOCKED = {401, 402, 403, 451}  # the site refuses scripted fetches: no point retrying today
RETRY = {429, 500, 502, 503, 504}
RETRIES = 2
BACKOFF = 1.0  # seconds, doubled per retry; Retry-After wins when the server sends it
MAX_WAIT = 10.0
TRIP_AFTER = 3  # consecutive failures before a domain's circuit opens
COOLDOWN = 300.0  # seconds a tripped domain is skipped
BLOCKED_COOLDOWN = 3600.0

_sleep = time.sleep
_clock = time.monotonic
_lock = threading.Lock()
_fails: dict[str, int] = {}
_open_until: dict[str, float] = {}


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def reset_breakers() -> None:
    with _lock:
        _fails.clear()
        _open_until.clear()


def _failed(host: str, blocked: bool) -> None:
    with _lock:
        _fails[host] = _fails.get(host, 0) + 1
        if blocked or _fails[host] >= TRIP_AFTER:
            _open_until[host] = _clock() + (BLOCKED_COOLDOWN if blocked else COOLDOWN)
            log.warning("circuit open for %s (%s)", host, "blocked" if blocked else f"{_fails[host]} failures")


def _retry_after(e: urllib.error.HTTPError, attempt: int) -> float:
    try:
        return min(float(e.headers.get("Retry-After", "")), MAX_WAIT)
    except (TypeError, ValueError):
        return min(BACKOFF * 2**attempt, MAX_WAIT)


def get(url: str, *, timeout: float = TIMEOUT) -> bytes:
    """GET with retries on 429/5xx. A domain that keeps failing, or answers 401/402/403,
    is skipped for a while instead of costing a timeout per article."""
    host = _host(url)
    with _lock:
        if _open_until.get(host, 0) > _clock():
            raise FetchError(f"{url}: skipped, circuit open for {host}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(MAX_BYTES)
            with _lock:
                _fails.pop(host, None)
            return body
        except urllib.error.HTTPError as e:
            if e.code in RETRY and attempt < RETRIES:
                _sleep(_retry_after(e, attempt))
                continue
            _failed(host, blocked=e.code in BLOCKED)
            raise FetchError(f"{url}: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            _failed(host, blocked=False)
            raise FetchError(f"{url}: {e}") from e
    raise AssertionError("unreachable")


ROBOTS_TTL = 6 * 3600.0  # `newsbrief schedule` runs for weeks: re-read robots.txt a few times a day


def _robots(origin: str) -> urllib.robotparser.RobotFileParser | None:
    return _robots_cached(origin, int(_clock() // ROBOTS_TTL))


@lru_cache(maxsize=256)
def _robots_cached(origin: str, _epoch: int) -> urllib.robotparser.RobotFileParser | None:
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(get(origin + "/robots.txt", timeout=8).decode("utf-8", "replace").splitlines())
    except FetchError:
        return None  # unreachable robots.txt -> treat as allowed, like most crawlers
    return rp


def allowed(url: str) -> bool:
    parts = urlsplit(url)
    rp = _robots(f"{parts.scheme}://{parts.netloc}")
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def polite_get(url: str) -> bytes:
    """GET that refuses URLs disallowed by the site's robots.txt."""
    if not allowed(url):
        raise FetchError(f"{url}: disallowed by robots.txt")
    return get(url)


def post_json(url: str, payload: dict, headers: dict[str, str], *, timeout: float = 30) -> bytes:
    import json

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise FetchError(f"{url}: HTTP {e.code}: {e.read()[:300]!r}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise FetchError(f"{url}: {e}") from e
