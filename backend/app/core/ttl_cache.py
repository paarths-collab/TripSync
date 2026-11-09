# backend/app/core/ttl_cache.py
"""Bounded in-memory TTL cache (LRU eviction), per process."""

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Hashable

MISSING = object()


class TTLCache:
    def __init__(self, max_entries: int = 1000, clock: Callable[[], float] = time.monotonic):
        self._max_entries = max(1, max_entries)
        self._clock = clock
        self._data: "OrderedDict[Hashable, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any:
        """The cached value, or MISSING when absent or expired."""
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return MISSING
            expires_at, value = item
            if expires_at <= self._clock():
                del self._data[key]
                return MISSING
            self._data.move_to_end(key)
            return value

    def set(self, key: Hashable, value: Any, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        with self._lock:
            self._data[key] = (self._clock() + ttl_seconds, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
