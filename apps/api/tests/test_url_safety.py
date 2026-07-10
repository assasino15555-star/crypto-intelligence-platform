from __future__ import annotations

import pytest

from apps.api.app.core.errors import ValidationError
from apps.api.app.utils.url_safety import assert_safe_outbound_url, resolve_and_validate_host


def test_https_url_allowed(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()
    assert_safe_outbound_url("https://api.etherscan.io/api")


def test_http_url_blocked_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("REDIS_URL", "redis://x:6379/0")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "k")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    from apps.api.app.core import config as cfg

    cfg.reset_settings_cache()
    with pytest.raises(ValidationError, match="http"):
        assert_safe_outbound_url("http://api.etherscan.io/api")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "mock")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    cfg.reset_settings_cache()


def test_credentials_in_url_blocked():
    with pytest.raises(ValidationError, match="credentials"):
        assert_safe_outbound_url("https://user:pass@etherscan.io/api")


_loopback_cases = [
    "https://127.0.0.1/api",
    "https://localhost/api",
    "https://[::1]/api",
    "https://10.0.0.1/api",
    "https://192.168.1.1/api",
    "https://169.254.1.1/api",
    "https://0.0.0.0/api",
]


@pytest.mark.parametrize("url", _loopback_cases)
def test_blocked_hosts(url):
    with pytest.raises(ValidationError):
        assert_safe_outbound_url(url)


def test_metadata_endpoint_blocked():
    with pytest.raises(ValidationError):
        assert_safe_outbound_url("https://169.254.169.254/latest/meta-data/")


def test_non_http_scheme_blocked():
    with pytest.raises(ValidationError, match="scheme"):
        assert_safe_outbound_url("file:///etc/passwd")
    with pytest.raises(ValidationError, match="scheme"):
        assert_safe_outbound_url("ftp://example.com")


def test_empty_url_blocked():
    with pytest.raises(ValidationError):
        assert_safe_outbound_url("")
    with pytest.raises(ValidationError):
        assert_safe_outbound_url(None)  # type: ignore[arg-type]


def test_missing_host_blocked():
    with pytest.raises(ValidationError, match="host"):
        assert_safe_outbound_url("https:///api")


def test_dns_rebinding_blocked_for_private_ip(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.utils.url_safety.socket.getaddrinfo",
        lambda host, *args, **kwargs: [
            (0, 0, 0, "", ("10.0.0.1", 0)),
        ],
    )
    with pytest.raises(ValidationError, match="blocked ip"):
        resolve_and_validate_host("evil.example.com")


def test_dns_resolution_passes_for_public_ip(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.utils.url_safety.socket.getaddrinfo",
        lambda host, *args, **kwargs: [
            (0, 0, 0, "", ("93.184.216.34", 0)),
        ],
    )
    ips = resolve_and_validate_host("example.com")
    assert "93.184.216.34" in ips


def test_dns_failure_rejected(monkeypatch):
    import socket

    def fail(host, *args, **kwargs):
        raise socket.gaierror("dns failed")

    monkeypatch.setattr("apps.api.app.utils.url_safety.socket.getaddrinfo", fail)
    with pytest.raises(ValidationError, match="dns"):
        resolve_and_validate_host("nonexistent.invalid")


def test_ipv4_mapped_ipv6_blocked():
    with pytest.raises(ValidationError):
        assert_safe_outbound_url("https://[::ffff:127.0.0.1]/api")
