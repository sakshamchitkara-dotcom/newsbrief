"""Signed unsubscribe tokens and List-Unsubscribe headers."""
from __future__ import annotations

import hashlib
import hmac
import os
from email.utils import parseaddr
from urllib.parse import urlencode


def _secret() -> bytes:
    s = os.environ.get("NEWSBRIEF_SECRET", "")
    if not s:
        # ponytail: dev-only default so dry runs work; real sends should set NEWSBRIEF_SECRET
        s = "newsbrief-dev-secret"
    return s.encode()


def make_token(email: str) -> str:
    return hmac.new(_secret(), email.strip().lower().encode(), hashlib.sha256).hexdigest()[:32]


def verify_token(email: str, token: str) -> bool:
    return hmac.compare_digest(make_token(email), token or "")


def unsubscribe_url(base_url: str, email: str) -> str:
    if not base_url:
        return ""
    return f"{base_url.rstrip('/')}/unsubscribe?" + urlencode({"email": email, "token": make_token(email)})


def list_unsubscribe_headers(base_url: str, from_email: str, email: str) -> dict[str, str]:
    """RFC 2369 List-Unsubscribe (+ RFC 8058 one-click when an https endpoint exists)."""
    targets = []
    url = unsubscribe_url(base_url, email)
    if url:
        targets.append(f"<{url}>")
    sender = parseaddr(from_email)[1]
    if sender:
        targets.append(f"<mailto:{sender}?subject=unsubscribe%20{make_token(email)}>")
    headers = {"List-Unsubscribe": ", ".join(targets)} if targets else {}
    if url.startswith("https://"):
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    return headers
