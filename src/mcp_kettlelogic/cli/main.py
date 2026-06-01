"""Composition root + entry point.

``ServerApplication`` wires every layer together from a :class:`ServerConfig`.
The console script targets ``ServerApplication.run_from_env`` (a classmethod), so
there are no module-level functions.
"""

from __future__ import annotations

from mcp_kettlelogic import constants
from mcp_kettlelogic.application.article_service import ArticleService
from mcp_kettlelogic.application.catalog_support import SectionSlugReader
from mcp_kettlelogic.application.industry_service import IndustryService
from mcp_kettlelogic.config import ConfigLoader, ServerConfig
from mcp_kettlelogic.domain.models import ArticleSummary, Industry
from mcp_kettlelogic.infrastructure.cache import TtlCache
from mcp_kettlelogic.infrastructure.html_parsing import HtmlParser, TextNormalizer
from mcp_kettlelogic.infrastructure.http_client import SiteHttpClient
from mcp_kettlelogic.infrastructure.observability import (
    LoggerFactory,
    MetricsHttpServer,
    MetricsRegistry,
    OperationObserver,
    PrometheusRenderer,
)
from mcp_kettlelogic.interfaces.mcp_server import McpContentServer
from mcp_kettlelogic.interfaces.serializer import ContentSerializer


class ServerApplication:
    """Builds and runs the MCP server."""

    def __init__(
        self,
        config: ServerConfig,
        mcp_server: McpContentServer,
        observer: OperationObserver,
        metrics_server: MetricsHttpServer,
    ) -> None:
        self._config = config
        self._mcp_server = mcp_server
        self._observer = observer
        self._metrics_server = metrics_server

    @classmethod
    def from_config(cls, config: ServerConfig) -> ServerApplication:
        observer = cls._build_observer(config)
        http_client = SiteHttpClient.create(config.base_url, config.http_timeout_seconds, observer)
        parser = HtmlParser()
        normalizer = TextNormalizer()
        slug_reader = SectionSlugReader(parser)
        article_cache: TtlCache[tuple[ArticleSummary, ...]] = TtlCache(config.cache_ttl_seconds)
        industry_cache: TtlCache[tuple[Industry, ...]] = TtlCache(config.cache_ttl_seconds)
        articles = ArticleService(
            http_client=http_client,
            parser=parser,
            normalizer=normalizer,
            slug_reader=slug_reader,
            cache=article_cache,
            observer=observer,
            max_articles=config.max_articles,
            fetch_concurrency=config.fetch_concurrency,
        )
        industries = IndustryService(
            http_client=http_client,
            parser=parser,
            normalizer=normalizer,
            slug_reader=slug_reader,
            cache=industry_cache,
            observer=observer,
            overview_max_chars=config.overview_max_chars,
        )
        mcp_server = McpContentServer(
            config=config,
            articles=articles,
            industries=industries,
            serializer=ContentSerializer(),
            observer=observer,
        )
        metrics_server = MetricsHttpServer(observer.registry, PrometheusRenderer())
        return cls(
            config=config, mcp_server=mcp_server, observer=observer, metrics_server=metrics_server
        )

    @classmethod
    def run_from_env(cls) -> None:
        cls.from_config(ConfigLoader().load()).run()

    def run(self) -> None:
        self._observer.logger.info(
            "starting mcp-kettlelogic base_url=%s transport=%s metrics_port=%s",
            self._config.base_url,
            self._config.transport.value,
            self._config.metrics_port,
        )
        self.start_metrics()
        self._mcp_server.run()  # pragma: no cover - blocking transport loop (see e2e)

    def start_metrics(self) -> None:
        port = self._config.metrics_port
        if port is None:
            return
        try:
            self._metrics_server.start(constants.METRICS_BIND_HOST, port)
        except OSError as exc:  # pragma: no cover - bind failure is environment-specific
            self._observer.logger.warning("metrics endpoint disabled: %s", exc)
            return
        self._observer.logger.info("metrics endpoint on :%d%s", port, constants.METRICS_PATH)

    def stop(self) -> None:
        self._metrics_server.stop()

    @classmethod
    def _build_observer(cls, config: ServerConfig) -> OperationObserver:
        logger = LoggerFactory().build(constants.LOGGER_NAME, config.log_level)
        return OperationObserver(logger, MetricsRegistry())
