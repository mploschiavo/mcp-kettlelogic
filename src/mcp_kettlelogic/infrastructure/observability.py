"""Observability: structured logging + Prometheus-style metrics.

Split into focused collaborators (registry / renderer / http exposer / logger
factory / operation scope) so no single class owns everything. Logs are emitted
to **stderr** — stdout is reserved for the MCP stdio protocol.
"""

from __future__ import annotations

import bisect
import logging
import sys
import threading
import time
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import TracebackType
from typing import Final

from mcp_kettlelogic import constants

_LabelKey = tuple[str, tuple[tuple[str, str], ...]]

# Metric names.
METRIC_OPERATIONS: Final = "mcp_operations_total"
METRIC_ERRORS: Final = "mcp_errors_total"
METRIC_HTTP_FETCHES: Final = "mcp_http_fetches_total"
METRIC_HTTP_ERRORS: Final = "mcp_http_errors_total"
METRIC_CACHE: Final = "mcp_cache_total"
METRIC_DURATION: Final = "mcp_op_duration_seconds"

# Histogram bucket upper bounds (seconds) for mcp_op_duration_seconds. Tuned for
# the sub-second tool calls this server makes; lets Grafana compute real p50/p95/p99.
DURATION_BUCKETS: Final = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

_MILLISECONDS_PER_SECOND: Final = 1000.0


class LoggerFactory:
    """Builds a stderr logger; never attaches handlers to stdout."""

    def build(self, name: str, level: str) -> logging.Logger:
        log = logging.getLogger(name)
        if not log.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter(constants.LOG_FORMAT))
            log.addHandler(handler)
        log.setLevel(level)
        log.propagate = False
        return log


