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


class FakeMessages:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.parsed, self.stop_reason, self.calls = parsed, stop_reason, []

    def parse(self, **kw):
        self.calls.append(kw)
        out_cls = kw["output_format"]
        parsed = out_cls.model_validate(self.parsed) if self.parsed else None
        return type("R", (), {"stop_reason": self.stop_reason, "parsed_output": parsed})()


class FakeClient:
    def __init__(self, *a, **k):
        self.messages = FakeMessages(*a, **k)


def two_story_brief():
    return Brief(
        "me@x.com",
        [
            Story([Article("Rates up", "u1", "wire", text=BODY)], topic="world"),
            Story([Article("Chip news", "u2", "hn", summary="A chip was released today by a company.")], topic="tech"),
        ],
    )


def test_claude_summaries_applied_and_request_shape():
    from newsbrief.summarize import MODEL, summarize_claude

    client = FakeClient(
        {"intro": "Rates and chips.", "stories": [{"id": 0, "headline": "H0", "summary": "S0", "why_it_matters": "W0"}]}
    )
    b = summarize_claude(two_story_brief(), client=client)
    assert b.intro == "Rates and chips." and b.summarizer == MODEL
    assert (b.stories[0].headline, b.stories[0].summary, b.stories[0].why_it_matters) == ("H0", "S0", "W0")
    assert b.stories[1].headline == "Chip news" and b.stories[1].summary  # extractive for uncovered story
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5-5" and "thinking" not in call
    assert call["output_config"] == {"effort": "medium"}
    assert '<cluster id="1" topic="tech">' in call["messages"][0]["content"]


def test_claude_refusal_keeps_extractive():
    from newsbrief.summarize import summarize_claude

    b = summarize_claude(two_story_brief(), client=FakeClient(None, stop_reason="refusal"))
    assert b.summarizer == "extractive" and b.stories[0].headline == "Rates up"


def test_summarize_falls_back_without_key(monkeypatch):
    from newsbrief.summarize import summarize

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert summarize(two_story_brief()).summarizer == "extractive"


def test_extractive_prefers_feed_blurb_over_page_text():
    blurb = "Trump hosted Xi Jinping at a White House state dinner, praising US-China ties while trade disputes remain."
    s = Story([Article("Trump hosts Xi at state dinner", "u", "bbc", summary=blurb,
                       text="Defence Secretary Pete Hegseth was at another table, looking serious. " * 3)])
    assert extractive_summary(s) == blurb


def test_extractive_uses_lead_blurb_not_longest():
    lead = Article("Pope heads to France", "u1", "aljazeera",
                   summary="Pope Leo XIV is heading to France for the first official papal visit in 18 years.")
    other = Article("Pope in France – live", "u2", "guardian",
                    summary="The pope will speak on AI Pope Leo gets off the plane , gets into a chat " * 4)
    assert extractive_summary(Story([lead, other])) == lead.summary


def test_extractive_why_it_matters_for_top_story_only():
    text = BODY + " The move could push mortgage costs to their highest level since 2008. Analysts cheered."
    b = Brief("me@x.com", [Story([Article("Central bank raises interest rate", "u1", "wire", text=text)], topic="world"),
                           Story([Article("Chip news", "u2", "hn", text=text)], topic="tech")])
    summarize_extractive(b)
    top, second = b.stories
    assert top.why_it_matters == "The move could push mortgage costs to their highest level since 2008."
    assert top.why_it_matters not in top.summary and second.why_it_matters == ""


def test_extractive_why_prefers_nothing_to_a_weak_guess():
    from newsbrief.summarize import extractive_why

    s = Story([Article("Club signs striker", "u", "s", summary="The club signed a striker on Tuesday afternoon.")])
    s.summary = extractive_summary(s)
    assert extractive_why(s) == ""


def test_claude_why_it_matters_is_top_story_only_with_extractive_fallback():
    from newsbrief.summarize import SYSTEM, summarize_claude

    assert "cluster 0 only" in SYSTEM
    text = BODY + " The move could push mortgage costs to their highest level since 2008."
    stories = [{"id": 0, "headline": "H0", "summary": "S0", "why_it_matters": ""},
               {"id": 1, "headline": "H1", "summary": "S1", "why_it_matters": "ignored"}]
    b = two_story_brief()
    b.stories[0].articles[0].text = text
    summarize_claude(b, client=FakeClient({"intro": "i", "stories": stories}))
    assert b.stories[0].why_it_matters.startswith("The move could push mortgage costs")  # extractive fallback
    assert b.stories[1].why_it_matters == ""
