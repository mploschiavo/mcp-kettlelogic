"""Observability tests: registry, renderer, metrics endpoint, logger, scopes."""

from __future__ import annotations

import httpx
import pytest

from mcp_kettlelogic.infrastructure import observability
from mcp_kettlelogic.infrastructure.observability import (
    LoggerFactory,
    MetricsHttpServer,
    MetricsRegistry,
    OperationObserver,
    PrometheusRenderer,
)


def test_registry_and_renderer_roundtrip() -> None:
    registry = MetricsRegistry()
    registry.increment(observability.METRIC_OPERATIONS, {"op": "x"})
    registry.increment(observability.METRIC_OPERATIONS, {"op": "x"})
    registry.increment("plain_counter")
    registry.observe_latency("x", 0.05)
    out = PrometheusRenderer().render(registry)
    assert 'mcp_operations_total{op="x"} 2' in out
    assert "plain_counter 1" in out
    assert 'mcp_op_duration_seconds_count{op="x"} 1' in out
    assert "# TYPE" in out


def test_logger_factory_is_idempotent() -> None:
    factory = LoggerFactory()
    first = factory.build("dup-logger", "INFO")
    second = factory.build("dup-logger", "INFO")
    assert first is second
    assert len(first.handlers) == 1  # handler not attached twice


def test_metrics_http_server_serves_and_404s() -> None:
    server = MetricsHttpServer(MetricsRegistry(), PrometheusRenderer())
    http = server.start("127.0.0.1", 0)
    try:
        port = http.server_address[1]
        ok = httpx.get(f"http://127.0.0.1:{port}/metrics")
        assert ok.status_code == 200
        assert "# TYPE" in ok.text or ok.text.strip() == ""
        missing = httpx.get(f"http://127.0.0.1:{port}/nope")
        assert missing.status_code == 404
    finally:
        server.stop()


async def test_operation_scope_records_success() -> None:
    registry = MetricsRegistry()
    observer = OperationObserver(LoggerFactory().build("obs-ok", "WARNING"), registry)
    async with observer.observe("job"):
        pass
    counters = registry.counters()
    assert (observability.METRIC_OPERATIONS, (("op", "job"),)) in counters


async def test_operation_scope_records_error() -> None:
    registry = MetricsRegistry()
    observer = OperationObserver(LoggerFactory().build("obs-err", "WARNING"), registry)
    with pytest.raises(ValueError):
        async with observer.observe("job"):
            raise ValueError("boom")
    errored = [
        value
        for (name, labels), value in registry.counters().items()
        if name == observability.METRIC_ERRORS and ("op", "job") in labels
    ]
    assert sum(errored) == 1
