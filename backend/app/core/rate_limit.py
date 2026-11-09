# backend/app/core/rate_limit.py
"""Small in-process rate limiter (sliding-window log, in memory).

Assumes ONE worker process: counters live in this process's memory, so with
several workers (or several hosts) each one enforces its own copy of every
limit. Deploy with a single uvicorn worker, or replace this module with a shared
store (e.g. Redis) before scaling out.

Rules come from settings as "<count>/<seconds>" strings (RATE_LIMIT_<NAME>);
"off", "0" or "" disables a rule and RATE_LIMIT_ENABLED=false disables all of
them. Settings are read on every call so tests can toggle them at runtime.
"""

import math
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Optional

from fastapi import Depends, Request

from app.core.config import settings
from app.core.errors import api_error


@dataclass(frozen=True)
class Rule:
    limit: int
    window_seconds: float


@lru_cache(maxsize=64)
def parse_rule(text: str | None) -> Optional[Rule]:
    """'10/60' -> Rule(10, 60.0); 'off' / '0' / '' / None -> None (disabled)."""
    if text is None:
        return None
    text = text.strip().lower()
    if text in ("", "0", "off", "none", "disabled"):
        return None
    try:
        count, _, seconds = text.partition("/")
        limit, window = int(count), float(seconds)
    except ValueError:
        raise ValueError(f"Invalid rate limit rule {text!r}; expected '<count>/<seconds>'") from None
    if limit <= 0 or window <= 0:
        return None
    return Rule(limit, window)


class RateLimiter:
    """Sliding-window log per (bucket, key). Thread-safe; bounded number of keys."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, max_keys: int = 50_000):
        self._clock = clock
        self._max_keys = max_keys
        self._hits: "OrderedDict[tuple[str, str], deque[float]]" = OrderedDict()
        self._lock = threading.Lock()

    def hit(self, bucket: str, key: str, rule: Rule) -> Optional[float]:
        """Record one request. Returns None if allowed, else seconds until a slot frees up."""
        now = self._clock()
        cutoff = now - rule.window_seconds
        with self._lock:
            entry = self._hits.get((bucket, key))
            if entry is None:
                entry = deque()
                self._hits[(bucket, key)] = entry
            else:
                self._hits.move_to_end((bucket, key))
            while entry and entry[0] <= cutoff:
                entry.popleft()
            if len(entry) >= rule.limit:
                return max(entry[0] + rule.window_seconds - now, 0.0)
            entry.append(now)
            self._evict_if_needed()
            return None

    def _evict_if_needed(self) -> None:
        # Least recently used keys go first; their windows are the most likely to be over.
        while len(self._hits) > self._max_keys:
            self._hits.popitem(last=False)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def too_many_requests(retry_after: float):
    seconds = max(1, math.ceil(retry_after))
    return api_error(
        429,
        "too_many_requests",
        f"Too many requests. Try again in {seconds} seconds.",
        headers={"Retry-After": str(seconds)},
        retry_after_seconds=seconds,
    )


def enforce(name: str, key: str) -> None:
    """Count one request against rule RATE_LIMIT_<NAME> for ``key``; raise 429 when over."""
    if not settings.RATE_LIMIT_ENABLED:
        return
    rule = parse_rule(getattr(settings, f"RATE_LIMIT_{name.upper()}", None))
    if rule is None:
        return
    retry_after = limiter.hit(name, key, rule)
    if retry_after is not None:
        raise too_many_requests(retry_after)


def client_ip(request: Request) -> str:
    """The caller's address. X-Forwarded-For is trusted only when TRUSTED_PROXY is on.

    With TRUSTED_PROXY_HOPS proxies in front of the app, each appending the address it
    saw, the client address is that many entries from the right; entries further left
    are client-supplied and can be forged.
    """
    if settings.TRUSTED_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            hops = max(1, settings.TRUSTED_PROXY_HOPS)
            return parts[-hops] if len(parts) >= hops else parts[0]
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def limit_by_ip(name: str):
    """Dependency: apply rule ``name`` per client IP."""

    def dependency(request: Request) -> None:
        enforce(name, client_ip(request))

    dependency.__name__ = f"rate_limit_{name}"
    return dependency


def limit_by_user(name: str):
    """Dependency: apply rule ``name`` per authenticated user (runs after authentication)."""
    from app.services import auth_service  # local import: auth_service must not import this module

    def dependency(current_user=Depends(auth_service.get_current_user)) -> None:
        enforce(name, f"user:{current_user.id}")

    dependency.__name__ = f"rate_limit_{name}"
    return dependency


class Cooldown:
    """Per-key minimum interval (e.g. one verification email per address per minute)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, max_keys: int = 50_000):
        self._clock = clock
        self._max_keys = max_keys
        self._until: "OrderedDict[str, float]" = OrderedDict()
        self._lock = threading.Lock()

    def remaining(self, key: str) -> float:
        with self._lock:
            until = self._until.get(key)
            if until is None:
                return 0.0
            left = until - self._clock()
            if left <= 0:
                self._until.pop(key, None)
                return 0.0
            return left

    def start(self, key: str, seconds: float) -> None:
        with self._lock:
            self._start_locked(key, seconds)

    def try_start(self, key: str, seconds: float) -> float:
        """Atomically start the cooldown if none is running. Returns 0 if started, else seconds left."""
        with self._lock:
            until = self._until.get(key)
            now = self._clock()
            if until is not None and until > now:
                return until - now
            self._start_locked(key, seconds)
            return 0.0

    def clear(self, key: str) -> None:
        with self._lock:
            self._until.pop(key, None)

    def _start_locked(self, key: str, seconds: float) -> None:
        self._until[key] = self._clock() + seconds
        self._until.move_to_end(key)
        while len(self._until) > self._max_keys:
            self._until.popitem(last=False)

    def reset(self) -> None:
        with self._lock:
            self._until.clear()


email_cooldown = Cooldown()


def reset_all() -> None:
    """Forget every counter and cooldown (tests)."""
    limiter.reset()
    email_cooldown.reset()
