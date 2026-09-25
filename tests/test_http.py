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
