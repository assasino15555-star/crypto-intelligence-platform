from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

from ..core.config import get_settings


class InitDataError(Exception):
    pass


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
        raise InitDataError("malformed") from exc
    if not isinstance(data, dict):
        raise InitDataError("malformed")
    if "id" not in data:
        raise InitDataError("malformed")
    uid = data["id"]
    if not isinstance(uid, int) or uid <= 0:
        raise InitDataError("malformed")
    return TelegramUser(
        id=uid,
        username=data.get("username"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        language_code=data.get("language_code"),
        is_premium=bool(data.get("is_premium", False)),
        raw=data,
    )


def _parse_fields(init_data: str) -> dict[str, str]:
    pairs = parse_qsl(init_data, keep_blank_values=True, max_num_fields=32)
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise InitDataError("malformed")
        fields[key] = value
    return fields


def verify_init_data(init_data: str, *, bot_token: str | None = None) -> VerifiedInitData:
    if not init_data or not isinstance(init_data, str):
        raise InitDataError("malformed")
    if len(init_data) > 8192:
        raise InitDataError("malformed")

    settings = get_settings()
    token = bot_token if bot_token is not None else settings.telegram_bot_token
    if not token:
        raise InitDataError("malformed")

    fields = _parse_fields(init_data)

    received_hash = fields.pop("hash", None)
    if not received_hash or len(received_hash) != 64:
        raise InitDataError("malformed")

    if "user" not in fields:
        raise InitDataError("malformed")

    auth_date_raw = fields.get("auth_date")
    if not auth_date_raw:
        raise InitDataError("malformed")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise InitDataError("malformed") from exc

    now = int(time.time())
    max_age = settings.initdata_max_age_seconds
    if now - auth_date > max_age:
        raise InitDataError("malformed")
    if auth_date - now > 60:
        raise InitDataError("malformed")

    sorted_keys = sorted(fields.keys())
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted_keys)

    secret = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    computed = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        raise InitDataError("malformed")

    user = _extract_user(fields["user"])
    query_id = fields.get("query_id")
    return VerifiedInitData(user=user, auth_date=auth_date, query_id=query_id, raw=fields)


def init_data_replay_key(verified: VerifiedInitData) -> str:
    raw = "&".join(f"{k}={v}" for k, v in sorted(verified.raw.items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
