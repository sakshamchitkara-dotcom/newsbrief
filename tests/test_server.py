import threading
import urllib.error
import urllib.request as ur
from http.server import ThreadingHTTPServer

import pytest

from newsbrief.server import make_handler
from newsbrief.state import State
from newsbrief.unsubscribe import unsubscribe_url


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.undo()  # this test talks to localhost only; re-enable urlopen
    db = str(tmp_path / "s.db")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(db))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", db
    srv.shutdown()


def test_one_click_unsubscribe(server):
    base, db = server
    url = unsubscribe_url(base, "me@x.com")
    assert b"Stop sending" in ur.urlopen(url).read()
    assert not State(db).is_unsubscribed("me@x.com")  # GET alone must not unsubscribe (link scanners)
    body = ur.urlopen(ur.Request(url, data=b"List-Unsubscribe=One-Click", method="POST")).read()
    assert b"has been unsubscribed" in body and State(db).is_unsubscribed("me@x.com")


def test_bad_token_rejected(server):
    base, db = server
    with pytest.raises(urllib.error.HTTPError) as e:
        ur.urlopen(ur.Request(f"{base}/unsubscribe?email=me@x.com&token=nope", data=b"", method="POST"))
    assert e.value.code == 400 and not State(db).is_unsubscribed("me@x.com")
