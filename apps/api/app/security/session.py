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
    rot: int


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(user_id: uuid.UUID, rotation: int = 0) -> tuple[str, int, str]:
    settings = get_settings()
    if not settings.app_secret:
        raise TokenError("malformed")
    iat = int(time.time())
    exp = iat + settings.session_ttl_seconds
    max_exp = iat + settings.session_max_lifetime_seconds
    if exp > max_exp:
        exp = max_exp
    jti = secrets.token_urlsafe(16)
    payload = {
        "sub": str(user_id),
        "iat": iat,
        "exp": exp,
        "jti": jti,
        "rot": rotation,
    }
    payload_b = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64(payload_b)
    sig = hmac.new(
        settings.app_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    token = f"{payload_b64}.{sig}"
    token_hash = hash_token(token)
    return token, exp, token_hash


def verify_token(token: str) -> TokenPayload:
    if not token or "." not in token:
        raise TokenError("malformed")
    parts = token.split(".")
    if len(parts) != 2:
        raise TokenError("malformed")
    payload_b64, sig = parts
    settings = get_settings()
    if not settings.app_secret:
        raise TokenError("malformed")
    expected = hmac.new(
        settings.app_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise TokenError("malformed")
    try:
        payload_b = _unb64(payload_b64)
        payload = json.loads(payload_b)
    except (ValueError, TypeError) as exc:
        raise TokenError("malformed") from exc
    try:
        sub = payload["sub"]
        iat = int(payload["iat"])
        exp = int(payload["exp"])
        jti = payload["jti"]
        rot = int(payload.get("rot", 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("malformed") from exc
    if not isinstance(jti, str) or len(jti) < 8:
        raise TokenError("malformed")
    now = int(time.time())
    if exp <= now:
        raise TokenError("expired")
    if iat > now + 60:
        raise TokenError("malformed")
    max_lifetime = settings.session_max_lifetime_seconds
    if exp - iat > max_lifetime + 60:
        raise TokenError("malformed")
    if now - iat > max_lifetime:
        raise TokenError("expired")
    return TokenPayload(sub=sub, iat=iat, exp=exp, jti=jti, rot=rot)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
