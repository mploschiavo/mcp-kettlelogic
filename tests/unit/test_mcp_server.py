"""McpContentServer handler tests (the MCP interface layer)."""

from __future__ import annotations

import json

import pytest
from conftest import Stack

from mcp_kettlelogic.domain.errors import UnknownIndustryError
from mcp_kettlelogic.infrastructure import observability


async def test_articles_manifest_handler(stack: Stack) -> None:
    payload = json.loads(await stack.mcp_server.articles_manifest())
    assert payload["count"] == 3


async def test_industries_list_handler(stack: Stack) -> None:
    payload = json.loads(await stack.mcp_server.industries_list())
    assert payload["count"] == 2


async def test_article_resource_handler(stack: Stack) -> None:
    text = await stack.mcp_server.article_resource("retail-strategy")
    assert text.startswith("# Retail Omnichannel Revenue")


async def test_list_articles_tool(stack: Stack) -> None:
    payload = json.loads(await stack.mcp_server.list_articles())
    assert payload["count"] == 3


async def test_list_industries_tool(stack: Stack) -> None:
    payload = json.loads(await stack.mcp_server.list_industries())
    assert payload["count"] == 2


async def test_get_article_tool(stack: Stack) -> None:
    text = await stack.mcp_server.get_article("retail-strategy")
    assert text.startswith("# Retail Omnichannel Revenue")


async def test_search_tool(stack: Stack) -> None:
    payload = json.loads(await stack.mcp_server.search_articles("healthcare"))
    assert payload["results"][0]["slug"] == "healthcare-playbook"


async def test_industry_overview_tool(stack: Stack) -> None:
    payload = json.loads(await stack.mcp_server.get_industry_overview("retail"))
    assert "Unify inventory" in payload["overview"]


async def test_handler_error_is_observed(stack: Stack) -> None:
    with pytest.raises(UnknownIndustryError):
        await stack.mcp_server.get_industry_overview("atlantis")
    errored = [
        v
        for (name, labels), v in stack.observer.registry.counters().items()
        if name == observability.METRIC_ERRORS and ("op", "get_industry_overview") in labels
    ]
    assert sum(errored) >= 1


def test_fastmcp_exposed(stack: Stack) -> None:
    assert stack.mcp_server.fastmcp is not None
