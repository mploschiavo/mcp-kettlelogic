"""Domain enumerations. Comparisons use the enum members, never raw strings."""

from __future__ import annotations

from enum import StrEnum


class TransportKind(StrEnum):
    """How the MCP server is served to clients."""

    STDIO = "stdio"
    HTTP = "streamable-http"


class CacheOutcome(StrEnum):
    """Result of a cache lookup, used as a metric label."""

    HIT = "hit"
    MISS = "miss"
