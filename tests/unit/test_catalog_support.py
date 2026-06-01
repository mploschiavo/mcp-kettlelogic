"""SectionSlugReader tests."""

from __future__ import annotations

from mcp_kettlelogic.application.catalog_support import SectionSlugReader
from mcp_kettlelogic.infrastructure.html_parsing import HtmlParser

_HTML = """<html><body>
<a href="/insights/a/">A</a>
<a href="/insights/b/">B</a>
<a href="/insights/a/">A dup</a>
<a href="https://other.test/insights/c/">offsite</a>
<a href="/about/">about</a>
</body></html>"""


def test_slugs_dedupes_and_filters_section() -> None:
    reader = SectionSlugReader(HtmlParser())
    assert reader.slugs(_HTML, "insights") == ["a", "b"]


def test_slugs_empty_for_absent_section() -> None:
    reader = SectionSlugReader(HtmlParser())
    assert reader.slugs(_HTML, "industries") == []
