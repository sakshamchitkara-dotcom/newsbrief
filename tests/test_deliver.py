import email
from email import policy

from newsbrief.deliver import build_message, write_outbox


def msg():
    return build_message(
        from_email="Brief <b@example.com>", to="me@x.com", subject="Brief", html="<p>Hi é</p>", text="Hi é",
        headers={"List-Unsubscribe": "<mailto:b@example.com>"},
    )


def test_multipart_alternative_with_headers():
    m = msg()
    assert m.get_content_type() == "multipart/alternative"
    assert [p.get_content_type() for p in m.iter_parts()] == ["text/plain", "text/html"]
    assert m["List-Unsubscribe"] == "<mailto:b@example.com>"
    assert m["Message-ID"].endswith("@example.com>")


def test_outbox_roundtrip(tmp_path):
    eml, page = write_outbox(msg(), "<p>Hi é</p>", tmp_path / "out", "me@x.com 2026-09-25")
    assert eml.name == "me-x-com-2026-09-25.eml" and page.read_text() == "<p>Hi é</p>"
    parsed = email.message_from_bytes(eml.read_bytes(), policy=policy.default)
    assert parsed.get_body(("plain",)).get_content().strip() == "Hi é"


class FakeSMTP:
    instances = []

    def __init__(self, host, port, **kw):
        self.host, self.port, self.log = host, port, []
        FakeSMTP.instances.append(self)

    def starttls(self, context=None):
        self.log.append("starttls")

    def login(self, u, p):
        self.log.append(("login", u, p))

    def send_message(self, m):
        self.log.append(("send", m["To"]))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.log.append("quit")


def test_smtp_uses_starttls_then_login(monkeypatch):
    import smtplib

    from newsbrief.deliver import send_smtp

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    send_smtp(msg(), {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "u", "SMTP_PASS": "p"})
    s = FakeSMTP.instances[-1]
    assert (s.host, s.port) == ("smtp.example.com", 587)
    assert s.log == ["starttls", ("login", "u", "p"), ("send", "me@x.com"), "quit"]


def test_smtp_requires_host():
    import pytest

    from newsbrief.deliver import DeliveryError, send_smtp

    with pytest.raises(DeliveryError):
        send_smtp(msg(), {})


def test_api_payloads_carry_unsubscribe_header():
    from newsbrief.deliver import resend_payload, sendgrid_payload

    r = resend_payload(msg(), "<p>h</p>", "t")
    assert r["to"] == ["me@x.com"] and r["headers"] == {"List-Unsubscribe": "<mailto:b@example.com>"}
    s = sendgrid_payload(msg(), "<p>h</p>", "t")
    assert s["from"] == {"email": "b@example.com", "name": "Brief"}
    assert [c["type"] for c in s["content"]] == ["text/plain", "text/html"]


def test_send_api_posts_with_bearer(monkeypatch):
    from newsbrief import http
    from newsbrief.deliver import send

    calls = []
    monkeypatch.setattr(http, "post_json", lambda url, payload, headers: calls.append((url, headers)) or b"{}")
    assert send(msg(), "<p>h</p>", "t", {"RESEND_API_KEY": "re_123", "SMTP_HOST": "x"}) == "resend"
    assert calls == [("https://api.resend.com/emails", {"Authorization": "Bearer re_123"})]


def test_pick_transport():
    import pytest

    from newsbrief.deliver import DeliveryError, pick_transport

    assert pick_transport({"SMTP_HOST": "h", "NEWSBRIEF_TRANSPORT": "sendgrid"}) == "sendgrid"
    assert pick_transport({"SMTP_HOST": "h"}) == "smtp"
    with pytest.raises(DeliveryError):
        pick_transport({})
