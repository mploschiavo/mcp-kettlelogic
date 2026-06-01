"""Named constants — the single home for literals.

Per the project's ratchets, magic numbers and meaningful string literals do not
appear inline in business logic; they are named here and imported. Env-var names
live in the config layer (the only place allowed to read the environment).
"""

from __future__ import annotations

from typing import Final

from mcp_kettlelogic.version import VERSION

# -- identity --------------------------------------------------------------- #
SERVER_NAME: Final = "kettlelogic-content"
USER_AGENT: Final = f"mcp-kettlelogic/{VERSION} (+https://github.com/mploschiavo/mcp-kettlelogic)"
LOGGER_NAME: Final = "mcp-kettlelogic"
LOG_FORMAT: Final = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

# -- target site ------------------------------------------------------------ #
DEFAULT_BASE_URL: Final = "https://kettlelogic.com"
INSIGHTS_INDEX_PATH: Final = "/insights/"
INDUSTRIES_INDEX_PATH: Final = "/industries/"
LLMS_TXT_PATH: Final = "/llms.txt"
ARTICLE_PATH_TEMPLATE: Final = "/insights/{slug}/"
INDUSTRY_PATH_TEMPLATE: Final = "/industries/{slug}/"
INSIGHTS_SECTION: Final = "insights"
INDUSTRIES_SECTION: Final = "industries"

# -- MCP resource surface --------------------------------------------------- #
RESOURCE_SCHEME: Final = "kettlelogic"
ARTICLES_MANIFEST_URI: Final = "kettlelogic://articles/manifest"
INDUSTRIES_LIST_URI: Final = "kettlelogic://industries/list"
ARTICLE_RESOURCE_URI_TEMPLATE: Final = "kettlelogic://articles/{slug}"
TOOL_SEARCH_ARTICLES: Final = "search_articles"
TOOL_GET_INDUSTRY_OVERVIEW: Final = "get_industry_overview"
TOOL_LIST_ARTICLES: Final = "list_articles"
TOOL_LIST_INDUSTRIES: Final = "list_industries"
TOOL_GET_ARTICLE: Final = "get_article"

# -- tunable defaults (overridable via config) ------------------------------ #
DEFAULT_CACHE_TTL_SECONDS: Final = 600.0
DEFAULT_HTTP_TIMEOUT_SECONDS: Final = 15.0
DEFAULT_MAX_ARTICLES: Final = 200
DEFAULT_FETCH_CONCURRENCY: Final = 8
DEFAULT_OVERVIEW_MAX_CHARS: Final = 1500
DEFAULT_SEARCH_LIMIT: Final = 5
MIN_SEARCH_LIMIT: Final = 1
MAX_SEARCH_LIMIT: Final = 25
DEFAULT_LOG_LEVEL: Final = "INFO"

# -- transport / serving ---------------------------------------------------- #
DEFAULT_HTTP_HOST: Final = "0.0.0.0"  # noqa: S104 - container listen address by design
DEFAULT_HTTP_PORT: Final = 8080
METRICS_PATH: Final = "/metrics"
METRICS_CONTENT_TYPE: Final = "text/plain; version=0.0.4"
METRICS_BIND_HOST: Final = "0.0.0.0"  # noqa: S104 - container listen address by design

# -- HTTP status codes ------------------------------------------------------ #
HTTP_NOT_FOUND: Final = 404

# -- cache keys ------------------------------------------------------------- #
CACHE_KEY_ARTICLES: Final = "articles"
CACHE_KEY_INDUSTRIES: Final = "industries"

# -- operation names (metric/latency labels) -------------------------------- #
HTTP_FETCH_OPERATION: Final = "http_fetch"

# -- HTML parsing ----------------------------------------------------------- #
# Tags whose text is chrome rather than content.
SKIP_TEXT_TAGS: Final[frozenset[str]] = frozenset(
    {"script", "style", "noscript", "template", "svg", "head"}
)
# Structural wrappers dropped entirely so extracted prose reads cleanly.
SKIP_REGION_TAGS: Final[frozenset[str]] = frozenset({"nav", "header", "footer", "aside", "form"})
# Tags that introduce a line break in extracted text.
BLOCK_TAGS: Final[frozenset[str]] = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "li",
        "ul",
        "ol",
        "br",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "figure",
        "blockquote",
    }
)
ANCHOR_TAG: Final = "a"
TITLE_TAG: Final = "title"
META_TAG: Final = "meta"
HREF_ATTR: Final = "href"
META_NAME_ATTR: Final = "name"
META_CONTENT_ATTR: Final = "content"
META_DESCRIPTION_NAME: Final = "description"

# Splits a page <title> on its " — Brand" / " | Brand" suffix.
TITLE_SUFFIX_SEPARATORS: Final = r"\s+[—|]\s+"
# Parses "- Title: https://url" lines out of an llms.txt listing.
LLMS_LINK_PATTERN: Final = r"^-\s+(.+?):\s+(https?://\S+)"
