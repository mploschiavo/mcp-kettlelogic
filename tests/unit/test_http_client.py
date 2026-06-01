"""HTTP client tests — domain-error translation, no real network."""

from __future__ import annotations

import httpx
import pytest

from mcp_kettlelogic.domain.errors import FetchError, NotFoundError
from mcp_kettlelogic.infrastructure.http_client import SiteHttpClient
from mcp_kettlelogic.infrastructure.observability import (
    LoggerFactory,
    MetricsRegistry,
    OperationObserver,
)

BASE = "https://example.test"


def _observer() -> OperationObserver:
    return OperationObserver(LoggerFactory().build("http-test", "WARNING"), MetricsRegistry())


def _client(handler: object) -> SiteHttpClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return SiteHttpClient(BASE, _observer(), httpx.AsyncClient(transport=transport, base_url=BASE))


async def test_get_text_ok() -> None:
    client = _client(lambda request: httpx.Response(200, text="hello"))
    assert await client.get_text("/x") == "hello"
    assert client.url("/insights/") == f"{BASE}/insights/"
    await client.aclose()


async def test_404_raises_not_found() -> None:
    client = _client(lambda request: httpx.Response(404))
    with pytest.raises(NotFoundError):
        await client.get_text("/missing")
    await client.aclose()


async def test_500_raises_fetch_error() -> None:
    client = _client(lambda request: httpx.Response(500))
    with pytest.raises(FetchError):
        await client.get_text("/boom")
    await client.aclose()


async def test_transport_error_raises_fetch_error() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = _client(explode)
    with pytest.raises(FetchError):
        await client.get_text("/x")
    await client.aclose()


def test_create_builds_a_client() -> None:
    client = SiteHttpClient.create(BASE, 5.0, _observer())
    assert client.base_url == BASE
