"""Config layer tests."""

from __future__ import annotations

import pytest

from mcp_kettlelogic import constants
from mcp_kettlelogic.config import ConfigError, ConfigLoader
from mcp_kettlelogic.domain.enums import TransportKind


def test_defaults_on_empty_environment() -> None:
    config = ConfigLoader({}).load()
    assert config.base_url == constants.DEFAULT_BASE_URL
    assert config.transport is TransportKind.STDIO
    assert config.metrics_port is None
    assert config.log_level == constants.DEFAULT_LOG_LEVEL
    assert config.max_articles == constants.DEFAULT_MAX_ARTICLES


def test_overrides_are_parsed() -> None:
    config = ConfigLoader(
        {
            "KETTLELOGIC_BASE_URL": "https://my.site",
            "KETTLELOGIC_LOG_LEVEL": "debug",
            "KETTLELOGIC_METRICS_PORT": "9464",
            "KETTLELOGIC_TRANSPORT": "http",
            "KETTLELOGIC_HTTP_PORT": "9000",
            "KETTLELOGIC_CACHE_TTL_SECONDS": "30",
            "KETTLELOGIC_MAX_ARTICLES": "10",
        }
    ).load()
    assert config.base_url == "https://my.site"
    assert config.log_level == "DEBUG"
    assert config.metrics_port == 9464
    assert config.transport is TransportKind.HTTP
    assert config.http_port == 9000
    assert config.cache_ttl_seconds == 30.0
    assert config.max_articles == 10


@pytest.mark.parametrize("alias", ["stdio", "http", "streamable-http"])
def test_transport_aliases(alias: str) -> None:
    config = ConfigLoader({"KETTLELOGIC_TRANSPORT": alias}).load()
    assert config.transport in (TransportKind.STDIO, TransportKind.HTTP)


def test_invalid_transport_raises() -> None:
    with pytest.raises(ConfigError):
        ConfigLoader({"KETTLELOGIC_TRANSPORT": "carrier-pigeon"}).load()


def test_invalid_int_raises() -> None:
    with pytest.raises(ConfigError):
        ConfigLoader({"KETTLELOGIC_MAX_ARTICLES": "lots"}).load()


def test_invalid_optional_int_raises() -> None:
    with pytest.raises(ConfigError):
        ConfigLoader({"KETTLELOGIC_METRICS_PORT": "soon"}).load()


def test_invalid_float_raises() -> None:
    with pytest.raises(ConfigError):
        ConfigLoader({"KETTLELOGIC_HTTP_TIMEOUT_SECONDS": "fast"}).load()
