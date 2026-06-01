"""ArticleService tests."""

from __future__ import annotations

import pytest
from conftest import Stack, build_stack

from mcp_kettlelogic.domain.errors import EmptyQueryError, NotFoundError
from mcp_kettlelogic.infrastructure import observability


async def test_list_summaries_sorted_dedup_and_degraded(stack: Stack) -> None:
    summaries = await stack.articles.list_summaries()
    slugs = [s.slug for s in summaries]
    assert slugs == ["broken-article", "healthcare-playbook", "retail-strategy"]
    by_slug = {s.slug: s for s in summaries}
    assert by_slug["retail-strategy"].title == "Retail Omnichannel Revenue"  # suffix stripped
    assert by_slug["broken-article"].title == "Broken Article"  # degraded slug-title


async def test_list_summaries_caches(stack: Stack) -> None:
    await stack.articles.list_summaries()
    await stack.articles.list_summaries()
    hits = [
        v
        for (name, labels), v in stack.observer.registry.counters().items()
        if name == observability.METRIC_CACHE and ("result", "hit") in labels
    ]
    assert sum(hits) >= 1


async def test_search_matches(stack: Stack) -> None:
    results = await stack.articles.search("retail", limit=5)
    assert results.count == 1
    assert results.hits[0].slug == "retail-strategy"
    assert results.hits[0].resource_uri == "kettlelogic://articles/retail-strategy"


async def test_search_empty_query_raises(stack: Stack) -> None:
    with pytest.raises(EmptyQueryError):
        await stack.articles.search("   ", limit=5)


async def test_search_clamps_limit(stack: Stack) -> None:
    results = await stack.articles.search("a", limit=10_000)
    assert results.count <= 25


async def test_get_content_ok(stack: Stack) -> None:
    content = await stack.articles.get_content("retail-strategy")
    assert content.summary.title == "Retail Omnichannel Revenue"
    assert "Omnichannel revenue architecture" in content.text


async def test_get_content_missing_raises() -> None:
    built = build_stack()
    with pytest.raises(NotFoundError):
        await built.articles.get_content("does-not-exist")
    await built.aclose()
