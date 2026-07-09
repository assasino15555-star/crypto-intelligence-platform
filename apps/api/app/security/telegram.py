"""Telegram Mini App initData verification.

Reference: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Algorithm:
  1. Parse the initData query string into key=value pairs.
  2. Pop `hash` and `sign` (legacy).
  3. Build the data-check string by sorting remaining keys alphabetically
     and joining as "key=value\\n".
  4. Compute secret_key = HMAC-SHA256(key="WebAppData", msg=bot_token).
  5. Compute hash = HMAC-SHA256(key=secret_key, msg=data_check_string).
  6. Compare with the received `hash` using constant-time comparison.

Auth age:
  * The `auth_date` field is parsed as a unix timestamp (UTC).
  * Reject if (now - auth_date) > initdata_max_age_seconds.

Constant-time comparison uses hmac.compare_digest.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

from ..core.config import get_settings


class InitDataError(Exception):
    """Raised when initData fails validation."""


@dataclass(frozen=True)
class TelegramUser:
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_premium: bool = False
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class VerifiedInitData:
    user: TelegramUser
    auth_date: int
    query_id: str | None
    raw: dict[str, str]


def _extract_user(user_raw: str) -> TelegramUser:
    import json

    try:
        data = json.loads(user_raw)
    except (ValueError, TypeError) as exc:
        raise InitDataError("malformed user json") from exc
    if not isinstance(data, dict):
        raise InitDataError("user is not an object")
    if "id" not in data:
        raise InitDataError("missing user id")
    uid = data["id"]
    if not isinstance(uid, int) or uid <= 0:
        raise InitDataError("invalid user id")
    return TelegramUser(
        id=uid,
        username=data.get("username"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        language_code=data.get("language_code"),
        is_premium=bool(data.get("is_premium", False)),
        raw=data,
    )


def verify_init_data(init_data: str, *, bot_token: str | None = None) -> VerifiedInitData:
    """Validate Telegram Mini App initData and return parsed user.

    Raises InitDataError on any failure (malformed, bad signature, stale auth,
    missing fields). Never returns a partial result.
    """
    if not init_data or not isinstance(init_data, str):
        raise InitDataError("empty init_data")

    settings = get_settings()
    token = bot_token if bot_token is not None else settings.telegram_bot_token
    if not token:
        raise InitDataError("bot token not configured")

    # parse as a query string
    pairs = parse_qsl(init_data, keep_blank_values=True)
    fields: dict[str, str] = {}
    for k, v in pairs:
        fields[k] = v

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise InitDataError("missing hash")

    if "user" not in fields:
        raise InitDataError("missing user field")

    auth_date_raw = fields.get("auth_date")
    if not auth_date_raw:
        raise InitDataError("missing auth_date")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise InitDataError("auth_date not integer") from exc

    # Enforce max age
    now = int(time.time())
    max_age = settings.initdata_max_age_seconds
    if now - auth_date > max_age:
        raise InitDataError("auth_date too old")
    if auth_date - now > 60:
        # small clock skew tolerance; reject future auth_dates
        raise InitDataError("auth_date in future")

    # Build data-check string (sorted keys)
    sorted_keys = sorted(fields.keys())
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted_keys)

    # Compute secret key
    secret = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    computed = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    # Constant-time comparison
    if not hmac.compare_digest(computed, received_hash):
        raise InitDataError("invalid signature")

    user = _extract_user(fields["user"])
    query_id = fields.get(
        "hash"
    )  # Telegram uses `hash` as the message signature; query_id may also be present
    query_id = fields.get("query_id")
    return VerifiedInitData(user=user, auth_date=auth_date, query_id=query_id, raw=fields)
