from __future__ import annotations

import asyncio
import time

import pytest

from apps.api.app.core.errors import RateLimitError
from apps.api.app.utils.rate_limit import InMemoryRateLimiter, LimitSpec


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_under_capacity_succeeds():
    rl = InMemoryRateLimiter(LimitSpec(capacity=3, window_seconds=60))
    _run(rl.check("a"))
    _run(rl.check("a"))
    _run(rl.check("a"))


def test_over_capacity_raises():
    rl = InMemoryRateLimiter(LimitSpec(capacity=2, window_seconds=60))
    _run(rl.check("a"))
    _run(rl.check("a"))
    with pytest.raises(RateLimitError):
        _run(rl.check("a"))


def test_different_keys_are_independent():
    rl = InMemoryRateLimiter(LimitSpec(capacity=1, window_seconds=60))
    _run(rl.check("a"))
    _run(rl.check("b"))


def test_window_reset():
    rl = InMemoryRateLimiter(LimitSpec(capacity=1, window_seconds=0.05))
    _run(rl.check("a"))
    with pytest.raises(RateLimitError):
        _run(rl.check("a"))
    time.sleep(0.06)
    _run(rl.check("a"))


def test_eviction_keeps_memory_bounded():
    rl = InMemoryRateLimiter(LimitSpec(capacity=1, window_seconds=60))
    for i in range(100):
        _run(rl.check(f"k{i}"))
    assert len(rl._timestamps) <= 100
    rl._timestamps = {f"k{i}": [0.0] for i in range(20_000)}
    _run(rl.check("trigger"))
    assert len(rl._timestamps) <= 20_000


def test_retry_after_returned_on_limit():
    rl = InMemoryRateLimiter(LimitSpec(capacity=1, window_seconds=60))
    _run(rl.check("k"))
    with pytest.raises(RateLimitError) as exc_info:
        _run(rl.check("k"))
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers
    assert int(exc_info.value.headers["Retry-After"]) >= 1


def test_concurrent_burst_counts_every_request():
    rl = InMemoryRateLimiter(LimitSpec(capacity=5, window_seconds=60))
    allowed = 0
    rejected = 0
    for _ in range(10):
        try:
            _run(rl.check("burst"))
            allowed += 1
        except RateLimitError:
            rejected += 1
    assert allowed == 5
    assert rejected == 5
