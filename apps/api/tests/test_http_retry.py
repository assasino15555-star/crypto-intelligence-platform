from __future__ import annotations

import httpx
import pytest

from apps.api.app.core.errors import (
    ProviderPermanentError,
    ProviderRetryableError,
)
from apps.api.app.utils.http_retry import (
    _PERMANENT_STATUS,
    _RETRYABLE_STATUS,
    HttpRetry,
    assert_json_content_type,
)


def test_permanent_status_classification():
    assert {400, 401, 403, 404, 422} == _PERMANENT_STATUS


def test_retryable_status_classification():
    assert {429, 500, 502, 503, 504} == _RETRYABLE_STATUS


@pytest.mark.asyncio
async def test_retry_does_not_retry_permanent_4xx(monkeypatch):
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        retry = HttpRetry(max_retries=3, base_backoff=0.001, max_response_bytes=1024 * 1024)
        with pytest.raises(ProviderPermanentError):
            await retry.request(client, "GET", "https://example.com/x")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retry_retries_429_then_succeeds(monkeypatch):
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
        retry = HttpRetry(max_retries=4, base_backoff=0.001, max_response_bytes=1024 * 1024)
        resp = await retry.request(client, "GET", "https://example.com/x")
        assert resp.status_code == 200
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_retries_transport_error(monkeypatch):
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
        retry = HttpRetry(max_retries=4, base_backoff=0.001, max_response_bytes=1024 * 1024)
        resp = await retry.request(client, "GET", "https://example.com/x")
        assert resp.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_retry_gives_up_after_max(monkeypatch):
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        retry = HttpRetry(max_retries=2, base_backoff=0.001, max_response_bytes=1024 * 1024)
        with pytest.raises(ProviderRetryableError):
            await retry.request(client, "GET", "https://example.com/x")
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_after_negative_value_handled(monkeypatch):
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "-5"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        retry = HttpRetry(max_retries=1, base_backoff=0.001, max_response_bytes=1024 * 1024)
        with pytest.raises(ProviderRetryableError):
            await retry.request(client, "GET", "https://example.com/x")


@pytest.mark.asyncio
async def test_oversized_response_rejected(monkeypatch):
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()

    big_body = "x" * 100

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=big_body,
            headers={"Content-Length": "100"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        retry = HttpRetry(max_retries=0, max_response_bytes=50)
        with pytest.raises(ProviderPermanentError, match="too large"):
            await retry.request(client, "GET", "https://example.com/x")


def test_assert_json_content_type_passes():
    resp = httpx.Response(200, headers={"Content-Type": "application/json"})
    assert_json_content_type(resp)


def test_assert_json_content_type_rejects_html():
    resp = httpx.Response(200, headers={"Content-Type": "text/html"})
    with pytest.raises(ProviderPermanentError):
        assert_json_content_type(resp)
