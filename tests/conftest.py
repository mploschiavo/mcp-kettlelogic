"""Shared test fixtures: a fake Kettle Logic-shaped site served via
``httpx.MockTransport`` and a builder that wires the full stack against it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pytest

from mcp_kettlelogic.application.article_service import ArticleService
from mcp_kettlelogic.application.catalog_support import SectionSlugReader
from mcp_kettlelogic.application.industry_service import IndustryService
from mcp_kettlelogic.config import ConfigLoader
from mcp_kettlelogic.domain.models import ArticleSummary, Industry
from mcp_kettlelogic.infrastructure.cache import TtlCache
from mcp_kettlelogic.infrastructure.html_parsing import HtmlParser, TextNormalizer
from mcp_kettlelogic.infrastructure.http_client import SiteHttpClient
from mcp_kettlelogic.infrastructure.observability import (
    LoggerFactory,
    MetricsRegistry,
    OperationObserver,
)
from mcp_kettlelogic.interfaces.mcp_server import McpContentServer
from mcp_kettlelogic.interfaces.serializer import ContentSerializer

BASE_URL = "https://example.test"

_CACHE_TTL = 600.0
_MAX_ARTICLES = 200
_FETCH_CONCURRENCY = 8
_OVERVIEW_MAX_CHARS = 1500

Handler = Callable[[httpx.Request], httpx.Response]

INSIGHTS_INDEX = """
<html><body><nav><a href="/">Home</a></nav><main>
  <a href="/insights/retail-strategy/">Retail Strategy</a>
  <a href="/insights/healthcare-playbook/">Healthcare Playbook</a>
  <a href="/insights/broken-article/">Broken Article</a>
  <a href="/insights/retail-strategy/">Retail Strategy (dup)</a>
  <a href="https://twitter.com/x">offsite</a>
  <a href="/about/">About</a>
</main></body></html>
"""

ARTICLES = {
    "retail-strategy": """
<html><head><title>Retail Omnichannel Revenue — Kettle Logic</title>
<meta name="description" content="Executive strategy on retail revenue."></head>
<body><nav>menu junk</nav><main><h1>Retail</h1>
<p>Omnichannel revenue architecture for modern retail.</p>
<script>var x = 1 < 2 && 3 > 1;</script></main><footer>footer junk</footer></body></html>
""",
    "healthcare-playbook": """
<html><head><title>Healthcare Ops Playbook — Kettle Logic</title>
<meta name="description" content="Healthcare operations playbook."></head>
<body><main><p>Care pathways and throughput.</p></main></body></html>
""",
}

LLMS_TXT = """# Kettle Logic
## Key pages
- Home: https://example.test/
- Retail: https://example.test/industries/retail/
- Healthcare: https://example.test/industries/healthcare/
- Legal: https://example.test/legal/
"""

INDUSTRIES_INDEX = """
<html><body><main>
  <a href="/industries/retail/">Retail</a>
  <a href="/industries/energy/">Energy</a>
</main></body></html>
"""

INDUSTRY_RETAIL = """
<html><head><title>Retail — Kettle Logic</title></head>
<body><nav>nav</nav><main><h2>Retail</h2>
<p>Unify inventory, pricing, and fulfillment across channels.</p>
</main><footer>f</footer></body></html>
"""


def default_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    routes = {
        "/insights/": INSIGHTS_INDEX,
        "/llms.txt": LLMS_TXT,
        "/industries/": INDUSTRIES_INDEX,
        "/industries/retail/": INDUSTRY_RETAIL,
    }
    if path in routes:
        return httpx.Response(200, text=routes[path])
    if path == "/insights/broken-article/":
        return httpx.Response(500, text="boom")
    if path.startswith("/insights/"):
        slug = path.strip("/").split("/")[-1]
        if slug in ARTICLES:
            return httpx.Response(200, text=ARTICLES[slug])
    return httpx.Response(404, text="not found")


@dataclass
class Stack:
    observer: OperationObserver
    http_client: SiteHttpClient
    articles: ArticleService
    industries: IndustryService
    serializer: ContentSerializer
    mcp_server: McpContentServer

    async def aclose(self) -> None:
        await self.http_client.aclose()


def build_stack(handler: Handler = default_handler, base_url: str = BASE_URL) -> Stack:
    observer = OperationObserver(LoggerFactory().build("test", "WARNING"), MetricsRegistry())
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=base_url)
    http_client = SiteHttpClient(base_url=base_url, observer=observer, client=client)
    parser = HtmlParser()
    normalizer = TextNormalizer()
    slug_reader = SectionSlugReader(parser)
    article_cache: TtlCache[tuple[ArticleSummary, ...]] = TtlCache(_CACHE_TTL)
    industry_cache: TtlCache[tuple[Industry, ...]] = TtlCache(_CACHE_TTL)
    articles = ArticleService(
        http_client=http_client,
        parser=parser,
        normalizer=normalizer,
        slug_reader=slug_reader,
        cache=article_cache,
        observer=observer,
        max_articles=_MAX_ARTICLES,
        fetch_concurrency=_FETCH_CONCURRENCY,
    )
    industries = IndustryService(
        http_client=http_client,
        parser=parser,
        normalizer=normalizer,
        slug_reader=slug_reader,
        cache=industry_cache,
        observer=observer,
        overview_max_chars=_OVERVIEW_MAX_CHARS,
    )
    serializer = ContentSerializer()
    config = ConfigLoader({"KETTLELOGIC_BASE_URL": base_url}).load()
    mcp_server = McpContentServer(config, articles, industries, serializer, observer)
    return Stack(observer, http_client, articles, industries, serializer, mcp_server)


@pytest.fixture
async def stack() -> Stack:
    built = build_stack()
    yield built
    await built.aclose()
