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
    duplicate_field: tuple[str, str] | None = None,
) -> str:
    user = user if user is not None else USER_OBJ
    auth_date = auth_date if auth_date is not None else int(time.time())
    fields = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user, separators=(",", ":")),
        "auth_date": str(auth_date),
        **(extra or {}),
    }
    fields.pop("hash", None)
    sorted_keys = sorted(fields.keys())
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted_keys)
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    encoded = urlencode(fields)
    if duplicate_field:
        encoded += f"&{duplicate_field[0]}={duplicate_field[1]}"
    return encoded


def test_valid_init_data(monkeypatch):
    from apps.api.app.core import config as cfg

    monkeypatch.setattr(cfg.get_settings(), "telegram_bot_token", BOT_TOKEN)
    monkeypatch.setattr(cfg.get_settings(), "initdata_max_age_seconds", 3600)
    init = _make_init_data()
    verified = verify_init_data(init, bot_token=BOT_TOKEN)
    assert verified.user.id == 123456789
    assert verified.user.username == "alice"
    assert verified.query_id == "AAHdF6IQAAAAAN0XohDhrOrc"


def test_invalid_signature_rejected():
    init = _make_init_data()
    tampered = init[:-2] + "00"
    with pytest.raises(InitDataError):
        verify_init_data(tampered, bot_token=BOT_TOKEN)


def test_modified_user_payload_rejected():
    init = _make_init_data()
    import re

    tampered_user = json.dumps({**USER_OBJ, "id": 999999}, separators=(",", ":"))
    new_init = re.sub(r"user=[^&]+", f"user={tampered_user}", init)
    with pytest.raises(InitDataError):
        verify_init_data(new_init, bot_token=BOT_TOKEN)


def test_expired_auth_date_rejected(monkeypatch):
    from apps.api.app.core import config as cfg

    monkeypatch.setattr(cfg.get_settings(), "initdata_max_age_seconds", 10)
    old = int(time.time()) - 100
    init = _make_init_data(auth_date=old)
    with pytest.raises(InitDataError):
        verify_init_data(init, bot_token=BOT_TOKEN)


def test_future_auth_date_rejected():
    future = int(time.time()) + 120
    init = _make_init_data(auth_date=future)
    with pytest.raises(InitDataError):
        verify_init_data(init, bot_token=BOT_TOKEN)


def test_malformed_user_json_rejected():
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
    init = urlencode(fields)
    with pytest.raises(InitDataError):
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
    init = urlencode(fields)
    with pytest.raises(InitDataError):
        verify_init_data(init, bot_token=BOT_TOKEN)


def test_missing_hash_rejected():
    init = _make_init_data().replace("&hash=", "&nothash=")
    with pytest.raises(InitDataError):
        verify_init_data(init, bot_token=BOT_TOKEN)


def test_empty_init_data_rejected():
    with pytest.raises(InitDataError):
        verify_init_data("", bot_token=BOT_TOKEN)


def test_oversized_init_data_rejected():
    huge = "user=x&auth_date=1&hash=" + "a" * 10000
    with pytest.raises(InitDataError):
        verify_init_data(huge, bot_token=BOT_TOKEN)


def test_duplicate_parameters_rejected():
    init = _make_init_data(duplicate_field=("auth_date", str(int(time.time()) - 999)))
    with pytest.raises(InitDataError):
        verify_init_data(init, bot_token=BOT_TOKEN)


def test_all_errors_are_normalized():
    init = _make_init_data()
    tampered = init[:-2] + "00"
    with pytest.raises(InitDataError) as exc_info:
        verify_init_data(tampered, bot_token=BOT_TOKEN)
    assert str(exc_info.value) == "malformed"
