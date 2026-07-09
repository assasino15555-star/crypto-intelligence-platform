"""Session token issuance and verification tests."""

from __future__ import annotations

import uuid

import pytest

from apps.api.app.core import config as cfg
from apps.api.app.security.session import (
    TokenError,
    hash_token,
    issue_token,
    verify_token,
)


def test_issue_and_verify_roundtrip(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    monkeypatch.setattr(cfg.get_settings(), "session_ttl_seconds", 60)
    uid = uuid.uuid4()
    token, exp, thash = issue_token(uid)
    assert isinstance(token, str)
    assert "." in token
    assert hash_token(token) == thash
    payload = verify_token(token)
    assert payload.sub == str(uid)
    assert payload.exp > payload.iat


def test_verify_rejects_malformed_token(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    with pytest.raises(TokenError, match="malformed"):
        verify_token("not-a-token")


def test_verify_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    uid = uuid.uuid4()
    token, _, _ = issue_token(uid)
    # Tamper with the signature portion
    parts = token.split(".")
    parts[1] = "a" * 64
    bad = ".".join(parts)
    with pytest.raises(TokenError, match="bad signature"):
        verify_token(bad)


def test_verify_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    monkeypatch.setattr(cfg.get_settings(), "session_ttl_seconds", -10)
    uid = uuid.uuid4()
    token, _, _ = issue_token(uid)
    with pytest.raises(TokenError, match="expired"):
        verify_token(token)


def test_verify_rejects_token_with_different_secret(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    uid = uuid.uuid4()
    token, _, _ = issue_token(uid)
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "y" * 40)
    with pytest.raises(TokenError, match="bad signature"):
        verify_token(token)


def test_issue_requires_secret(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "")
    with pytest.raises(TokenError, match="APP_SECRET"):
        issue_token(uuid.uuid4())
