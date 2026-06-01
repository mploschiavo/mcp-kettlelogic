"""Use cases for insight articles: catalog, search, and full-text retrieval."""

from __future__ import annotations

import asyncio

from mcp_kettlelogic import constants
from mcp_kettlelogic.application.catalog_support import SectionSlugReader
from mcp_kettlelogic.domain.enums import CacheOutcome
from mcp_kettlelogic.domain.errors import EmptyQueryError, FetchError
from mcp_kettlelogic.domain.models import ArticleContent, ArticleSummary, SearchResults
from mcp_kettlelogic.infrastructure import observability
from mcp_kettlelogic.infrastructure.cache import TtlCache
from mcp_kettlelogic.infrastructure.html_parsing import HtmlParser, TextNormalizer
from mcp_kettlelogic.infrastructure.http_client import SiteHttpClient
from mcp_kettlelogic.infrastructure.observability import OperationObserver

_Summaries = tuple[ArticleSummary, ...]


class ArticleService:
    """Reads and searches the site's insight articles."""

    def __init__(
        self,
        http_client: SiteHttpClient,
        parser: HtmlParser,
        normalizer: TextNormalizer,
        slug_reader: SectionSlugReader,
        cache: TtlCache[_Summaries],
        observer: OperationObserver,
        max_articles: int,
        fetch_concurrency: int,
    ) -> None:
        self._http = http_client
        self._parser = parser
        self._normalizer = normalizer
        self._slug_reader = slug_reader
        self._cache = cache
        self._observer = observer
        self._max_articles = max_articles
        self._fetch_concurrency = fetch_concurrency

    async def list_summaries(self) -> _Summaries:
        cached = self._cache.get(constants.CACHE_KEY_ARTICLES)
        if cached is not None:
            self._record_cache(CacheOutcome.HIT)
            return cached
        self._record_cache(CacheOutcome.MISS)
        index = await self._http.get_text(constants.INSIGHTS_INDEX_PATH)
        slugs = self._slug_reader.slugs(index, constants.INSIGHTS_SECTION)[: self._max_articles]
        semaphore = asyncio.Semaphore(self._fetch_concurrency)
        summaries = await asyncio.gather(*(self._summary_for(slug, semaphore) for slug in slugs))
        ordered = tuple(sorted(summaries, key=lambda summary: summary.slug))
        self._cache.set(constants.CACHE_KEY_ARTICLES, ordered)
        return ordered

    async def search(self, query: str, limit: int) -> SearchResults:
        cleaned = query.strip()
        if not cleaned:
            raise EmptyQueryError("query is required")
        bounded = max(constants.MIN_SEARCH_LIMIT, min(limit, constants.MAX_SEARCH_LIMIT))
        needle = cleaned.lower()
        matches = tuple(s for s in await self.list_summaries() if s.matches(needle))
        return SearchResults(query=cleaned, hits=matches[:bounded])

    async def get_content(self, slug: str) -> ArticleContent:
        path = constants.ARTICLE_PATH_TEMPLATE.format(slug=slug)
        document = self._parser.parse_document(await self._http.get_text(path))
        title = self._normalizer.clean_title(document.title) or self._normalizer.slug_to_title(slug)
        summary = ArticleSummary(
            slug=slug, title=title, description=document.description, url=self._http.url(path)
        )
        return ArticleContent(summary=summary, text=document.text)

    async def _summary_for(self, slug: str, semaphore: asyncio.Semaphore) -> ArticleSummary:
        path = constants.ARTICLE_PATH_TEMPLATE.format(slug=slug)
        url = self._http.url(path)
        async with semaphore:
            try:
                html = await self._http.get_text(path)
            except FetchError:
                return ArticleSummary(
                    slug=slug, title=self._normalizer.slug_to_title(slug), description="", url=url
                )
        document = self._parser.parse_document(html)
        title = self._normalizer.clean_title(document.title) or self._normalizer.slug_to_title(slug)
        return ArticleSummary(slug=slug, title=title, description=document.description, url=url)

    def _record_cache(self, outcome: CacheOutcome) -> None:
        self._observer.registry.increment(
            observability.METRIC_CACHE,
            {"result": outcome.value, "key": constants.CACHE_KEY_ARTICLES},
        )
