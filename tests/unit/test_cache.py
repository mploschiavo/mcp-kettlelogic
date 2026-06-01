"""TtlCache tests with an injected clock."""

from __future__ import annotations

from mcp_kettlelogic.infrastructure.cache import TtlCache


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_miss_then_hit() -> None:
    cache: TtlCache[str] = TtlCache(ttl_seconds=10.0, clock=_FakeClock())
    assert cache.get("k") is None
    cache.set("k", "v")
    assert cache.get("k") == "v"


def test_entry_expires() -> None:
    clock = _FakeClock()
    cache: TtlCache[str] = TtlCache(ttl_seconds=10.0, clock=clock)
    cache.set("k", "v")
    clock.now = 9.0
    assert cache.get("k") == "v"
    clock.now = 10.0
    assert cache.get("k") is None
    assert cache.get("k") is None  # second miss after eviction
