"""End-to-end tests: drive the real server over the real MCP stdio protocol.

Unlike ``test_server.py`` (which unit-tests the client with a mock transport),
this spins up an actual local HTTP server with fixture content, launches
``server.py`` as a subprocess via the official MCP stdio client, and exercises
the full path: MCP handshake → tools/resources → live HTTP fetch → parse.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

mcp_client = pytest.importorskip("mcp.client.stdio")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

HERE = Path(__file__).resolve().parent

PAGES = {
    "/insights/": """<html><body><main>
        <a href="/insights/retail-strategy/">Retail Strategy</a>
        <a href="/insights/healthcare-playbook/">Healthcare Playbook</a>
        </main></body></html>""",
    "/insights/retail-strategy/": """<html><head>
        <title>Retail Omnichannel Revenue — Kettle Logic</title>
        <meta name="description" content="Executive strategy on retail revenue."></head>
        <body><nav>junk</nav><main><h1>Retail</h1>
        <p>Omnichannel revenue architecture for modern retail.</p></main></body></html>""",
    "/insights/healthcare-playbook/": """<html><head>
        <title>Healthcare Ops — Kettle Logic</title></head>
        <body><main><p>Care pathways.</p></main></body></html>""",
    "/llms.txt": "# K\n- Retail: http://HOST/industries/retail/\n",
    "/industries/retail/": """<html><head><title>Retail — Kettle Logic</title></head>
        <body><main><h2>Retail</h2><p>Unify inventory and fulfillment.</p></main></body></html>""",
}


@pytest.fixture
def site():
    """A local HTTP server serving the fixture pages; yields its base URL."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
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

        def log_message(self, *_a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()


@contextlib.asynccontextmanager
async def _session(base_url: str):
    env = {**os.environ, "KETTLELOGIC_BASE_URL": base_url, "KETTLELOGIC_LOG_LEVEL": "WARNING"}
    params = StdioServerParameters(
        command=sys.executable, args=[str(HERE / "server.py")], env=env, cwd=str(HERE)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def test_e2e_lists_tools_and_resources(site):
    async with _session(site) as session:
        tools = {t.name for t in (await session.list_tools()).tools}
        assert {"search_articles", "get_industry_overview"} <= tools

        resources = {str(r.uri) for r in (await session.list_resources()).resources}
        assert "kettlelogic://articles/manifest" in resources
        assert "kettlelogic://industries/list" in resources


async def test_e2e_search_articles_tool(site):
    async with _session(site) as session:
        result = await session.call_tool("search_articles", {"query": "retail"})
        payload = json.loads(result.content[0].text)
        assert payload["count"] == 1
        assert payload["results"][0]["slug"] == "retail-strategy"


async def test_e2e_get_industry_overview_tool(site):
    async with _session(site) as session:
        result = await session.call_tool("get_industry_overview", {"industry": "retail"})
        payload = json.loads(result.content[0].text)
        assert "Unify inventory" in payload["overview"]


async def test_e2e_read_manifest_and_article_resources(site):
    async with _session(site) as session:
        manifest_res = await session.read_resource("kettlelogic://articles/manifest")
        manifest = json.loads(manifest_res.contents[0].text)
        assert manifest["count"] == 2

        article_res = await session.read_resource("kettlelogic://articles/retail-strategy")
        text = article_res.contents[0].text
        assert "Retail Omnichannel Revenue" in text
        assert "Omnichannel revenue architecture" in text


async def test_e2e_unknown_industry_is_error(site):
    async with _session(site) as session:
        result = await session.call_tool("get_industry_overview", {"industry": "nope"})
        # tool errors surface as isError with the message in content
        assert result.isError
        assert "Unknown industry" in result.content[0].text
