# mcp-kettlelogic

A **Model Context Protocol (MCP) server** that exposes a [Kettle Logic](https://kettlelogic.com)
site's published content — whitepapers/playbooks ("insights") and industry pages —
to any MCP-capable agent (Claude Desktop, IDEs, custom orchestrators).

It is a **pure, read-only client of the public website**: it fetches content live
over HTTP and parses it with the Python standard library. No database, no API keys,
no dependency on any backend cluster or LLM. The target site is configurable, so you
can point it at your own deployment — or any site with the same shape — and see what
it discovers.

Built on the official [`mcp`](https://pypi.org/project/mcp/) Python SDK (FastMCP),
speaking the standard **stdio** transport.

---

## What it exposes

### Tools
| Tool | Description |
|------|-------------|
| `search_articles(query, limit=5)` | Search insight articles by title / slug / description. |
| `get_industry_overview(industry)` | Plain-text overview extracted from an industry page. |

### Resources
| URI | Description |
|-----|-------------|
| `kettlelogic://articles/manifest` | JSON catalog of every insight article (slug, title, description, url). |
| `kettlelogic://industries/list` | JSON list of industry pages discovered on the site. |
| `kettlelogic://articles/{slug}` | A single article rendered as readable text. |

Discovery is live: articles come from the site's `/insights/` index, and industries
from its [`/llms.txt`](https://llmstxt.org/) (falling back to crawling `/industries/`).

---

## Install

```bash
pip install .            # or: pip install -r requirements.txt
```

Requires Python ≥ 3.10. Dependencies: `mcp`, `httpx` (both pulled in automatically).

## Run

```bash
mcp-kettlelogic          # console script (installed by `pip install .`)
# or
python server.py
```

The server talks MCP over stdio, so it's normally launched **by an MCP client**, not
by hand. To smoke-test it interactively, use the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector mcp-kettlelogic
```

## Configure

| Env var | Default | Purpose |
|---------|---------|---------|
| `KETTLELOGIC_BASE_URL` | `https://kettlelogic.com` | Target site to read. Point it at your own site. |
| `KETTLELOGIC_LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG`/`INFO`/`WARNING`/…). Logs go to **stderr**. |
| `KETTLELOGIC_METRICS_PORT` | _(unset)_ | If set, serve Prometheus metrics at `http://<host>:<port>/metrics`. |

## Use it in an MCP client

```json
{
  "mcpServers": {
    "kettlelogic": {
      "command": "mcp-kettlelogic",
      "env": { "KETTLELOGIC_BASE_URL": "https://kettlelogic.com" }
    }
  }
}
```

Or, without installing, point at the script directly:

```json
{
  "mcpServers": {
    "kettlelogic": {
      "command": "python",
      "args": ["server.py"]
    }
  }
}
```

## Run in Docker

```bash
docker build -t kettlelogic-mcp:latest .
docker run --rm -i kettlelogic-mcp:latest      # -i: stdio is interactive
```

```json
{
  "mcpServers": {
    "kettlelogic": {
      "command": "docker",
      "args": ["run", "--rm", "-i",
               "-e", "KETTLELOGIC_BASE_URL=https://kettlelogic.com",
               "kettlelogic-mcp:latest"]
    }
  }
}
```

---

## Observability

**Logging** — structured logs to **stderr** (never stdout, which is the MCP channel):
operation start/finish with durations, fetch results, cache hits/misses, and errors.
Control with `KETTLELOGIC_LOG_LEVEL`.

**Metrics** — when `KETTLELOGIC_METRICS_PORT` is set, the server exposes
Prometheus-format metrics at `/metrics`:

| Metric | Type | Labels |
|--------|------|--------|
| `mcp_operations_total` | counter | `op` |
| `mcp_errors_total` | counter | `op`, `error` |
| `mcp_http_fetches_total` | counter | — |
| `mcp_http_errors_total` | counter | `error` |
| `mcp_cache_total` | counter | `result` (hit/miss), `key` |
| `mcp_op_duration_seconds` | summary | `op` |

```bash
KETTLELOGIC_METRICS_PORT=9464 mcp-kettlelogic &
curl localhost:9464/metrics
```

---

## Develop & test

```bash
pip install -e ".[dev]"
pytest                       # unit + e2e, with coverage gate (fail-under 90%)
```

- `test_server.py` — unit tests against an injected `httpx.MockTransport` (no network):
  parsers, tools, resources, caching, metrics, and error paths.
- `test_e2e.py` — launches the **real server over real MCP stdio** (via the official
  SDK client) against a local HTTP fixture site, exercising the full handshake →
  tools/resources → fetch → parse path.

Coverage runs ~99%.

## How it works

See [ARCHITECTURE.md](./ARCHITECTURE.md) for diagrams and design notes.

## License

MIT — see [LICENSE](./LICENSE).
