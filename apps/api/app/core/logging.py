from __future__ import annotations

import contextlib
import logging
import sys
from typing import Any

from .config import get_settings

_SENSITIVE_KEYS = {
    "authorization",
    "token",
    "api_key",
    "apikey",
    "secret",
    "password",
    "init_data",
    "initdata",
    "bot_token",
    "cookie",
    "session",
    "x-api-key",
    "x-telegram-bot-auth-secret",
}

_REDACTED = "***"


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


class _SanitizingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            with contextlib.suppress(Exception):
                record.args = tuple(_sanitize(a) for a in record.args)
        return True


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (_REDACTED if _is_sensitive(k) else _sanitize(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_sanitize(v) for v in value)
    return value


def _is_sensitive(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    return key.lower() in _SENSITIVE_KEYS


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(stream=sys.stdout)
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | rid=%(request_id)s | %(message)s"
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)
    handler.addFilter(_RequestIdFilter())
    handler.addFilter(_SanitizingFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
