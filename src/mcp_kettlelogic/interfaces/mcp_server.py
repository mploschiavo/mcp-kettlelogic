"""MCP interface layer: binds the application services to FastMCP tools and
resources. Every handler is a method (no module-level functions) wrapped in an
observability scope.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_kettlelogic import constants
from mcp_kettlelogic.application.article_service import ArticleService
from mcp_kettlelogic.application.industry_service import IndustryService
from mcp_kettlelogic.config import ServerConfig
from mcp_kettlelogic.infrastructure.observability import OperationObserver
from mcp_kettlelogic.interfaces.serializer import ContentSerializer


class McpContentServer:
    """Exposes article/industry content as MCP tools and resources."""

    def __init__(
        self,
        config: ServerConfig,
        articles: ArticleService,
        industries: IndustryService,
        serializer: ContentSerializer,
        observer: OperationObserver,
    ) -> None:
        self._config = config
        self._articles = articles
        self._industries = industries
        self._serializer = serializer
        self._observer = observer
        self._mcp = FastMCP(constants.SERVER_NAME, host=config.http_host, port=config.http_port)
        self._register()

    @property
    def fastmcp(self) -> FastMCP:
        return self._mcp

    def run(self) -> None:
        self._mcp.run(transport=self._config.transport.value)

    def _register(self) -> None:
        self._mcp.tool(name=constants.TOOL_SEARCH_ARTICLES)(self.search_articles)
        self._mcp.tool(name=constants.TOOL_GET_INDUSTRY_OVERVIEW)(self.get_industry_overview)
        self._mcp.resource(constants.ARTICLES_MANIFEST_URI)(self.articles_manifest)
        self._mcp.resource(constants.INDUSTRIES_LIST_URI)(self.industries_list)
        self._mcp.resource(constants.ARTICLE_RESOURCE_URI_TEMPLATE)(self.article_resource)

    async def search_articles(self, query: str, limit: int = constants.DEFAULT_SEARCH_LIMIT) -> str:
        """Search Kettle Logic insight articles by title, slug or description."""
        async with self._observer.observe(constants.TOOL_SEARCH_ARTICLES):
            return self._serializer.search_results(await self._articles.search(query, limit))

    async def get_industry_overview(self, industry: str) -> str:
        """Return a plain-text overview for an industry page (slug, e.g. "retail")."""
        async with self._observer.observe(constants.TOOL_GET_INDUSTRY_OVERVIEW):
            return self._serializer.industry_overview(
                await self._industries.get_overview(industry)
            )

    async def articles_manifest(self) -> str:
        """JSON catalog of every insight article on the configured site."""
        async with self._observer.observe("articles_manifest"):
            return self._serializer.articles_manifest(await self._articles.list_summaries())

    async def industries_list(self) -> str:
        """JSON list of industry pages discovered on the configured site."""
        async with self._observer.observe("industries_list"):
            return self._serializer.industries_list(await self._industries.list_industries())

    async def article_resource(self, slug: str) -> str:
        """A single insight article rendered as readable text."""
        async with self._observer.observe("article_resource"):
            return self._serializer.article_text(await self._articles.get_content(slug))
