from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Protocol

from ..core.errors import AiProviderError

_MAX_TX_IN_PROMPT = 20
_MAX_LABEL_LEN = 64
_MAX_FIELD_LEN = 128
_MAX_OUTPUT_CHARS = 4000
_MAX_OUTPUT_WORDS = 250
_MAX_INPUT_CHARS = 8000
_MAX_AI_RETRIES = 2

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_URL_RE = re.compile(
    r"(?:https?://|www\.|ftp://|file://|javascript:|data:)[^\s<>\'\"]+", re.IGNORECASE
)
_MARKDOWN_RE = re.compile(r"[#*_~`\[\]>|]{2,}")
_HTML_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")


def sanitize_text(value: str | None, *, max_len: int = _MAX_LABEL_LEN) -> str:
    if value is None:
        return ""
    cleaned = _CTRL_RE.sub("", str(value))
    return cleaned[:max_len]


class AiProvider(Protocol):
    name: str

    async def complete(self, system: str, user: str, *, max_tokens: int) -> str: ...


def _bounded_tx(tx: dict[str, Any]) -> dict[str, Any]:
    return {
        "hash": sanitize_text(str(tx.get("hash", "")), max_len=80),
        "direction": sanitize_text(str(tx.get("direction", "")), max_len=8),
        "counterparty": sanitize_text(str(tx.get("counterparty", "")), max_len=80),
        "amount": sanitize_text(str(tx.get("amount", "")), max_len=40),
        "symbol": sanitize_text(str(tx.get("symbol", "")), max_len=16),
        "status": sanitize_text(str(tx.get("status", "")), max_len=16),
        "risk_level": sanitize_text(str(tx.get("risk_level", "")), max_len=8),
        "token_symbol": sanitize_text(str(tx.get("token_symbol") or ""), max_len=16) or None,
        "token_amount": sanitize_text(str(tx.get("token_amount") or ""), max_len=40) or None,
    }


def build_wallet_prompt(
    *,
    chain: str,
    address: str,
    label: str | None,
    native_amount: Decimal | None,
    native_symbol: str | None,
    total_usd: Decimal | None,
    recent_txs: list[dict[str, Any]],
    tokens_count: int,
) -> tuple[str, str]:
    system = (
        "You are an analyst for a read-only crypto wallet intelligence platform. "
        "Your task is to summarize on-chain wallet activity for the user in plain language. "
        "Rules you MUST follow:\n"
        "- Distinguish clearly between factual on-chain data and your interpretation.\n"
        "- Never output URLs, never output executable code, never output commands.\n"
        "- Never claim a wallet is malicious unless you can cite an on-chain fact from the data.\n"
        "- Do not provide financial advice.\n"
        "- Keep the response under 200 words.\n"
        "- Output a single plain-text explanation, no markdown, no JSON, no HTML.\n"
    )
    bounded_txs = [_bounded_tx(tx) for tx in (recent_txs or [])[:_MAX_TX_IN_PROMPT]]
    payload = {
        "chain": sanitize_text(chain, max_len=_MAX_FIELD_LEN),
        "address": sanitize_text(address, max_len=80),
        "label": sanitize_text(label, max_len=_MAX_LABEL_LEN),
        "native_amount": str(native_amount) if native_amount is not None else None,
        "native_symbol": sanitize_text(native_symbol, max_len=16) if native_symbol else None,
        "total_usd": str(total_usd) if total_usd is not None else None,
        "tokens_count": int(tokens_count) if tokens_count is not None else 0,
        "recent_transactions": bounded_txs,
    }
    user_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(user_payload) > _MAX_INPUT_CHARS:
        truncated_txs = bounded_txs[:5]
        payload["recent_transactions"] = truncated_txs
        user_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        if len(user_payload) > _MAX_INPUT_CHARS:
            user_payload = user_payload[:_MAX_INPUT_CHARS]
    return system, user_payload


def validate_explanation(text: str) -> str:
    if not text or not isinstance(text, str):
        raise AiProviderError("empty model output")
    cleaned = _CTRL_RE.sub("", text)
    cleaned = _URL_RE.sub("[redacted]", cleaned)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = cleaned.replace("`", "")
    cleaned = _MARKDOWN_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    words = cleaned.split()
    if len(words) > _MAX_OUTPUT_WORDS:
        cleaned = " ".join(words[:_MAX_OUTPUT_WORDS])
    if len(cleaned) > _MAX_OUTPUT_CHARS:
        cleaned = cleaned[:_MAX_OUTPUT_CHARS]
    if not cleaned.strip():
        raise AiProviderError("empty model output after sanitization")
    return cleaned
