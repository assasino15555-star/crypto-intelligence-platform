"""Rate limiter tests."""

from __future__ import annotations

import pytest

from apps.api.app.core.errors import RateLimitError
from apps.api.app.utils.rate_limit import RateLimiter


def test_consume_under_capacity_succeeds():
    rl = RateLimiter(capacity=3, window=60.0)
    rl.consume("a")
    rl.consume("a")
    rl.consume("a")


def test_consume_over_capacity_raises():
    rl = RateLimiter(capacity=2, window=60.0)
    rl.consume("a")
    rl.consume("a")
    with pytest.raises(RateLimitError):
        rl.consume("a")


def test_different_keys_are_independent():
    rl = RateLimiter(capacity=1, window=60.0)
    rl.consume("a")
    rl.consume("b")  # different key, should not be limited


def test_window_reset(monkeypatch):
    rl = RateLimiter(capacity=1, window=0.05)
    rl.consume("a")
    with pytest.raises(RateLimitError):
        rl.consume("a")
    # After window passes, capacity resets
    import time

    time.sleep(0.06)
    rl.consume("a")


def test_eviction_keeps_memory_bounded():
    rl = RateLimiter(capacity=1, window=60.0)
    rl._buckets.clear()
    # Force MAX_KEYS threshold
    for i in range(100):
        rl.consume(f"k{i}")
    assert len(rl._buckets) <= 100
    # Trigger eviction by exceeding MAX_KEYS via direct injection
    rl._buckets = {
        f"k{i}": rl._buckets.get("k0", RateLimiter(capacity=1, window=1.0)) for i in range(20_000)
    }
    rl.consume("trigger")
    assert len(rl._buckets) <= 20_000  # evicted down