class MetricsRegistry:
    """Thread-safe counters and per-operation latency aggregates."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[_LabelKey, int] = {}
        self._latency_count: dict[str, int] = {}
        self._latency_sum: dict[str, float] = {}
        # Per-operation histogram bucket counts (len(DURATION_BUCKETS) + 1 for +Inf).
        self._latency_buckets: dict[str, list[int]] = {}

    def increment(self, name: str, labels: Mapping[str, str] | None = None) -> None:
        key = self._key(name, labels or {})
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + 1

    def observe_latency(self, operation: str, seconds: float) -> None:
        with self._lock:
            self._latency_count[operation] = self._latency_count.get(operation, 0) + 1
            self._latency_sum[operation] = self._latency_sum.get(operation, 0.0) + seconds
            buckets = self._latency_buckets.setdefault(operation, [0] * (len(DURATION_BUCKETS) + 1))
            # First bound >= seconds; past all bounds falls into the +Inf bucket.
            buckets[bisect.bisect_left(DURATION_BUCKETS, seconds)] += 1

    def counters(self) -> dict[_LabelKey, int]:
        with self._lock:
            return dict(self._counters)

    def latencies(self) -> dict[str, tuple[int, float]]:
        with self._lock:
            return {
                op: (self._latency_count[op], self._latency_sum[op]) for op in self._latency_count
            }

    def latency_buckets(self) -> dict[str, list[int]]:
        with self._lock:
            return {op: list(counts) for op, counts in self._latency_buckets.items()}

    @staticmethod
    def _key(name: str, labels: Mapping[str, str]) -> _LabelKey:
        return name, tuple(sorted(labels.items()))


class PrometheusRenderer:
    """Renders a :class:`MetricsRegistry` to Prometheus text exposition format."""

    def render(self, registry: MetricsRegistry) -> str:
        lines: list[str] = []
        lines.extend(self._render_counters(registry.counters()))
        lines.extend(self._render_latencies(registry.latencies(), registry.latency_buckets()))
        return "\n".join(lines) + "\n"

    def _render_counters(self, counters: Mapping[_LabelKey, int]) -> list[str]:
        grouped: dict[str, list[tuple[tuple[tuple[str, str], ...], int]]] = {}
        for (name, labels), value in counters.items():
            grouped.setdefault(name, []).append((labels, value))
        out: list[str] = []
        for name in sorted(grouped):
            out.append(f"# TYPE {name} counter")
            for labels, value in grouped[name]:
                out.append(self._format_sample(name, labels, value))
        return out

    def _render_latencies(
        self,
        latencies: Mapping[str, tuple[int, float]],
        buckets_by_op: Mapping[str, list[int]],
    ) -> list[str]:
        out: list[str] = []
        for operation in sorted(latencies):
            count, total = latencies[operation]
            counts = buckets_by_op.get(operation, [0] * (len(DURATION_BUCKETS) + 1))
            out.append(f"# TYPE {METRIC_DURATION} histogram")
            cumulative = 0
            for bound, in_bucket in zip(DURATION_BUCKETS, counts, strict=False):
                cumulative += in_bucket
                out.append(
                    f'{METRIC_DURATION}_bucket{{op="{operation}",le="{bound}"}} {cumulative}'
                )
            cumulative += counts[len(DURATION_BUCKETS)]  # +Inf overflow
            out.append(f'{METRIC_DURATION}_bucket{{op="{operation}",le="+Inf"}} {cumulative}')
            out.append(f'{METRIC_DURATION}_sum{{op="{operation}"}} {total:.6f}')
            out.append(f'{METRIC_DURATION}_count{{op="{operation}"}} {count}')
        return out

    @staticmethod
    def _format_sample(name: str, labels: tuple[tuple[str, str], ...], value: int) -> str:
        if not labels:
            return f"{name} {value}"
        rendered = ",".join(f'{key}="{val}"' for key, val in labels)
        return f"{name}{{{rendered}}} {value}"


class MetricsHttpServer:
    """Serves GET /metrics on a background thread."""

    def __init__(self, registry: MetricsRegistry, renderer: PrometheusRenderer) -> None:
        self._registry = registry
        self._renderer = renderer
        self._http: HTTPServer | None = None

    def start(self, host: str, port: int) -> HTTPServer:
        handler = self._build_handler()
        server = HTTPServer((host, port), handler)
        self._http = server
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    def stop(self) -> None:
        if self._http is not None:
            self._http.shutdown()
            self._http = None

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        registry = self._registry
        renderer = self._renderer

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server contract
                if self.path != constants.METRICS_PATH:
                    self.send_response(constants.HTTP_NOT_FOUND)
                    self.end_headers()
                    return
                body = renderer.render(registry).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", constants.METRICS_CONTENT_TYPE)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                return None

        return _Handler


class OperationScope:
    """Async context manager that times, counts and logs one operation."""

    def __init__(self, observer: OperationObserver, operation: str) -> None:
        self._observer = observer
        self._operation = operation
        self._started = 0.0

    async def __aenter__(self) -> OperationScope:
        self._started = time.monotonic()
        self._observer.on_start(self._operation)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Returns None — the scope never suppresses the exception.
        duration = time.monotonic() - self._started
        if exc is not None:
            self._observer.on_error(self._operation, exc)
        self._observer.on_finish(self._operation, duration)


class OperationObserver:
    """Couples a logger and a registry to record operation outcomes."""

    def __init__(self, logger: logging.Logger, registry: MetricsRegistry) -> None:
        self._logger = logger
        self._registry = registry

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @property
    def registry(self) -> MetricsRegistry:
        return self._registry

    def observe(self, operation: str) -> OperationScope:
        return OperationScope(self, operation)

    def on_start(self, operation: str) -> None:
        self._registry.increment(METRIC_OPERATIONS, {"op": operation})
        self._logger.debug("op.start op=%s", operation)

    def on_error(self, operation: str, exc: BaseException) -> None:
        self._registry.increment(METRIC_ERRORS, {"op": operation, "error": type(exc).__name__})
        self._logger.warning("op.error op=%s error=%s msg=%s", operation, type(exc).__name__, exc)

    def on_finish(self, operation: str, duration_seconds: float) -> None:
        self._registry.observe_latency(operation, duration_seconds)
        self._logger.info(
            "op.done op=%s duration_ms=%.1f",
            operation,
            duration_seconds * _MILLISECONDS_PER_SECOND,
        )
