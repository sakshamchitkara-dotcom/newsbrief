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


class DeliveryError(Exception):
    pass


def send_smtp(msg: EmailMessage, env: dict[str, str]) -> None:
    """SMTP with STARTTLS (587, default) or implicit TLS (465)."""
    import smtplib
    import ssl

    host = env.get("SMTP_HOST")
    if not host:
        raise DeliveryError("SMTP_HOST is not set")
    port = int(env.get("SMTP_PORT") or 587)
    ctx = ssl.create_default_context()
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls(context=ctx)  # refuse to send credentials in the clear
        with server:
            if env.get("SMTP_USER"):
                server.login(env["SMTP_USER"], env.get("SMTP_PASS", ""))
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise DeliveryError(f"smtp: {e}") from e
