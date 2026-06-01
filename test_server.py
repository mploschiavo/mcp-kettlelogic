"""Unit tests for the Kettle Logic MCP content client + MCP surface.

The client takes an injectable ``httpx.AsyncClient``; here we back it with an
``httpx.MockTransport`` that serves a tiny fake site, so every parser/tool/
resource path — plus logging, metrics and caching — is exercised with zero
network. The real stdio protocol is covered separately in ``test_e2e.py``.
"""

from __future__ import annotations

import json

import httpx
import pytest

import server
from server import KettleLogicContent, Metrics, _clean_title, _slug_to_title, _TextParser

BASE = "https://example.test"

INSIGHTS_INDEX = """
<html><body><nav><a href="/">Home</a></nav>
<main>
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
    # an article whose page 500s — list_articles must degrade, not crash
    "broken-article": "BOOM",
}

LLMS_TXT = """# Kettle Logic
## Key pages
- Home: https://example.test/
- Retail: https://example.test/industries/retail/
- Healthcare: https://example.test/industries/healthcare/
- Legal: https://example.test/legal/
"""

INDUSTRY_RETAIL = """
<html><head><title>Retail — Kettle Logic</title></head>
<body><nav>nav</nav><main><h2>Retail</h2>
<p>Unify inventory, pricing, and fulfillment across channels.</p>
</main><footer>f</footer></body></html>
"""

# index variant with no llms.txt → industries discovered by crawling
INDUSTRIES_INDEX = """
<html><body><main>
  <a href="/industries/retail/">Retail</a>
  <a href="/industries/energy/">Energy</a>
