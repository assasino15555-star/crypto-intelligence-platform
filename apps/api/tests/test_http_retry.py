"""HTTP retry classification tests."""

from __future__ import annotations

import httpx
import pytest

from apps.api.app.utils.http_retry import _PERMANENT_STATUS, _RETRYABLE_STATUS, HttpRetry


def test_permanent_status_classification():
    assert {400, 401, 403, 404, 422} == _PERMANENT_STATUS


def test_retryable_status_classification():
    assert {429, 500, 502, 503, 504} == _RETRYABLE_STATUS


@pytest.mark.asyncio
async def test_retry_does_not_retry_permanent_4xx(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        retry = HttpRetry(max_retries=3, base_backoff=0.001)
        from apps.api.app.core.errors import ProviderPermanentError

        with pytest.raises(ProviderPermanentError):
            await retry.request(client, "GET", "https://example.com/x")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retry_retries_429_then_succeeds(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        retry = HttpRetry(max_retries=4, base_backoff=0.001)
        resp = await retry.request(client, "GET", "https://example.com/x")
        assert resp.status_code == 200
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_retries_transport_error_then_succeeds(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        retry = HttpRetry(max_retries=4, base_backoff=0.001)
        resp = await retry.request(client, "GET", "https://example.com/x")
        assert resp.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_retry_gives_up_after_max(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        retry = HttpRetry(max_retries=2, base_backoff=0.001)
        from apps.api.app.core.errors import ProviderRetryableError

        with pytest.raises(ProviderRetryableError):
            await retry.request(client, "GET", "https://example.com/x")
    assert calls["n"] == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_retry_respects_retry_after_header(monkeypatch):
    """429 with Retry-After: 2 should sleep ~2s, not the exponential backoff."""

    monkeypatch.setenv("ENVIRONMENT", "development")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()

    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("apps.api.app.utils.http_retry.asyncio.sleep", fake_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "2"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        retry = HttpRetry(max_retries=1, base_backoff=0.001)
        from apps.api.app.core.errors import ProviderRetryableError

        with pytest.raises(ProviderRetryableError):
            await retry.request(client, "GET", "https://example.com/x")
    # The single retry should have slept ~2.0s (Retry-After), not the small backoff
    assert sleep_calls and any(abs(s - 2.0) < 0.1 for s in sleep_calls)
