from newsbrief.extract import extract_text


def test_extracts_article_body_only(fixture_bytes):
    text = extract_text(fixture_bytes("article.html").decode())
    paras = text.split("\n\n")
    assert len(paras) == 3
    assert paras[0].startswith("The central bank raised")
    assert "largest move" in paras[0]
    assert "stubbornly high" in paras[1]
    for junk in ("header", "caption", "Copyright", "Related", "not text", "Short."):
        assert junk not in text


def test_falls_back_to_meta_description():
    html = '<html><head><meta name="description" content="Just a blurb"></head><body><p>hi</p></body></html>'
    assert extract_text(html) == "Just a blurb"


def test_malformed_html_does_not_raise():
    assert isinstance(extract_text("<p><div></span></p></p><a>" * 50), str)
