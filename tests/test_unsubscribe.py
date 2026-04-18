import pytest

from newsbrief.unsubscribe import list_unsubscribe_headers, require_secret, make_token, unsubscribe_url, verify_token


def test_tokens_are_per_email_and_secret(monkeypatch):
    monkeypatch.setenv("NEWSBRIEF_SECRET", "s1")
    t = make_token("Me@X.com ")
    assert verify_token("me@x.com", t) and not verify_token("you@x.com", t)
    monkeypatch.setenv("NEWSBRIEF_SECRET", "s2")
    assert not verify_token("me@x.com", t)
    assert not verify_token("me@x.com", "")


def test_headers_with_https_endpoint():
    h = list_unsubscribe_headers("https://brief.example.com/", "Brief <b@example.com>", "me@x.com")
    url = unsubscribe_url("https://brief.example.com/", "me@x.com")
    assert url.startswith("https://brief.example.com/unsubscribe?email=me%40x.com&token=")
    assert h["List-Unsubscribe"].startswith(f"<{url}>, <mailto:b@example.com?subject=unsubscribe%20")
    assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_headers_mailto_only_without_base_url():
    h = list_unsubscribe_headers("", "b@example.com", "me@x.com")
    assert h["List-Unsubscribe"].startswith("<mailto:b@example.com") and "List-Unsubscribe-Post" not in h


def test_real_sends_require_secret(monkeypatch):
    monkeypatch.delenv("NEWSBRIEF_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="NEWSBRIEF_SECRET"):
        require_secret()
    monkeypatch.setenv("NEWSBRIEF_SECRET", "s1")
    require_secret()
