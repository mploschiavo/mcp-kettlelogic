"""HTML parsing + text normalization tests."""

from __future__ import annotations

from mcp_kettlelogic.infrastructure.html_parsing import HtmlParser, TextNormalizer

_ARTICLE = """
<html><head><title>Retail Omnichannel Revenue — Kettle Logic</title>
<meta name="description" content="Executive strategy."></head>
<body><nav>menu junk</nav><main><h1>Retail</h1>
<p>Omnichannel revenue architecture.</p>
<script>var x = 1 < 2 && 3 > 1;</script></main><footer>footer junk</footer></body></html>
"""

_INDEX = """<html><body>
<a href="/insights/a/">A</a><a href="https://x.test/y">offsite</a>
</body></html>"""


def test_normalizer_clean_title() -> None:
    norm = TextNormalizer()
    assert norm.clean_title("Retail Revenue — Kettle Logic") == "Retail Revenue"
    assert norm.clean_title("Foo | Bar") == "Foo"
    assert norm.clean_title("   ") == ""


def test_normalizer_slug_to_title() -> None:
    assert TextNormalizer().slug_to_title("automotive-aftermarket") == "Automotive Aftermarket"


def test_parse_document_extracts_clean_content() -> None:
    doc = HtmlParser().parse_document(_ARTICLE)
    assert doc.title.strip().startswith("Retail Omnichannel Revenue")
    assert doc.description == "Executive strategy."
    assert "Omnichannel revenue architecture" in doc.text
    assert "var x" not in doc.text       # script removed
    assert "menu junk" not in doc.text   # nav removed
    assert "footer junk" not in doc.text  # footer removed


def test_extract_links_returns_all_anchors() -> None:
    links = HtmlParser().extract_links(_INDEX)
    hrefs = [link.href for link in links]
    assert "/insights/a/" in hrefs
    assert "https://x.test/y" in hrefs
