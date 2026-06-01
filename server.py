#!/usr/bin/env python3
"""Kettle Logic MCP server.

A Model Context Protocol server that exposes a Kettle Logic site's published
content — whitepapers/playbooks ("insights") and industry pages — as MCP
resources and tools, fetched **live** over HTTP.

It is a pure read-only client of the public site: no database, no credentials,
no dependency on the operator's cluster or any AI/LLM backend. Point it at any
site with the same shape via the ``KETTLELOGIC_BASE_URL`` environment variable
(default ``https://kettlelogic.com``) and see what it discovers.

Transport: stdio (the MCP default), handled by the official ``mcp`` SDK.

Surface
-------
Resources
  - ``kettlelogic://articles/manifest``   JSON catalog of insight articles
  - ``kettlelogic://industries/list``     JSON list of industry pages
  - ``kettlelogic://articles/{slug}``     a single article as readable text

Tools
  - ``search_articles(query, limit=5)``       filter the article catalog
  - ``get_industry_overview(industry)``       plain-text overview of an industry
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_BASE_URL = "https://kettlelogic.com"
# Content changes rarely; cache catalogs briefly so a burst of tool calls in one
# agent turn doesn't re-crawl the site.
CACHE_TTL_SECONDS = 600
HTTP_TIMEOUT_SECONDS = 15.0
# Bound the per-article metadata fan-out so a hostile/huge index can't make the
# server open thousands of sockets at once.
MAX_ARTICLES = 200
_CONCURRENCY = asyncio.Semaphore(8)


# --------------------------------------------------------------------------- #
# Observability: logging (stderr only — stdout is the MCP stdio channel) +
# Prometheus-style metrics. Metrics are always logged; an optional /metrics HTTP
# endpoint is exposed when KETTLELOGIC_METRICS_PORT is set.
# --------------------------------------------------------------------------- #

def _make_logger() -> logging.Logger:
    log = logging.getLogger("mcp-kettlelogic")
    if not log.handlers:
        handler = logging.StreamHandler(sys.stderr)  # NEVER stdout
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        log.addHandler(handler)
    log.setLevel(os.environ.get("KETTLELOGIC_LOG_LEVEL", "INFO").upper())
    log.propagate = False
    return log


logger = _make_logger()


class Metrics:
    """Tiny, dependency-free metrics registry with Prometheus text exposition.

    Counters and a coarse latency summary (count/sum) per operation — enough to
    answer "how many calls, how many errors, how slow" without pulling in a
    metrics library. Thread-safe so the optional HTTP exposer can read it.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
        self.latency_count: dict[str, int] = {}
        self.latency_sum: dict[str, float] = {}

    def inc(self, name: str, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self.counters[key] = self.counters.get(key, 0) + 1

    def observe_latency(self, op: str, seconds: float) -> None:
        with self._lock:
            self.latency_count[op] = self.latency_count.get(op, 0) + 1
            self.latency_sum[op] = self.latency_sum.get(op, 0.0) + seconds

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            by_name: dict[str, list[tuple[tuple[tuple[str, str], ...], int]]] = {}
            for (name, labels), val in self.counters.items():
                by_name.setdefault(name, []).append((labels, val))
            for name, series in sorted(by_name.items()):
                lines.append(f"# TYPE {name} counter")
                for labels, val in series:
                    lbl = ",".join(f'{k}="{v}"' for k, v in labels)
                    lines.append(f"{name}{{{lbl}}} {val}" if lbl else f"{name} {val}")
            for op in sorted(self.latency_count):
                lines.append(f"# TYPE mcp_op_duration_seconds summary")
                lines.append(f'mcp_op_duration_seconds_count{{op="{op}"}} {self.latency_count[op]}')
                lines.append(f'mcp_op_duration_seconds_sum{{op="{op}"}} {self.latency_sum[op]:.6f}')
        return "\n".join(lines) + "\n"


metrics = Metrics()


@asynccontextmanager
async def _observe(op: str):
    """Time + count an operation; log start/finish; record errors. Re-raises."""
    metrics.inc("mcp_operations_total", op=op)
    started = time.monotonic()
    logger.debug("op.start op=%s", op)
    try:
        yield
    except Exception as exc:  # noqa: BLE001 — count then re-raise
        metrics.inc("mcp_errors_total", op=op, error=type(exc).__name__)
        logger.warning("op.error op=%s error=%s msg=%s", op, type(exc).__name__, exc)
        raise
    finally:
        dur = time.monotonic() - started
        metrics.observe_latency(op, dur)
        logger.info("op.done op=%s duration_ms=%.1f", op, dur * 1000)


def _start_metrics_server() -> HTTPServer | None:
    """Expose GET /metrics on KETTLELOGIC_METRICS_PORT, if set. Best-effort."""
    port = os.environ.get("KETTLELOGIC_METRICS_PORT")
    if not port:
        return None

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            body = metrics.render_prometheus().encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/plain; version=0.0.4")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:  # silence default stderr spam
            pass

    try:
        srv = HTTPServer(("0.0.0.0", int(port)), _Handler)
    except OSError as exc:  # pragma: no cover - bind failure is environment-specific
        logger.warning("metrics endpoint disabled: %s", exc)
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    logger.info("metrics endpoint listening on :%s/metrics", port)
    return srv


# --------------------------------------------------------------------------- #
# HTML parsing (stdlib only — no scraping libraries, no brittle regex)
# --------------------------------------------------------------------------- #

# Elements whose text is chrome, not content.
_SKIP_TEXT_TAGS = {"script", "style", "noscript", "template", "svg", "head"}
# Structural wrappers we drop entirely so overviews read like prose, not nav.
_SKIP_REGION_TAGS = {"nav", "header", "footer", "aside", "form"}
_BLOCK_TAGS = {
    "p", "div", "section", "article", "li", "ul", "ol", "br", "tr",
    "h1", "h2", "h3", "h4", "h5", "h6", "figure", "blockquote",
}


class _LinkParser(HTMLParser):
    """Collect ``(href, anchor_text)`` pairs from an index page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._href = href
                self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


class _TextParser(HTMLParser):
    """Extract readable body text + ``<title>`` and meta description."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TEXT_TAGS or tag in _SKIP_REGION_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            a = dict(attrs)
            if a.get("name") == "description" and a.get("content"):
                self.description = a["content"].strip()
        if tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TEXT_TAGS or tag in _SKIP_REGION_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        # Capture <title> even though it lives inside the skipped <head> region.
        if self._in_title:
            self.title += data
            return
        if self._skip_depth:
            return
        self._chunks.append(data)

    @property
    def text(self) -> str:
        raw = "".join(self._chunks)
        # collapse runs of blank lines and trailing spaces into tidy prose
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        out: list[str] = []
        for ln in lines:
            if ln or (out and out[-1]):
                out.append(ln)
        return "\n".join(out).strip()


# --------------------------------------------------------------------------- #
# Content client
# --------------------------------------------------------------------------- #

@dataclass
class _Cached:
    value: object
    at: float


@dataclass
class KettleLogicContent:
    """Read-only HTTP client for a Kettle Logic-shaped site.

    Injectable: tests pass an ``httpx.AsyncClient`` backed by a mock transport,
    so the whole surface is exercised with zero network.
    """

    base_url: str = DEFAULT_BASE_URL
    client: httpx.AsyncClient | None = None
    _cache: dict[str, _Cached] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={
                    "user-agent": "mcp-kettlelogic/1.0 "
                    "(+https://github.com/mploschiavo/mcp-kettlelogic)"
                },
            )

    # -- low level -------------------------------------------------------- #
    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    async def _get_text(self, path: str) -> str:
        assert self.client is not None
        url = self._url(path)
        metrics.inc("mcp_http_fetches_total")
        started = time.monotonic()
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            metrics.inc("mcp_http_errors_total", error=type(exc).__name__)
            logger.warning("fetch.error url=%s error=%s", url, type(exc).__name__)
            raise
        metrics.observe_latency("http_fetch", time.monotonic() - started)
        logger.debug("fetch.ok url=%s bytes=%d", url, len(resp.text))
        return resp.text

    async def _cached(self, key: str, producer):
        hit = self._cache.get(key)
        now = time.monotonic()
        if hit is not None and (now - hit.at) < CACHE_TTL_SECONDS:
            metrics.inc("mcp_cache_total", result="hit", key=key)
            logger.debug("cache.hit key=%s", key)
            return hit.value
        metrics.inc("mcp_cache_total", result="miss", key=key)
        logger.debug("cache.miss key=%s", key)
        value = await producer()
        self._cache[key] = _Cached(value=value, at=now)
        return value

    def _same_site_slugs(self, html: str, section: str) -> list[str]:
        """Slugs for ``/{section}/<slug>/`` links that belong to this site."""
        parser = _LinkParser()
        parser.feed(html)
        slugs: list[str] = []
        seen: set[str] = set()
        pat = re.compile(rf"^/{re.escape(section)}/([^/?#]+)/?$")
        for href, _text in parser.links:
            # ignore cross-origin links; keep only same-site section paths
            path = urlparse(href).path if "://" in href else href
            m = pat.match(path)
            if not m:
                continue
            slug = m.group(1)
            if slug not in seen:
                seen.add(slug)
                slugs.append(slug)
        return slugs

    # -- articles --------------------------------------------------------- #
    async def list_articles(self) -> list[dict[str, str]]:
        async def produce() -> list[dict[str, str]]:
            index = await self._get_text("/insights/")
            slugs = self._same_site_slugs(index, "insights")[:MAX_ARTICLES]

            async def meta(slug: str) -> dict[str, str]:
                fallback = {
                    "slug": slug,
                    "title": _slug_to_title(slug),
                    "description": "",
                    "url": self._url(f"/insights/{slug}/"),
                }
                async with _CONCURRENCY:
                    try:
                        page = await self._get_text(f"/insights/{slug}/")
                    except httpx.HTTPError:
                        return fallback
                p = _TextParser()
                p.feed(page)
                return {
                    "slug": slug,
                    "title": _clean_title(p.title) or _slug_to_title(slug),
                    "description": p.description,
                    "url": self._url(f"/insights/{slug}/"),
                }

            articles = await asyncio.gather(*(meta(s) for s in slugs))
            return sorted(articles, key=lambda a: a["slug"])

        return await self._cached("articles", produce)

    async def get_article(self, slug: str) -> dict[str, str]:
        page = await self._get_text(f"/insights/{slug}/")
        p = _TextParser()
        p.feed(page)
        return {
            "slug": slug,
            "title": _clean_title(p.title) or _slug_to_title(slug),
            "description": p.description,
            "url": self._url(f"/insights/{slug}/"),
            "text": p.text,
        }

    async def search_articles(self, query: str, limit: int = 5) -> dict[str, object]:
        query = (query or "").strip()
        if not query:
            raise ValueError("query is required")
        limit = max(1, min(int(limit), 25))
        needle = query.lower()
        results = [
            {
                "slug": a["slug"],
                "title": a["title"],
                "resource_uri": f"kettlelogic://articles/{a['slug']}",
                "url": a["url"],
            }
            for a in await self.list_articles()
            if needle in f"{a['slug']} {a['title']} {a['description']}".lower()
        ][:limit]
        return {"query": query, "count": len(results), "results": results}

    # -- industries ------------------------------------------------------- #
    async def list_industries(self) -> list[dict[str, str]]:
        async def produce() -> list[dict[str, str]]:
            # Prefer the llms.txt convention (cross-site, structured); fall back
            # to crawling the /industries/ index if the site has no llms.txt.
            items: dict[str, dict[str, str]] = {}
            try:
                llms = await self._get_text("/llms.txt")
                for title, url in re.findall(
                    r"^-\s+(.+?):\s+(https?://\S+)", llms, re.MULTILINE
                ):
                    m = re.search(r"/industries/([^/?#]+)/?$", urlparse(url).path)
                    if m:
                        slug = m.group(1)
                        items[slug] = {
                            "slug": slug,
                            "title": title.strip(),
                            "url": url.strip(),
                        }
            except httpx.HTTPError:
                pass
            if not items:
                index = await self._get_text("/industries/")
                for slug in self._same_site_slugs(index, "industries"):
                    items[slug] = {
                        "slug": slug,
                        "title": _slug_to_title(slug),
                        "url": self._url(f"/industries/{slug}/"),
                    }
            return sorted(items.values(), key=lambda i: i["slug"])

        return await self._cached("industries", produce)

    async def get_industry_overview(
        self, industry: str, max_chars: int = 1500
    ) -> dict[str, str]:
        industry = (industry or "").strip().lower()
        if not industry:
            raise ValueError("industry is required")
        try:
            page = await self._get_text(f"/industries/{industry}/")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ValueError(f"Unknown industry: {industry}") from exc
            raise
        p = _TextParser()
        p.feed(page)
        return {
            "industry": industry,
            "title": _clean_title(p.title) or _slug_to_title(industry),
            "url": self._url(f"/industries/{industry}/"),
            "overview": p.text[:max_chars].rstrip(),
        }

    async def aclose(self) -> None:
        if self.client is not None:
            await self.client.aclose()


