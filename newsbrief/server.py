"""Minimal unsubscribe endpoint (stdlib http.server).

GET  /unsubscribe?email=..&token=..  -> confirmation page with a button
POST /unsubscribe?email=..&token=..  -> unsubscribes (RFC 8058 one-click compatible)
Put it behind a TLS-terminating proxy and set `base_url` in the config.
"""
from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .state import State
from .unsubscribe import verify_token


def make_handler(state_db: str):
    class Handler(BaseHTTPRequestHandler):
        def _params(self) -> tuple[str, str] | None:
            u = urlsplit(self.path)
            if u.path.rstrip("/") != "/unsubscribe":
                return None
            q = parse_qs(u.query)
            email, token = q.get("email", [""])[0], q.get("token", [""])[0]
            return (email, token) if email and verify_token(email, token) else ("", "")

        def _page(self, code: int, body: str) -> None:
            data = f"<!doctype html><meta charset=utf-8><title>Unsubscribe</title><body style='font:16px system-ui;max-width:32em;margin:4em auto'>{body}".encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            p = self._params()
            if p is None:
                return self._page(404, "Not found")
            if not p[0]:
                return self._page(400, "This unsubscribe link is invalid or expired.")
            self._page(200, f"<p>Stop sending the daily brief to <b>{escape(p[0])}</b>?</p>"
                            f"<form method=post><button>Unsubscribe</button></form>")

        def do_POST(self):  # noqa: N802
            p = self._params()
            if p is None:
                return self._page(404, "Not found")
            if not p[0]:
                return self._page(400, "This unsubscribe link is invalid or expired.")
            st = State(state_db)
            try:
                st.unsubscribe(p[0])
            finally:
                st.close()
            self._page(200, f"<p><b>{escape(p[0])}</b> has been unsubscribed. Sorry to see you go.</p>")

        def log_message(self, fmt, *args):  # keep emails out of stderr logs
            pass

    return Handler


def serve(state_db: str, host: str = "127.0.0.1", port: int = 8025) -> None:
    ThreadingHTTPServer((host, port), make_handler(state_db)).serve_forever()
