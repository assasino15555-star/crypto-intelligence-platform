from __future__ import annotations

import time
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
    monkeypatch.setattr(cfg.get_settings(), "session_max_lifetime_seconds", 3600)
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
    with pytest.raises(TokenError):
        verify_token("not-a-token")


def test_verify_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    monkeypatch.setattr(cfg.get_settings(), "session_max_lifetime_seconds", 3600)
    uid = uuid.uuid4()
    token, _, _ = issue_token(uid)
    parts = token.split(".")
    parts[1] = "a" * 64
    bad = ".".join(parts)
    with pytest.raises(TokenError):
        verify_token(bad)


def test_verify_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    monkeypatch.setattr(cfg.get_settings(), "session_ttl_seconds", -10)
    monkeypatch.setattr(cfg.get_settings(), "session_max_lifetime_seconds", 3600)
    uid = uuid.uuid4()
    token, _, _ = issue_token(uid)
    with pytest.raises(TokenError):
        verify_token(token)


def test_verify_rejects_token_with_different_secret(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    monkeypatch.setattr(cfg.get_settings(), "session_max_lifetime_seconds", 3600)
    uid = uuid.uuid4()
    token, _, _ = issue_token(uid)
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "y" * 40)
    with pytest.raises(TokenError):
        verify_token(token)


def test_issue_requires_secret(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "")
    with pytest.raises(TokenError):
        issue_token(uuid.uuid4())


def test_token_cannot_exceed_max_lifetime(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    monkeypatch.setattr(cfg.get_settings(), "session_ttl_seconds", 999999)
    monkeypatch.setattr(cfg.get_settings(), "session_max_lifetime_seconds", 100)
    uid = uuid.uuid4()
    token, exp, _ = issue_token(uid)
    payload = verify_token(token)
    assert payload.exp - payload.iat <= 100 + 60


def test_token_with_excessive_exp_rejected(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    monkeypatch.setattr(cfg.get_settings(), "session_max_lifetime_seconds", 100)
    import base64
    import hashlib
    import hmac
    import json

    uid = uuid.uuid4()
    iat = int(time.time())
    payload_dict = {
        "sub": str(uid),
        "iat": iat,
        "exp": iat + 999999,
        "jti": "abcdefghijklmnop",
        "rot": 0,
    }
    payload_b = json.dumps(payload_dict, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_b).rstrip(b"=").decode("ascii")
    sig = hmac.new(b"x" * 40, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    token = f"{payload_b64}.{sig}"
    with pytest.raises(TokenError):
        verify_token(token)


def test_token_with_old_iat_rejected(monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "app_secret", "x" * 40)
    monkeypatch.setattr(cfg.get_settings(), "session_max_lifetime_seconds", 100)
    import base64
    import hashlib
    import hmac
    import json

    uid = uuid.uuid4()
    iat = int(time.time()) - 999999
    payload_dict = {
        "sub": str(uid),
        "iat": iat,
        "exp": iat + 50,
        "jti": "abcdefghijklmnop",
        "rot": 0,
    }
    payload_b = json.dumps(payload_dict, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_b).rstrip(b"=").decode("ascii")
    sig = hmac.new(b"x" * 40, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    token = f"{payload_b64}.{sig}"
    with pytest.raises(TokenError):
        verify_token(token)