def _slug_to_title(slug: str) -> str:
    return slug.replace("-", " ").title()


def _clean_title(raw: str) -> str:
    """Drop the trailing ' — Kettle Logic' (or '| Brand') site suffix."""
    title = " ".join((raw or "").split())
    return re.split(r"\s+[—|]\s+", title)[0].strip() if title else ""


# --------------------------------------------------------------------------- #
# MCP server (FastMCP, stdio)
# --------------------------------------------------------------------------- #

mcp = FastMCP("kettlelogic-content")
_content = KettleLogicContent(
    base_url=os.environ.get("KETTLELOGIC_BASE_URL", DEFAULT_BASE_URL)
)


@mcp.resource("kettlelogic://articles/manifest", mime_type="application/json")
async def articles_manifest() -> str:
    """Structured catalog of every insight article on the configured site."""
    async with _observe("articles_manifest"):
        items = await _content.list_articles()
        return json.dumps({"count": len(items), "items": items}, indent=2)


@mcp.resource("kettlelogic://industries/list", mime_type="application/json")
async def industries_list() -> str:
    """List of industry pages discovered on the configured site."""
    async with _observe("industries_list"):
        items = await _content.list_industries()
        return json.dumps({"count": len(items), "items": items}, indent=2)


@mcp.resource("kettlelogic://articles/{slug}", mime_type="text/plain")
async def article_resource(slug: str) -> str:
    """A single insight article rendered as readable text."""
    async with _observe("article_resource"):
        article = await _content.get_article(slug)
        return f"# {article['title']}\n\n{article['url']}\n\n{article['text']}"


@mcp.tool()
async def search_articles(query: str, limit: int = 5) -> str:
    """Search Kettle Logic insight articles by title/slug/description.

    Args:
        query: phrase to match (e.g. "retail", "data quality").
        limit: max results, 1–25 (default 5).
    """
    async with _observe("search_articles"):
        return json.dumps(await _content.search_articles(query, limit), indent=2)


@mcp.tool()
async def get_industry_overview(industry: str) -> str:
    """Return a plain-text overview for an industry page.

    Args:
        industry: industry slug (e.g. "retail", "healthcare", "manufacturing").
                  Use ``kettlelogic://industries/list`` to discover valid slugs.
    """
    async with _observe("get_industry_overview"):
        return json.dumps(await _content.get_industry_overview(industry), indent=2)


def main() -> None:
    logger.info(
        "starting mcp-kettlelogic base_url=%s metrics_port=%s",
        _content.base_url,
        os.environ.get("KETTLELOGIC_METRICS_PORT", "off"),
    )
    _start_metrics_server()
    mcp.run()  # pragma: no cover - blocking stdio loop, covered by test_e2e.py


if __name__ == "__main__":  # pragma: no cover
    main()
