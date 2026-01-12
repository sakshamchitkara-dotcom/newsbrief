"""Build MIME messages and deliver them (outbox for dry runs, SMTP, Resend, SendGrid)."""
from __future__ import annotations

import logging
import re
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path

log = logging.getLogger(__name__)


def build_message(
    *, from_email: str, to: str, subject: str, html: str, text: str, headers: dict[str, str] | None = None
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=parseaddr(from_email)[1].rpartition("@")[2] or "newsbrief.local")
    for k, v in (headers or {}).items():
        msg[k] = v
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def write_outbox(msg: EmailMessage, html: str, outbox: str | Path, stem: str) -> tuple[Path, Path]:
    """Dry-run delivery: save the full .eml and a browser-viewable .html."""
    out = Path(outbox)
    out.mkdir(parents=True, exist_ok=True)
    name = _slug(stem)
    eml, page = out / f"{name}.eml", out / f"{name}.html"
    eml.write_bytes(bytes(msg))
    page.write_text(html, encoding="utf-8")
    return eml, page
