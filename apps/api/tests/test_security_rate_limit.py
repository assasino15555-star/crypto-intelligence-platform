from __future__ import annotations

from apps.api.app.utils.rate_limit import (
    InMemoryRateLimiter,
    LimitSpec,
    trusted_client_ip,
)


class FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None, client_host: str = ""):
        self.headers = headers or {}
        self.client = type("FakeClient", (), {"host": client_host})() if client_host else None


def test_xff_not_trusted_without_proxy_config(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXIES", "")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()
    req = FakeRequest(
        headers={"X-Forwarded-For": "1.2.3.4"},
        client_host="127.0.0.1",
    )
    ip = trusted_client_ip(req)
    assert ip == "127.0.0.1"


def test_xff_trusted_when_from_proxy(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXIES", "127.0.0.1")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()
    req = FakeRequest(
        headers={"X-Forwarded-For": "1.2.3.4"},
        client_host="127.0.0.1",
    )
    ip = trusted_client_ip(req)
    assert ip == "1.2.3.4"


def test_xff_not_trusted_from_non_proxy(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXIES", "10.0.0.1")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()
    req = FakeRequest(
        headers={"X-Forwarded-For": "1.2.3.4"},
        client_host="127.0.0.1",
    )
    ip = trusted_client_ip(req)
    assert ip == "127.0.0.1"


def test_spoofed_xff_cannot_bypass_rate_limit(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXIES", "")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()
    spec = LimitSpec(capacity=1, window_seconds=60)
    limiter = InMemoryRateLimiter(spec)

    req1 = FakeRequest(headers={"X-Forwarded-For": "1.1.1.1"}, client_host="10.0.0.1")
    req2 = FakeRequest(headers={"X-Forwarded-For": "2.2.2.2"}, client_host="10.0.0.1")

    ip1 = trusted_client_ip(req1)
    ip2 = trusted_client_ip(req2)
    assert ip1 == ip2

    import asyncio

    loop = asyncio.new_event_loop()
    loop.run_until_complete(limiter.check(f"test:{ip1}"))

    from apps.api.app.core.errors import RateLimitError

    with __import__("pytest").raises(RateLimitError):
        loop.run_until_complete(limiter.check(f"test:{ip2}"))
    loop.close()
