from datetime import datetime, timedelta, timezone

from newsbrief.config import Source
from newsbrief.models import Article, Story
from newsbrief.rank import rank, within

NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
SRC = {"a": Source("a", "rss", url="x", topics=["world"]), "b": Source("b", "rss", url="x", topics=["world", "biz"])}


def art(src="a", hours=1, weight=1.0, score=0):
    return Article("t", f"https://{src}.com/{hours}", src, published=NOW - timedelta(hours=hours), weight=weight, score=score)


def test_recency_wins_when_all_else_equal():
    old, new = Story([art(hours=30)]), Story([art(hours=1)])
    assert rank([old, new], SRC, NOW) == [new, old]


def test_cross_source_coverage_beats_single_outlet():
    single = Story([art("a", hours=2)])
    multi = Story([art("a", hours=4), art("b", hours=4)])
    assert rank([single, multi], SRC, NOW)[0] is multi


def test_source_weight_and_popularity():
    assert rank([Story([art(weight=1)]), s := Story([art(weight=2)])], SRC, NOW)[0] is s
    assert rank([Story([art()]), s := Story([art(score=900)])], SRC, NOW)[0] is s


def test_topic_assignment_and_window():
    s = rank([Story([art("a"), art("b")])], SRC, NOW)[0]
    assert s.topic == "world"
    assert within(Story([art(hours=10)]), NOW, 36)
    assert not within(Story([art(hours=50)]), NOW, 36)
