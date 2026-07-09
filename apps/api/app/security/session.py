"""Session token issuance and verification.

Sessions are signed (HMAC-SHA256) random tokens. The server stores only the
hash of the token, never the token itself. Tokens are short-lived.

Format: <payload_b64>.<sig_hex>
Payload contains: sub (user_id), iat (issued at), exp (expires at).

Verification:
  * Recompute signature with APP_SECRET.
  * Compare in constant time.
  * Reject expired tokens.
  * Look up the hashed token in `wallet_sessions` and ensure not revoked.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass

from ..core.config import get_settings


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenPayload:
    sub: str
    iat: int
    exp: int
    jti: str


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(user_id: uuid.UUID) -> tuple[str, int, str]:
    """Issue a signed session token.

    Returns (token, expires_at_unix, token_hash) — the caller persists the hash.
    """
    settings = get_settings()
    if not settings.app_secret:
        raise TokenError("APP_SECRET not configured")
    iat = int(time.time())
    exp = iat + settings.session_ttl_seconds
    jti = secrets.token_urlsafe(16)
    payload = {"sub": str(user_id), "iat": iat, "exp": exp, "jti": jti}
    payload_b = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64(payload_b)
    sig = hmac.new(
        settings.app_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    token = f"{payload_b64}.{sig}"
    token_hash = hash_token(token)
    return token, exp, token_hash


def verify_token(token: str) -> TokenPayload:
    """Verify token signature and expiration (NOT DB session validity)."""
    if not token or "." not in token:
        raise TokenError("malformed token")
    parts = token.split(".")
    if len(parts) != 2:
        raise TokenError("malformed token")
    payload_b64, sig = parts
    settings = get_settings()
    if not settings.app_secret:
        raise TokenError("APP_SECRET not configured")
    expected = hmac.new(
        settings.app_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise TokenError("bad signature")
    try:
        payload_b = _unb64(payload_b64)
        payload = json.loads(payload_b)
    except (ValueError, TypeError) as exc:
        raise TokenError("malformed payload") from exc
    try:
        sub = payload["sub"]
        iat = int(payload["iat"])
        exp = int(payload["exp"])
        jti = payload["jti"]
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("incomplete payload") from exc
    now = int(time.time())
    if exp <= now:
        raise TokenError("expired")
    if iat > now + 60:
        raise TokenError("issued in future")
    return TokenPayload(sub=sub, iat=iat, exp=exp, jti=jti)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
