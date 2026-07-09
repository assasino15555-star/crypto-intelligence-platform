"""Bounded in-process rate limiter.

Per-IP token bucket. Suitable for single-instance deployments. For
multi-instance production deployments, swap this for a Redis-backed limiter
that shares state across instances (the public API is unchanged).

The limiter is intentionally minimal: a sliding-window counter per key with
configurable capacity and window. Memory growth is bounded by evicting the
oldest keys when the table exceeds `MAX_KEYS`.
"""

from __future__ import annotations

import time
from threading import Lock

from ..core.errors import RateLimitError

MAX_KEYS = 10_000


class _Bucket:
    __slots__ = ("count", "reset_at")

    def __init__(self, capacity: int, window: float) -> None:
        self.count = capacity
        self.reset_at = time.monotonic() + window


class RateLimiter:
    """Sliding-window per-key counter."""

    def __init__(self, *, capacity: int, window: float) -> None:
        self.capacity = capacity
        self.window = window
        self._buckets: dict[str, _Bucket] = {}
        self._lock = Lock()

    def consume(self, key: str) -> None:
        """Raise RateLimitError if `key` has exceeded capacity within window."""
        with self._lock:
            if len(self._buckets) > MAX_KEYS:
                self._evict()
            b = self._buckets.get(key)
            now = time.monotonic()
            if b is None or b.reset_at <= now:
                b = _Bucket(self.capacity, self.window)
                self._buckets[key] = b
            if b.count <= 0:
                # Compute how long until reset for the client
                wait = max(0.0, b.reset_at - now)
                raise RateLimitError(f"rate limited; retry in {wait:.1f}s")
            b.count -= 1

    def _evict(self) -> None:
        now = time.monotonic()
        expired = [k for k, b in self._buckets.items() if b.reset_at <= now]
        for k in expired:
            self._buckets.pop(k, None)
        if len(self._buckets) > MAX_KEYS:
            # Drop oldest 25% — bounded memory, simple policy
            sorted_keys = sorted(self._buckets.items(), key=lambda kv: kv[1].reset_at)
            for k, _ in sorted_keys[: len(sorted_keys) // 4]:
                self._buckets.pop(k, None)


# Pre-configured limiters for sensitive endpoints.
LOGIN_LIMITER = RateLimiter(capacity=10, window=60.0)
AI_LIMITER = RateLimiter(capacity=20, window=60.0)
SNAPSHOT_LIMITER = RateLimiter(capacity=10, window=60.0)


def client_key(request: object) -> str:
    """Extract a stable client key from a request.

    Prefers X-Forwarded-For (first hop), falls back to client host, then to
    a fixed string if neither is available (e.g. in tests).
    """
    headers = getattr(request, "headers", {}) or {}
    fwd: str | None = None
    if hasattr(headers, "get"):
        v = headers.get("X-Forwarded-For")
        if isinstance(v, str):
            fwd = v
    if fwd:
        return fwd.split(",")[0].strip()
    client = getattr(request, "client", None)
    if client is not None:
        host = getattr(client, "host", None)
        if isinstance(host, str) and host:
            return host
    return "unknown"
