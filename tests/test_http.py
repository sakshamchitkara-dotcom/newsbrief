import io
import urllib.error
import urllib.request

import pytest

from newsbrief import http


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    http.reset_breakers()
    now = [0.0]
    monkeypatch.setattr(http, "_clock", lambda: now[0])
    monkeypatch.setattr(http, "_sleep", lambda s: now.__setitem__(0, now[0] + s))
    yield now
    http.reset_breakers()


def responder(monkeypatch, *codes):
    """urlopen that answers with the given status codes in turn (200 = body b'ok')."""
    calls = []

    def fake(req, timeout):
        calls.append(req.full_url)
        code = codes[min(len(calls), len(codes)) - 1]
        if code == 200:
            return io.BytesIO(b"ok")
        raise urllib.error.HTTPError(req.full_url, code, "x", {"Retry-After": "3"} if code == 429 else {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return calls


def test_retries_rate_limits_honouring_retry_after(monkeypatch, fresh):
    calls = responder(monkeypatch, 429, 503, 200)
    assert http.get("https://a.example/x") == b"ok"
    assert len(calls) == 3 and fresh[0] == 3 + 2  # Retry-After 3s, then 2s backoff


def test_blocking_status_opens_circuit_immediately(monkeypatch, fresh):
    calls = responder(monkeypatch, 402)
    with pytest.raises(http.FetchError, match="HTTP 402"):
        http.get("https://npr.example/a")
    with pytest.raises(http.FetchError, match="circuit open"):
        http.get("https://npr.example/b")
    assert len(calls) == 1  # no retry, no second request
    responder(monkeypatch, 200)
    assert http.get("https://other.example/a") == b"ok"  # other domains unaffected


def test_repeated_failures_trip_then_cool_down(monkeypatch, fresh):
    calls = responder(monkeypatch, 404)
    for _ in range(http.TRIP_AFTER):
        with pytest.raises(http.FetchError, match="404"):
            http.get("https://flaky.example/a")
    with pytest.raises(http.FetchError, match="circuit open"):
        http.get("https://flaky.example/a")
    assert len(calls) == http.TRIP_AFTER
    fresh[0] += http.COOLDOWN + 1
    responder(monkeypatch, 200)
    assert http.get("https://flaky.example/a") == b"ok"


def test_success_resets_failure_count(monkeypatch):
    responder(monkeypatch, 404, 404, 200, 404, 404)
    for _ in range(2):
        with pytest.raises(http.FetchError):
            http.get("https://x.example/a")
    assert http.get("https://x.example/a") == b"ok"
    for _ in range(2):
        with pytest.raises(http.FetchError, match="404"):
            http.get("https://x.example/a")  # still under TRIP_AFTER since the success


def test_robots_txt_is_refetched_after_ttl(monkeypatch):
    fetched = []

    def fake_get(url, timeout=0):
        fetched.append(url)
        return b"User-agent: *\nDisallow: /private" if len(fetched) == 1 else b"User-agent: *\nDisallow:"

    t = [0.0]
    monkeypatch.setattr(http, "get", fake_get)
    monkeypatch.setattr(http, "_clock", lambda: t[0])
    http._robots_cached.cache_clear()
    assert not http.allowed("https://ttl.example/private/x")
    assert not http.allowed("https://ttl.example/private/y") and len(fetched) == 1  # cached
    t[0] += http.ROBOTS_TTL
    assert http.allowed("https://ttl.example/private/x") and len(fetched) == 2  # site changed its rules


def test_post_json_sends_json_and_reports_the_error_body(monkeypatch):
    import json

    seen = []

    def fake(req, timeout):
        seen.append((req.get_method(), req.headers, json.loads(req.data)))
        if len(seen) == 1:
            return io.BytesIO(b'{"id": "1"}')
        if len(seen) == 2:
            raise urllib.error.HTTPError(req.full_url, 422, "x", {}, io.BytesIO(b'{"message": "invalid from"}'))
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert http.post_json("https://api.example/send", {"to": ["a@b"]}, {"Authorization": "Bearer k"}) == b'{"id": "1"}'
    method, headers, body = seen[0]
    assert method == "POST" and body == {"to": ["a@b"]}
    assert headers["Authorization"] == "Bearer k" and headers["Content-type"] == "application/json"
    with pytest.raises(http.FetchError, match="HTTP 422: .*invalid from"):
        http.post_json("https://api.example/send", {}, {})
    with pytest.raises(http.FetchError, match="name resolution failed"):
        http.post_json("https://api.example/send", {}, {})
