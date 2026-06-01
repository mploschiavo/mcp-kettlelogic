"""The HTTP client layer.

All outbound network access lives here (enforced by a ratchet); higher layers
receive parsed text, never a socket. The ``httpx.AsyncClient`` is injectable so
tests drive a mock transport with no network.
"""

from __future__ import annotations

import time
from urllib.parse import urljoin

import httpx

from mcp_kettlelogic import constants
from mcp_kettlelogic.domain.errors import FetchError, NotFoundError
from mcp_kettlelogic.infrastructure import observability
from mcp_kettlelogic.infrastructure.observability import OperationObserver


class SiteHttpClient:
    """Read-only HTTP reader for a Kettle Logic-shaped site."""

    def __init__(
        self, base_url: str, observer: OperationObserver, client: httpx.AsyncClient
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._observer = observer
        self._client = client

    @classmethod
    def create(
        cls, base_url: str, timeout_seconds: float, observer: OperationObserver
    ) -> SiteHttpClient:
        client = httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"user-agent": constants.USER_AGENT},
        )
        return cls(base_url=base_url, observer=observer, client=client)

    @property
    def base_url(self) -> str:
        return self._base_url

    def url(self, path: str) -> str:
        return urljoin(self._base_url + "/", path.lstrip("/"))

    async def get_text(self, path: str) -> str:
        url = self.url(path)
        self._observer.registry.increment(observability.METRIC_HTTP_FETCHES)
        started = time.monotonic()
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._record_error(url, exc)
            if exc.response.status_code == constants.HTTP_NOT_FOUND:
                raise NotFoundError(url) from exc
            raise FetchError(url) from exc
        except httpx.HTTPError as exc:
            self._record_error(url, exc)
            raise FetchError(url) from exc
        self._observer.registry.observe_latency(
            constants.HTTP_FETCH_OPERATION, time.monotonic() - started
        )
        self._observer.logger.debug("fetch.ok url=%s bytes=%d", url, len(response.text))
        return response.text

    def _record_error(self, url: str, exc: httpx.HTTPError) -> None:
        self._observer.registry.increment(
            observability.METRIC_HTTP_ERRORS, {"error": type(exc).__name__}
        )
        self._observer.logger.warning("fetch.error url=%s error=%s", url, type(exc).__name__)

    async def aclose(self) -> None:
        await self._client.aclose()
