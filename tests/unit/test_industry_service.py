"""IndustryService tests."""

from __future__ import annotations

import httpx
import pytest
from conftest import Stack, build_stack, default_handler

from mcp_kettlelogic.domain.errors import UnknownIndustryError


async def test_list_industries_from_llms(stack: Stack) -> None:
    industries = await stack.industries.list_industries()
    slugs = [i.slug for i in industries]
    assert slugs == ["healthcare", "retail"]
    assert {i.slug: i.title for i in industries}["retail"] == "Retail"


async def test_list_industries_falls_back_to_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/llms.txt":
            return httpx.Response(404)
        return default_handler(request)

    built = build_stack(handler)
    industries = await built.industries.list_industries()
    assert [i.slug for i in industries] == ["energy", "retail"]
    await built.aclose()


async def test_overview_ok(stack: Stack) -> None:
    overview = await stack.industries.get_overview("retail")
    assert "Unify inventory" in overview.overview
    assert overview.title == "Retail"
    assert overview.url.endswith("/industries/retail/")


async def test_overview_unknown_raises(stack: Stack) -> None:
    with pytest.raises(UnknownIndustryError):
        await stack.industries.get_overview("atlantis")


async def test_overview_empty_raises(stack: Stack) -> None:
    with pytest.raises(UnknownIndustryError):
        await stack.industries.get_overview("   ")


async def test_industries_cached(stack: Stack) -> None:
    first = await stack.industries.list_industries()
    second = await stack.industries.list_industries()
    assert first == second
