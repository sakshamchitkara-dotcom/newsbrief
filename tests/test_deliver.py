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
