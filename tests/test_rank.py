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


def test_diversify_caps_topics_but_fills_slots():
    from newsbrief.rank import diversify

    stories = [Story([art()], rank=10 - i, topic=t) for i, t in enumerate(["w", "w", "w", "t", "w", "b"])]
    assert [s.topic for s in diversify(stories, 4, per_topic=2)] == ["w", "w", "t", "b"]
    # not enough other topics: overflow fills remaining slots in rank order
    assert [s.rank for s in diversify(stories, 6, per_topic=2)] == [10, 9, 8, 7, 6, 5]


def test_personalize_weights_boosts_and_mutes():
    from newsbrief.config import Subscriber
    from newsbrief.rank import personalize

    def story(title, topic, rank):
        return Story([Article(title, f"https://x/{title}", "s", summary=f"About {title}.")], rank=rank, topic=topic)

    stories = [story("Election results", "world", 3.0), story("New GPU launch", "tech", 2.0),
               story("Rust 2.0 released", "tech", 1.0), story("Celebrity gossip roundup", "world", 2.5)]
    sub = Subscriber("me@x.com", topic_weights={"tech": 1.2, "world": 0.5}, boost=["rust"], mute=["celebrity"])
    out = personalize(stories, sub)
    assert [s.lead.title for s in out] == ["New GPU launch", "Rust 2.0 released", "Election results"]
    assert [round(s.rank, 2) for s in out] == [2.4, 1.8, 1.5]
    # whole words only: "rust" must not boost "trust"
    assert personalize([story("Voters trust polls", "world", 1.0)], Subscriber("a@b.c", boost=["rust"]))[0].rank == 1.0
    # a zero weight hides a topic entirely
    assert personalize(stories[:2], Subscriber("a@b.c", topic_weights={"tech": 0}))[0].lead.title == "Election results"
    assert len(personalize(stories[:2], Subscriber("a@b.c", topic_weights={"tech": 0}))) == 1


def test_blank_and_symbol_terms():
    from newsbrief.config import Subscriber
    from newsbrief.rank import personalize

    def story(title, topic, rank):
        return Story([Article(title, f"https://x/{title}", "s")], rank=rank, topic=topic)

    s = [story("New C++ standard approved", "tech", 1.0), story("Rates rise", "world", 1.0)]
    assert len(personalize(s, Subscriber("a@b.c", mute=["", "  "]))) == 2  # blank mutes nothing
    assert [x.lead.title for x in personalize(s, Subscriber("a@b.c", mute=["c++"]))] == ["Rates rise"]
    assert personalize(s, Subscriber("a@b.c", boost=["C++"]))[0].rank == 1.5
