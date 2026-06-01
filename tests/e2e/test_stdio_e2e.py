"""End-to-end: drive the packaged server over real MCP stdio.

Launches ``ServerApplication.run_from_env`` as a subprocess via the official MCP
stdio client, pointed at a local HTTP fixture site, and exercises the full
handshake → tools/resources → live fetch → parse path.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("mcp.client.stdio")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

_LAUNCH = "from mcp_kettlelogic.cli.main import ServerApplication; ServerApplication.run_from_env()"

PAGES = {
    "/insights/": """<html><body><main>
        <a href="/insights/retail-strategy/">Retail</a>
        <a href="/insights/healthcare-playbook/">Healthcare</a></main></body></html>""",
    "/insights/retail-strategy/": """<html><head>
        <title>Retail Omnichannel Revenue — Kettle Logic</title>
        <meta name="description" content="Executive strategy."></head>
        <body><main><h1>Retail</h1>
        <p>Omnichannel revenue architecture.</p></main></body></html>""",
    "/insights/healthcare-playbook/": """<html><head>
        <title>Healthcare Ops — Kettle Logic</title></head>
        <body><main><p>Care pathways.</p></main></body></html>""",
    "/llms.txt": "# K\n- Retail: http://HOST/industries/retail/\n",
    "/industries/retail/": """<html><head><title>Retail — Kettle Logic</title></head>
        <body><main><h2>Retail</h2><p>Unify inventory.</p></main></body></html>""",
}


@pytest.fixture
def site() -> str:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = PAGES.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            host = f"127.0.0.1:{self.server.server_address[1]}"
            payload = body.replace("HOST", host).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


@contextlib.asynccontextmanager
async def _session(base_url: str) -> AsyncIterator[ClientSession]:
    env = {**os.environ, "KETTLELOGIC_BASE_URL": base_url, "KETTLELOGIC_LOG_LEVEL": "WARNING"}
    params = StdioServerParameters(command=sys.executable, args=["-c", _LAUNCH], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def test_e2e_lists_tools_and_resources(site: str) -> None:
    async with _session(site) as session:
        tools = {tool.name for tool in (await session.list_tools()).tools}
        assert {
            "search_articles",
            "get_industry_overview",
            "list_articles",
            "list_industries",
            "get_article",
        } <= tools
        resources = {str(r.uri) for r in (await session.list_resources()).resources}
        assert "kettlelogic://articles/manifest" in resources


async def test_e2e_search_tool(site: str) -> None:
    async with _session(site) as session:
        result = await session.call_tool("search_articles", {"query": "retail"})
        payload = json.loads(result.content[0].text)
        assert payload["results"][0]["slug"] == "retail-strategy"


async def test_e2e_read_article_resource(site: str) -> None:
    async with _session(site) as session:
        result = await session.read_resource("kettlelogic://articles/retail-strategy")
        text = result.contents[0].text
        assert "Retail Omnichannel Revenue" in text
        assert "Omnichannel revenue architecture" in text


async def test_e2e_unknown_industry_errors(site: str) -> None:
    async with _session(site) as session:
        result = await session.call_tool("get_industry_overview", {"industry": "atlantis"})
        assert result.isError
        assert "Unknown industry" in result.content[0].text
