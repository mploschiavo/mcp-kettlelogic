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
speaking the standard **stdio** transport (and an optional **streamable-http**
transport for container/Kubernetes deployment).

> Engineering note: this repository doubles as a reference for how we build —
> hexagonal layering, fully-typed OO, dependency injection, and a suite of
> **ratchets** (see [ARCHITECTURE.md](./ARCHITECTURE.md)) that enforce the rules
> in CI. `pytest` runs unit tests, real-stdio e2e tests, and the ratchets together.

---

## What it exposes

### Tools
| Tool | Description |
|------|-------------|
| `search_articles(query, limit=5)` | Search insight articles by title / slug / description. |
| `get_industry_overview(industry)` | Plain-text overview extracted from an industry page. |
| `list_articles()` | JSON catalog of every insight article (title, slug, description). |
| `list_industries()` | JSON list of industries with guidance (name + slug). |
| `get_article(slug)` | A single insight article rendered as readable text. |

### Resources
| URI | Description |
|-----|-------------|
| `kettlelogic://articles/manifest` | JSON catalog of every insight article. |
| `kettlelogic://industries/list` | JSON list of industry pages discovered on the site. |
| `kettlelogic://articles/{slug}` | A single article rendered as readable text. |

Discovery is live: articles from the site's `/insights/` index, industries from its
[`/llms.txt`](https://llmstxt.org/) (falling back to crawling `/industries/`).

---

## Install & run

```bash
pip install .            # Python >= 3.11; pulls in mcp + httpx
mcp-kettlelogic          # console script (stdio transport by default)
```

Normally an MCP client launches it. To explore interactively:

```bash
npx @modelcontextprotocol/inspector mcp-kettlelogic
```

### Use it in an MCP client

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

### Or connect to the hosted server (no install)

A hardened instance runs live over streamable-HTTP — point any MCP client at it:

```json
{
  "mcpServers": {
    "kettlelogic": { "url": "https://kettlelogic.com/mcp" }
  }
}
```

## Publishing to the MCP registry

This server is listed in the public [MCP registry](https://registry.modelcontextprotocol.io)
as **`com.kettlelogic/mcp-kettlelogic`** (brand: *kettlelogic*, not a personal GitHub
handle). [`server.json`](server.json) is the manifest — it advertises the hosted
streamable-HTTP remote and validates against the `2025-12-11` schema.

The listing is claimed by **HTTP domain ownership**, not a GitHub login: the registry
fetches `https://kettlelogic.com/.well-known/mcp-registry-auth` (a public-key challenge
served by the marketing site — `web/public/.well-known/mcp-registry-auth` in the
`kettlelogic` repo) and verifies a signature made with our Ed25519 **private** key.

### Automated (preferred)

[`.github/workflows/publish-registry.yml`](.github/workflows/publish-registry.yml)
**publishes automatically on every GitHub Release** (and via manual *Run workflow*).
It aligns `server.json`'s `version` with the release tag, validates, then
`login http` + `publish` using the `MCP_REGISTRY_KEY` repo secret.

So the normal flow is just: **bump `version.py` + `server.json` `version`, then cut a
GitHub Release** — the registry updates itself.

**One-time secret setup** (the CI's signing key — run locally, never prints the key):

```bash
gh secret set MCP_REGISTRY_KEY --repo mploschiavo/mcp-kettlelogic \
  --body "$(openssl pkey -in .secrets/mcp-registry-key.pem -outform DER | tail -c 32 | xxd -p -c 64)"
```

### Manual

If you ever need to publish by hand:

```bash
# 1. Get the CLI (prebuilt binary from the registry releases)
curl -L https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_linux_amd64.tar.gz | tar xz mcp-publisher

# 2. From the repo root (where server.json lives):
./mcp-publisher validate
./mcp-publisher login http --domain kettlelogic.com \
  --private-key "$(openssl pkey -in .secrets/mcp-registry-key.pem -outform DER | tail -c 32 | xxd -p -c 64)"
./mcp-publisher publish
```

### Keys & rotation

- The Ed25519 **private key** lives at `.secrets/mcp-registry-key.pem` (gitignored) and
  is the publish credential for the `com.kettlelogic` namespace — keep it in a password
  manager. The matching **public** key is committed only as the served challenge file.
- **Rotate:** generate a new key (`openssl genpkey -algorithm Ed25519 -out
  .secrets/mcp-registry-key.pem`), regenerate the challenge file
  (`echo "v=MCPv1; k=ed25519; p=$(openssl pkey -in .secrets/mcp-registry-key.pem -pubout -outform DER | tail -c 32 | base64)" > ../kettlelogic/web/public/.well-known/mcp-registry-auth`),
  redeploy the site, update the `MCP_REGISTRY_KEY` secret, then re-publish.
- **Versions are immutable** in the registry — you can't re-publish an existing version;
  bump it first.

## Configure

| Env var | Default | Purpose |
|---------|---------|---------|
| `KETTLELOGIC_BASE_URL` | `https://kettlelogic.com` | Target site to read. Point it at your own. |
| `KETTLELOGIC_TRANSPORT` | `stdio` | `stdio` (local clients) or `streamable-http` (network/k8s). |
| `KETTLELOGIC_HTTP_HOST` / `KETTLELOGIC_HTTP_PORT` | `0.0.0.0` / `8080` | Bind for the http transport. |
| `KETTLELOGIC_METRICS_PORT` | _(unset)_ | If set, serve Prometheus metrics at `/metrics`. |
| `KETTLELOGIC_LOG_LEVEL` | `INFO` | Log level. Logs go to **stderr** (stdout is the MCP channel). |
| `KETTLELOGIC_CACHE_TTL_SECONDS` / `KETTLELOGIC_MAX_ARTICLES` / `KETTLELOGIC_FETCH_CONCURRENCY` / `KETTLELOGIC_OVERVIEW_MAX_CHARS` | see `constants.py` | Tuning. |

## Containers & Kubernetes

For network deployment the server runs the **streamable-http** transport.

```bash
docker compose -f deploy/docker/docker-compose.yaml up --build
```

Kubernetes manifests live in [`deploy/k8s/`](./deploy/k8s/) (Deployment with 2
replicas, readiness/liveness probes, resource bounds, non-root + read-only root FS,
ClusterIP Service, ConfigMap). Apply with:

```bash
kubectl apply -k deploy/k8s
```

## Observability

- **Logging** — structured logs to **stderr**: operation start/finish + durations,
  fetch results, cache hits/misses, errors. Set `KETTLELOGIC_LOG_LEVEL`.
- **Metrics** — Prometheus `/metrics` (set `KETTLELOGIC_METRICS_PORT`):
  `mcp_operations_total`, `mcp_errors_total`, `mcp_http_fetches_total`,
  `mcp_http_errors_total`, `mcp_cache_total{result}`, `mcp_op_duration_seconds`.

## Develop & test

```bash
pip install -e ".[dev]"
ruff check src tests        # lint + import order
mypy                        # type check (disallow-untyped-defs)
pytest                      # unit + e2e + ratchets, coverage gate (fail-under 90%)
```

Coverage runs ~99%. See [ARCHITECTURE.md](./ARCHITECTURE.md) for layering, the
request flow, and the full list of ratchets.

## License

MIT — see [LICENSE](./LICENSE).
