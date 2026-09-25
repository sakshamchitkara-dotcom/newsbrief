"""Tiny HTTP layer: polite GETs with a UA, timeouts and robots.txt checks."""
from __future__ import annotations

import logging
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


def get(url: str, *, timeout: float = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(MAX_BYTES)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise FetchError(f"{url}: {e}") from e


@lru_cache(maxsize=256)
def _robots(origin: str) -> urllib.robotparser.RobotFileParser | None:
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
