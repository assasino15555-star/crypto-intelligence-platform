"""Telegram initData verification tests.

Covers:
  - valid initData (computed with the real algorithm)
  - invalid signature (tampered hash)
  - modified payload (tampered user)
  - expired auth_date
  - malformed user JSON
  - missing required fields
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from apps.api.app.security.telegram import InitDataError, verify_init_data

BOT_TOKEN = "1234567890:TESTBOTOKEN0123456789_abcdefghij"
USER_OBJ = {
    "id": 123456789,
    "username": "alice",
    "first_name": "Alice",
    "last_name": "Tester",
    "language_code": "en",
}


def _make_init_data(
    *,
    user: dict | None = None,
    auth_date: int | None = None,
    extra: dict | None = None,
    bot_token: str = BOT_TOKEN,
) -> str:
    user = user if user is not None else USER_OBJ
    auth_date = auth_date if auth_date is not None else int(time.time())
    fields = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user, separators=(",", ":")),
        "auth_date": str(auth_date),
        "signature": "unused",
        **(extra or {}),
    }
    fields.pop("hash", None)
    sorted_keys = sorted(fields.keys())
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted_keys)
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    hash_hex = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    fields["hash"] = hash_hex
    return urlencode(fields)


def test_valid_init_data(monkeypatch):
    from apps.api.app.core import config as cfg

    monkeypatch.setattr(cfg.get_settings(), "telegram_bot_token", BOT_TOKEN)
    monkeypatch.setattr(cfg.get_settings(), "initdata_max_age_seconds", 3600)
    init = _make_init_data()
    verified = verify_init_data(init, bot_token=BOT_TOKEN)
    assert verified.user.id == 123456789
    assert verified.user.username == "alice"


def test_invalid_signature_rejected(monkeypatch):
    init = _make_init_data()
    # Tamper with hash
    tampered = init.replace("hash=", "hash=00")[:-2]
    with pytest.raises(InitDataError, match="invalid signature"):
        verify_init_data(tampered, bot_token=BOT_TOKEN)


def test_modified_user_payload_rejected():
    init = _make_init_data()
    # Replace user id while keeping the same hash. The new init string differs
    # from the one the hash was computed over, so verification must fail.
    tampered_user = json.dumps({**USER_OBJ, "id": 999999}, separators=(",", ":"))
    import re

    new_init = re.sub(
        r"user=[^&]+",
        f"user={tampered_user}",
        init,
    )
    with pytest.raises(InitDataError):
        verify_init_data(new_init, bot_token=BOT_TOKEN)


def test_expired_auth_date_rejected(monkeypatch):
    from apps.api.app.core import config as cfg

    monkeypatch.setattr(cfg.get_settings(), "initdata_max_age_seconds", 10)
    old = int(time.time()) - 100
    init = _make_init_data(auth_date=old)
    with pytest.raises(InitDataError, match="too old"):
        verify_init_data(init, bot_token=BOT_TOKEN)


def test_future_auth_date_rejected():
    future = int(time.time()) + 120
    init = _make_init_data(auth_date=future)
    with pytest.raises(InitDataError, match="future"):
        verify_init_data(init, bot_token=BOT_TOKEN)


def test_malformed_user_json_rejected():
    # Build initData with invalid JSON in `user`, but with a valid signature
    # over the malformed string. Verification passes; user parsing fails.
    bad_user = "{not valid json"
    fields = {
        "query_id": "x",
        "user": bad_user,
        "auth_date": str(int(time.time())),
    }
    sorted_keys = sorted(fields.keys())
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted_keys)
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    from urllib.parse import urlencode

    init = urlencode(fields)
    with pytest.raises(InitDataError, match="malformed user"):
        verify_init_data(init, bot_token=BOT_TOKEN)


def test_missing_user_field_rejected():
    fields = {
        "query_id": "x",
        "auth_date": str(int(time.time())),
    }
    sorted_keys = sorted(fields.keys())
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted_keys)
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    from urllib.parse import urlencode

    init = urlencode(fields)
    with pytest.raises(InitDataError, match="missing user"):
        verify_init_data(init, bot_token=BOT_TOKEN)


def test_missing_hash_rejected():
    init = _make_init_data().replace("&hash=", "&nothash=")
    # Renamed field removes hash; signature verification then fails.
    with pytest.raises(InitDataError, match="missing hash"):
        verify_init_data(init, bot_token=BOT_TOKEN)


def test_empty_init_data_rejected():
    with pytest.raises(InitDataError):
        verify_init_data("", bot_token=BOT_TOKEN)


def test_no_bot_token_rejected(monkeypatch):
    from apps.api.app.core import config as cfg

    monkeypatch.setattr(cfg.get_settings(), "telegram_bot_token", "")
    init = _make_init_data()
    with pytest.raises(InitDataError, match="bot token"):
        verify_init_data(init)
