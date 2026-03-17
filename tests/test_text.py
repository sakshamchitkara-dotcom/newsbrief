from newsbrief.text import clean, sentences, strip_html, truncate


def test_clean_removes_invisible_characters():
    # observed in a live Guardian feed: "The \u2060Saudi-led coalition ... \u200bArabia"
    assert clean("The \u2060Saudi-led  coalition\n in western Saudi \u200bArabia") == "The Saudi-led coalition in western Saudi Arabia"


def test_strip_html_skips_scripts_and_unescapes():
    assert strip_html("<p>A &amp; B</p><script>x()</script><style>p{}</style> C") == "A & B C"
    assert strip_html("Tom &amp; Jerry") == "Tom & Jerry"


def test_sentences_and_truncate():
    assert sentences('He said "yes." Then left. 3 more followed.') == ['He said "yes."', "Then left.", "3 more followed."]
    assert truncate("one two three four", 9) == "one two…"
    assert truncate("short", 9) == "short"
