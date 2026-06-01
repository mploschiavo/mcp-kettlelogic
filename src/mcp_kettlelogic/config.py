"""Configuration layer.

This is the single place in the codebase that reads the process environment
(enforced by a ratchet). Everything else receives a frozen :class:`ServerConfig`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from mcp_kettlelogic import constants
from mcp_kettlelogic.domain.enums import TransportKind

ENV_BASE_URL: Final = "KETTLELOGIC_BASE_URL"
ENV_LOG_LEVEL: Final = "KETTLELOGIC_LOG_LEVEL"
ENV_METRICS_PORT: Final = "KETTLELOGIC_METRICS_PORT"
ENV_TRANSPORT: Final = "KETTLELOGIC_TRANSPORT"
ENV_HTTP_HOST: Final = "KETTLELOGIC_HTTP_HOST"
ENV_HTTP_PORT: Final = "KETTLELOGIC_HTTP_PORT"
ENV_CACHE_TTL: Final = "KETTLELOGIC_CACHE_TTL_SECONDS"
ENV_HTTP_TIMEOUT: Final = "KETTLELOGIC_HTTP_TIMEOUT_SECONDS"
ENV_MAX_ARTICLES: Final = "KETTLELOGIC_MAX_ARTICLES"
ENV_FETCH_CONCURRENCY: Final = "KETTLELOGIC_FETCH_CONCURRENCY"
ENV_OVERVIEW_MAX_CHARS: Final = "KETTLELOGIC_OVERVIEW_MAX_CHARS"

_TRANSPORT_ALIASES: Final[Mapping[str, TransportKind]] = {
    "stdio": TransportKind.STDIO,
    "http": TransportKind.HTTP,
    "streamable-http": TransportKind.HTTP,
}


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Resolved, validated runtime configuration."""

    base_url: str
    log_level: str
    transport: TransportKind
    http_host: str
    http_port: int
    metrics_port: int | None
    cache_ttl_seconds: float
    http_timeout_seconds: float
    max_articles: int
    fetch_concurrency: int
    overview_max_chars: int


class ConfigError(ValueError):
    """Raised when an environment value cannot be parsed."""


class ConfigLoader:
    """Builds a :class:`ServerConfig` from an environment mapping."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ: Mapping[str, str] = os.environ if environ is None else environ

    def load(self) -> ServerConfig:
        return ServerConfig(
            base_url=self._text(ENV_BASE_URL, constants.DEFAULT_BASE_URL),
            log_level=self._text(ENV_LOG_LEVEL, constants.DEFAULT_LOG_LEVEL).upper(),
            transport=self._transport(),
            http_host=self._text(ENV_HTTP_HOST, constants.DEFAULT_HTTP_HOST),
            http_port=self._int(ENV_HTTP_PORT, constants.DEFAULT_HTTP_PORT),
            metrics_port=self._optional_int(ENV_METRICS_PORT),
            cache_ttl_seconds=self._float(ENV_CACHE_TTL, constants.DEFAULT_CACHE_TTL_SECONDS),
            http_timeout_seconds=self._float(
                ENV_HTTP_TIMEOUT, constants.DEFAULT_HTTP_TIMEOUT_SECONDS
            ),
            max_articles=self._int(ENV_MAX_ARTICLES, constants.DEFAULT_MAX_ARTICLES),
            fetch_concurrency=self._int(ENV_FETCH_CONCURRENCY, constants.DEFAULT_FETCH_CONCURRENCY),
            overview_max_chars=self._int(
                ENV_OVERVIEW_MAX_CHARS, constants.DEFAULT_OVERVIEW_MAX_CHARS
            ),
        )

    def _text(self, name: str, default: str) -> str:
        value = self._environ.get(name, "").strip()
        return value if value else default

    def _int(self, name: str, default: int) -> int:
        raw = self._environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc

    def _optional_int(self, name: str) -> int | None:
        raw = self._environ.get(name, "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc

    def _float(self, name: str, default: float) -> float:
        raw = self._environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError as exc:
            raise ConfigError(f"{name} must be a number, got {raw!r}") from exc

    def _transport(self) -> TransportKind:
        raw = self._environ.get(ENV_TRANSPORT, "").strip().lower()
        if not raw:
            return TransportKind.STDIO
        resolved = _TRANSPORT_ALIASES.get(raw)
        if resolved is None:
            allowed = ", ".join(sorted(_TRANSPORT_ALIASES))
            raise ConfigError(f"{ENV_TRANSPORT} must be one of: {allowed}; got {raw!r}")
        return resolved
