"""ContentSerializer tests."""

from __future__ import annotations

import json

from mcp_kettlelogic.domain.models import (
    ArticleContent,
    ArticleSummary,
    Industry,
    IndustryOverview,
    SearchResults,
)
from mcp_kettlelogic.interfaces.serializer import ContentSerializer

_SER = ContentSerializer()
_SUMMARY = ArticleSummary(
    slug="retail", title="Retail", description="desc", url="https://x/retail/"
)


def test_articles_manifest() -> None:
    payload = json.loads(_SER.articles_manifest([_SUMMARY]))
    assert payload["count"] == 1
    assert payload["items"][0]["slug"] == "retail"


def test_industries_list() -> None:
    payload = json.loads(_SER.industries_list([Industry("retail", "Retail", "https://x/")]))
    assert payload["items"][0]["title"] == "Retail"


def test_search_results() -> None:
    payload = json.loads(_SER.search_results(SearchResults(query="r", hits=(_SUMMARY,))))
    assert payload["query"] == "r"
    assert payload["results"][0]["resource_uri"] == "kettlelogic://articles/retail"


def test_industry_overview() -> None:
    overview = IndustryOverview(slug="retail", title="Retail", url="https://x/", overview="text")
    payload = json.loads(_SER.industry_overview(overview))
    assert payload["industry"] == "retail"
    assert payload["overview"] == "text"


def test_article_text() -> None:
    text = _SER.article_text(ArticleContent(summary=_SUMMARY, text="body here"))
    assert text.startswith("# Retail")
    assert "body here" in text
