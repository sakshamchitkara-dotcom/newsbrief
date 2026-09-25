from newsbrief.scrape import headline_links

HTML = """
<a href="/">Home</a>
<a href="/world/2026/09/rates-rise">Central bank raises rates to fight inflation</a>
<a href="/world/2026/09/rates-rise#comments">Central bank raises rates to fight inflation</a>
<a href="https://other.example.com/x">Offsite link with a long headline text here</a>
<a href="/tech/chips"><span>New chip</span> <b>doubles battery life in phones</b></a>
<a href="/subscribe">Subscribe now</a>
"""


def test_headline_links_filters_and_resolves():
    links = headline_links(HTML, "https://news.example.com/section")
    assert links == [
        ("https://news.example.com/world/2026/09/rates-rise", "Central bank raises rates to fight inflation"),
        ("https://news.example.com/tech/chips", "New chip doubles battery life in phones"),
    ]