</main></body></html>
"""


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/insights/":
        return httpx.Response(200, text=INSIGHTS_INDEX)
    if path == "/llms.txt":
        return httpx.Response(200, text=LLMS_TXT)
    if path == "/industries/":
        return httpx.Response(200, text=INDUSTRIES_INDEX)
    if path == "/industries/retail/":
        return httpx.Response(200, text=INDUSTRY_RETAIL)
    if path == "/insights/broken-article/":
        return httpx.Response(500, text="boom")
    if path.startswith("/insights/"):
        slug = path.strip("/").split("/")[-1]
        if slug in ARTICLES:
            return httpx.Response(200, text=ARTICLES[slug])
    return httpx.Response(404, text="not found")


def make_content(handler=_handler, base_url=BASE) -> KettleLogicContent:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=base_url)
    return KettleLogicContent(base_url=base_url, client=client)


@pytest.fixture
async def content():
    c = make_content()
    yield c
    await c.aclose()


# --- pure helpers ------------------------------------------------------------

def test_text_parser_strips_chrome_and_scripts():
    p = _TextParser()
    p.feed(ARTICLES["retail-strategy"])
    assert "Omnichannel revenue architecture" in p.text
    assert "var x" not in p.text          # script dropped
    assert "menu junk" not in p.text      # nav dropped
    assert "footer junk" not in p.text    # footer dropped
    assert p.description == "Executive strategy on retail revenue."
    assert p.title.strip().startswith("Retail Omnichannel Revenue")


def test_clean_title_and_slug_helpers():
    assert _clean_title("Retail Omnichannel Revenue — Kettle Logic") == "Retail Omnichannel Revenue"
    assert _clean_title("Foo | Bar") == "Foo"
    assert _clean_title("") == ""
    assert _slug_to_title("automotive-aftermarket") == "Automotive Aftermarket"


def test_base_url_trailing_slash_normalized():
    c = make_content(base_url=BASE + "/")
    assert c.base_url == BASE
    assert c._url("/insights/") == f"{BASE}/insights/"


def test_default_client_is_constructed_when_none():
    c = KettleLogicContent(base_url=BASE)   # no client injected
    assert c.client is not None


# --- articles ----------------------------------------------------------------

async def test_list_articles_dedupes_skips_offsite_and_degrades(content):
    items = await content.list_articles()
    slugs = [a["slug"] for a in items]
    # sorted, deduped; broken-article still listed (degraded), offsite/about excluded
    assert slugs == ["broken-article", "healthcare-playbook", "retail-strategy"]
    titles = {a["slug"]: a["title"] for a in items}
    assert titles["retail-strategy"] == "Retail Omnichannel Revenue"     # suffix stripped
    assert titles["broken-article"] == "Broken Article"                  # slug-derived fallback


async def test_get_article_returns_readable_text(content):
    art = await content.get_article("retail-strategy")
    assert art["title"] == "Retail Omnichannel Revenue"
    assert "Omnichannel revenue architecture" in art["text"]
    assert art["url"] == f"{BASE}/insights/retail-strategy/"
    assert art["description"] == "Executive strategy on retail revenue."


async def test_get_article_404_raises(content):
    with pytest.raises(httpx.HTTPStatusError):
        await content.get_article("nope")


async def test_search_articles_matches_and_shapes_result(content):
    res = await content.search_articles("retail")
    assert res["count"] == 1
    assert res["results"][0]["slug"] == "retail-strategy"
    assert res["results"][0]["resource_uri"] == "kettlelogic://articles/retail-strategy"
    assert res["results"][0]["url"] == f"{BASE}/insights/retail-strategy/"


async def test_search_requires_query(content):
    with pytest.raises(ValueError):
        await content.search_articles("   ")


async def test_search_limit_is_clamped(content):
    res = await content.search_articles("a", limit=999)   # clamps to 25, no crash
    assert res["count"] <= 25


# --- industries --------------------------------------------------------------

async def test_list_industries_from_llms_txt(content):
    items = await content.list_industries()
    slugs = [i["slug"] for i in items]
    assert slugs == ["healthcare", "retail"]
    assert {i["slug"]: i["title"] for i in items}["retail"] == "Retail"


async def test_list_industries_falls_back_to_index_when_no_llms(content):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/llms.txt":
            return httpx.Response(404)
        return _handler(request)

    c = make_content(handler)
    items = await c.list_industries()
    assert [i["slug"] for i in items] == ["energy", "retail"]
    await c.aclose()


async def test_industry_overview(content):
    ov = await content.get_industry_overview("retail")
    assert "Unify inventory" in ov["overview"]
    assert ov["title"] == "Retail"
    assert ov["url"] == f"{BASE}/industries/retail/"


async def test_unknown_industry_raises_valueerror(content):
    with pytest.raises(ValueError):
        await content.get_industry_overview("does-not-exist")


async def test_industry_requires_argument(content):
    with pytest.raises(ValueError):
        await content.get_industry_overview("  ")


async def test_industry_non_404_error_propagates():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    c = make_content(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await c.get_industry_overview("retail")
    await c.aclose()


async def test_caching_returns_same_object(content):
    first = await content.list_industries()
    cached = await content.list_industries()
    assert first == cached
    # second call must have registered a cache hit
    hits = [v for (n, lbl), v in server.metrics.counters.items()
            if n == "mcp_cache_total" and ("result", "hit") in lbl]
    assert sum(hits) >= 1


# --- metrics -----------------------------------------------------------------

def test_metrics_render_prometheus_roundtrip():
    m = Metrics()
    m.inc("mcp_operations_total", op="x")
    m.inc("mcp_operations_total", op="x")
    m.inc("mcp_errors_total", op="x", error="ValueError")
    m.observe_latency("x", 0.05)
    out = m.render_prometheus()
    assert 'mcp_operations_total{op="x"} 2' in out
    assert 'mcp_errors_total{error="ValueError",op="x"} 1' in out
    assert 'mcp_op_duration_seconds_count{op="x"} 1' in out
    assert "# TYPE" in out


def test_metrics_render_handles_unlabeled_counter():
    m = Metrics()
    m.inc("plain_counter")
    assert "plain_counter 1" in m.render_prometheus()


# --- MCP surface wrappers (cover _observe success + error paths) -------------

async def test_mcp_tool_and_resource_wrappers(monkeypatch, content):
    monkeypatch.setattr(server, "_content", content)

    manifest = json.loads(await server.articles_manifest())
    assert manifest["count"] == 3

    industries = json.loads(await server.industries_list())
    assert industries["count"] == 2

    article = await server.article_resource("retail-strategy")
    assert article.startswith("# Retail Omnichannel Revenue")

    search = json.loads(await server.search_articles("healthcare"))
    assert search["results"][0]["slug"] == "healthcare-playbook"

    overview = json.loads(await server.get_industry_overview("retail"))
    assert "Unify inventory" in overview["overview"]


async def test_mcp_wrapper_error_is_counted(monkeypatch, content):
    monkeypatch.setattr(server, "_content", content)
    before = dict(server.metrics.counters)
    with pytest.raises(ValueError):
        await server.get_industry_overview("nope")
    # an mcp_errors_total{op=get_industry_overview,...} counter advanced
    err = [v for (n, lbl), v in server.metrics.counters.items()
           if n == "mcp_errors_total" and ("op", "get_industry_overview") in lbl]
    assert sum(err) >= 1
    assert server.metrics.counters != before


def test_metrics_server_disabled_without_env(monkeypatch):
    monkeypatch.delenv("KETTLELOGIC_METRICS_PORT", raising=False)
    assert server._start_metrics_server() is None


def test_metrics_server_starts_and_serves(monkeypatch):
    monkeypatch.setenv("KETTLELOGIC_METRICS_PORT", "0")  # OS-assigned free port
    srv = server._start_metrics_server()
    assert srv is not None
    try:
        host, port = srv.server_address
        resp = httpx.get(f"http://127.0.0.1:{port}/metrics")
        assert resp.status_code == 200
        assert "# TYPE" in resp.text
        assert httpx.get(f"http://127.0.0.1:{port}/nope").status_code == 404
    finally:
        srv.shutdown()
