from newsbrief.models import Article, Brief, Story
from newsbrief.summarize import extractive_summary, summarize_extractive

BODY = (
    "The central bank raised its benchmark interest rate by half a point on Tuesday. "
    "The weather in the capital was mild and sunny for most of the afternoon. "
    "Officials said the rate increase was needed because inflation remains high. "
    "A local football club also announced a new stadium sponsor this week."
)


def test_extractive_picks_on_topic_sentences():
    s = Story([Article("Central bank raises interest rate as inflation stays high", "u", "s", text=BODY)])
    out = extractive_summary(s)
    assert "benchmark interest rate" in out and "inflation remains high" in out
    assert "football" not in out and "weather" not in out


def test_extractive_handles_empty_and_short_bodies():
    assert extractive_summary(Story([Article("Title", "u", "s")])) == ""
    assert extractive_summary(Story([Article("Title", "u", "s", summary="Tiny blurb")])) == "Tiny blurb"


def test_summarize_extractive_fills_brief():
    b = Brief("me@x.com", [Story([Article("Rates up", "u", "s", text=BODY)], topic="world")])
    summarize_extractive(b)
    assert b.stories[0].headline == "Rates up" and b.stories[0].summary
    assert b.intro == "1 story today across world." and b.summarizer == "extractive"
