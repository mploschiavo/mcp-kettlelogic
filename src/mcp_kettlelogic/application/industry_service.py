"""Use cases for industry pages: catalog discovery and overview extraction."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from mcp_kettlelogic import constants
from mcp_kettlelogic.application.catalog_support import SectionSlugReader
from mcp_kettlelogic.domain.enums import CacheOutcome
from mcp_kettlelogic.domain.errors import FetchError, NotFoundError, UnknownIndustryError
from mcp_kettlelogic.domain.models import Industry, IndustryOverview
from mcp_kettlelogic.infrastructure import observability
from mcp_kettlelogic.infrastructure.cache import TtlCache
from mcp_kettlelogic.infrastructure.html_parsing import HtmlParser, TextNormalizer
from mcp_kettlelogic.infrastructure.http_client import SiteHttpClient
from mcp_kettlelogic.infrastructure.observability import OperationObserver

_Industries = tuple[Industry, ...]


class IndustryService:
    """Discovers industry pages and extracts plain-text overviews."""

    def __init__(
        self,
        http_client: SiteHttpClient,
        parser: HtmlParser,
        normalizer: TextNormalizer,
        slug_reader: SectionSlugReader,
        cache: TtlCache[_Industries],
        observer: OperationObserver,
        overview_max_chars: int,
    ) -> None:
        self._http = http_client
        self._parser = parser
        self._normalizer = normalizer
        self._slug_reader = slug_reader
        self._cache = cache
        self._observer = observer
        self._overview_max_chars = overview_max_chars
        self._industry_path = re.compile(rf"/{constants.INDUSTRIES_SECTION}/([^/?#]+)/?$")
        self._llms_link = re.compile(constants.LLMS_LINK_PATTERN, re.MULTILINE)

    async def list_industries(self) -> _Industries:
        cached = self._cache.get(constants.CACHE_KEY_INDUSTRIES)
        if cached is not None:
            self._record_cache(CacheOutcome.HIT)
            return cached
        self._record_cache(CacheOutcome.MISS)
        discovered = await self._discover()
        ordered = tuple(sorted(discovered, key=lambda industry: industry.slug))
        self._cache.set(constants.CACHE_KEY_INDUSTRIES, ordered)
        return ordered

    async def get_overview(self, industry: str) -> IndustryOverview:
        slug = industry.strip().lower()
        if not slug:
            raise UnknownIndustryError("industry is required")
        path = constants.INDUSTRY_PATH_TEMPLATE.format(slug=slug)
        try:
            html = await self._http.get_text(path)
        except NotFoundError as exc:
            raise UnknownIndustryError(f"Unknown industry: {slug}") from exc
        document = self._parser.parse_document(html)
        title = self._normalizer.clean_title(document.title) or self._normalizer.slug_to_title(slug)
        return IndustryOverview(
            slug=slug,
            title=title,
            url=self._http.url(path),
            overview=document.text[: self._overview_max_chars].rstrip(),
        )

    async def _discover(self) -> list[Industry]:
        from_llms = self._parse_llms(await self._safe_llms())
        if from_llms:
            return from_llms
        index = await self._http.get_text(constants.INDUSTRIES_INDEX_PATH)
        return [
            Industry(
                slug=slug,
                title=self._normalizer.slug_to_title(slug),
                url=self._http.url(constants.INDUSTRY_PATH_TEMPLATE.format(slug=slug)),
            )
            for slug in self._slug_reader.slugs(index, constants.INDUSTRIES_SECTION)
        ]

    async def _safe_llms(self) -> str | None:
        try:
            return await self._http.get_text(constants.LLMS_TXT_PATH)
        except FetchError:
            return None

    def _parse_llms(self, text: str | None) -> list[Industry]:
        if text is None:
            return []
        seen: set[str] = set()
        industries: list[Industry] = []
        for title, url in self._llms_link.findall(text):
            match = self._industry_path.search(urlparse(url).path)
            if match is None:
                continue
            slug = match.group(1)
            if slug not in seen:
                seen.add(slug)
                industries.append(Industry(slug=slug, title=title.strip(), url=url.strip()))
        return industries

    def _record_cache(self, outcome: CacheOutcome) -> None:
        self._observer.registry.increment(
            observability.METRIC_CACHE,
            {"result": outcome.value, "key": constants.CACHE_KEY_INDUSTRIES},
        )
