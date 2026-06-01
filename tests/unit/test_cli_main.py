"""Composition-root tests for ServerApplication."""

from __future__ import annotations

from mcp_kettlelogic.cli.main import ServerApplication
from mcp_kettlelogic.config import ConfigLoader


def test_from_config_builds_application() -> None:
    config = ConfigLoader({"KETTLELOGIC_BASE_URL": "https://x.test"}).load()
    app = ServerApplication.from_config(config)
    assert isinstance(app, ServerApplication)


def test_start_metrics_noop_without_port() -> None:
    config = ConfigLoader({}).load()
    assert config.metrics_port is None
    app = ServerApplication.from_config(config)
    app.start_metrics()  # no-op, must not raise
    app.stop()


def test_start_and_stop_metrics_endpoint() -> None:
    config = ConfigLoader({"KETTLELOGIC_METRICS_PORT": "0"}).load()
    assert config.metrics_port == 0
    app = ServerApplication.from_config(config)
    app.start_metrics()
    app.stop()
