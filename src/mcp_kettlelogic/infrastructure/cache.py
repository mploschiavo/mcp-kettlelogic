"""A minimal in-memory TTL cache."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

Clock = Callable[[], float]


@dataclass(frozen=True, slots=True)
class _Entry(Generic[T]):
    value: T
    stored_at: float


class TtlCache(Generic[T]):
    """Time-bounded cache. The clock is injectable for deterministic tests."""

    def __init__(self, ttl_seconds: float, clock: Clock = time.monotonic) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, _Entry[T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if (self._clock() - entry.stored_at) >= self._ttl_seconds:
            del self._entries[key]
            return None
        return entry.value

    def set(self, key: str, value: T) -> None:
        self._entries[key] = _Entry(value=value, stored_at=self._clock())
