import json

import pytest

from newsbrief.config import ConfigError, load_config, parse_config

BASE = {"sources": {"a": {"url": "https://a/rss", "topics": ["world"]}, "hn": {"type": "hackernews", "topics": ["tech"]}}}


def cfg(**subs):
    return parse_config({**BASE, "subscribers": [{"email": "x@y.z", **subs}]})


def test_defaults_and_source_selection():
    c = cfg()
    assert c.sources["a"].type == "rss" and c.max_stories == 12
    assert [s.name for s in c.sources_for(c.subscribers[0])] == ["a", "hn"]
    c = cfg(topics=["tech"])
    assert [s.name for s in c.sources_for(c.subscribers[0])] == ["hn"]
    c = cfg(sources=["a"])
    assert [s.name for s in c.sources_for(c.subscribers[0])] == ["a"]


@pytest.mark.parametrize(
    "bad,msg",
    [
        ({"timezone": "Mars/Base"}, "timezone"),
        ({"send_at": "25:00"}, "HH:MM"),
        ({"sources": ["nope"]}, "unknown sources"),
        ({"email": "not-an-email"}, "invalid subscriber"),
        ({"topic_weights": {"tech": -1}}, "topic_weights"),
        ({"topic_weights": {"tech": "lots"}}, "topic_weights"),
        ({"topic_weights": 3}, "topic_weights"),
        ({"topics": ["tehc"]}, "unknown topics"),
        ({"topic_weights": {"sport": 2}}, "unknown topics"),
        ({"favourite_colour": "red"}, "unexpected keyword"),
    ],
)
def test_invalid_subscribers(bad, msg):
    with pytest.raises(ConfigError, match=msg):
        cfg(**bad)


def test_source_validation():
    with pytest.raises(ConfigError, match="url is required"):
        parse_config({"sources": {"a": {"type": "rss"}}})
    with pytest.raises(ConfigError, match="at least one source"):
        parse_config({"sources": {}})


def test_json_and_yaml_loading(tmp_path):
    j = tmp_path / "c.json"
    j.write_text(json.dumps({**BASE, "subscribers": []}))
    assert set(load_config(j).sources) == {"a", "hn"}
    y = tmp_path / "c.yaml"
    y.write_text("sources:\n  a: {url: 'https://a/rss'}\nmax_stories: 5\n")
    assert load_config(y).max_stories == 5


def test_duplicate_subscribers_rejected():
    with pytest.raises(ConfigError, match="duplicate subscriber"):
        parse_config({**BASE, "subscribers": [{"email": "a@b.c"}, {"email": "A@b.c"}]})
