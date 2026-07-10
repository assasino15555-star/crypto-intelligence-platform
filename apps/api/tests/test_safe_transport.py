from __future__ import annotations

import pytest

from apps.api.app.core.errors import ValidationError
from apps.api.app.utils.url_safety import resolve_and_validate_host


def test_resolve_rejects_private_dns(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.utils.url_safety.socket.getaddrinfo",
        lambda host, *args, **kwargs: [(0, 0, 0, "", ("10.0.0.1", 0))],
    )
    with pytest.raises(ValidationError, match="blocked ip"):
        resolve_and_validate_host("evil.example.com")


def test_resolve_rejects_metadata_endpoint(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.utils.url_safety.socket.getaddrinfo",
        lambda host, *args, **kwargs: [(0, 0, 0, "", ("169.254.169.254", 0))],
    )
    with pytest.raises(ValidationError, match="blocked ip"):
        resolve_and_validate_host("metadata.example.com")


def test_resolve_rejects_loopback_dns(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.utils.url_safety.socket.getaddrinfo",
        lambda host, *args, **kwargs: [(0, 0, 0, "", ("127.0.0.1", 0))],
    )
    with pytest.raises(ValidationError, match="blocked ip"):
        resolve_and_validate_host("rebind.example.com")


def test_resolve_rejects_ipv6_loopback_dns(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.utils.url_safety.socket.getaddrinfo",
        lambda host, *args, **kwargs: [(0, 0, 0, "", ("::1", 0, 0, 0))],
    )
    with pytest.raises(ValidationError, match="blocked ip"):
        resolve_and_validate_host("v6loop.example.com")


def test_resolve_passes_public_dns(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.utils.url_safety.socket.getaddrinfo",
        lambda host, *args, **kwargs: [(0, 0, 0, "", ("93.184.216.34", 0))],
    )
    ips = resolve_and_validate_host("api.example.com")
    assert "93.184.216.34" in ips


def test_resolve_validates_all_a_records(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.utils.url_safety.socket.getaddrinfo",
        lambda host, *args, **kwargs: [
            (0, 0, 0, "", ("93.184.216.34", 0)),
            (0, 0, 0, "", ("10.0.0.1", 0)),
        ],
    )
    with pytest.raises(ValidationError, match="blocked ip"):
        resolve_and_validate_host("mixed.example.com")


def test_resolve_rejects_ipv4_mapped_ipv6(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.utils.url_safety.socket.getaddrinfo",
        lambda host, *args, **kwargs: [(0, 0, 0, "", ("::ffff:127.0.0.1", 0, 0, 0))],
    )
    with pytest.raises(ValidationError, match="blocked ip"):
        resolve_and_validate_host("mapped.example.com")


def test_resolve_rejects_unspecified_address(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.utils.url_safety.socket.getaddrinfo",
        lambda host, *args, **kwargs: [(0, 0, 0, "", ("0.0.0.0", 0))],
    )
    with pytest.raises(ValidationError, match="blocked ip"):
        resolve_and_validate_host("unspecified.example.com")


def test_dns_failure_rejected(monkeypatch):
    import socket

    def fail(host, *args, **kwargs):
        raise socket.gaierror("dns failed")

    monkeypatch.setattr("apps.api.app.utils.url_safety.socket.getaddrinfo", fail)
    with pytest.raises(ValidationError, match="dns"):
        resolve_and_validate_host("nonexistent.invalid")
