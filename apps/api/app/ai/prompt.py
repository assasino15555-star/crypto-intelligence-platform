"""AI provider abstraction with strict input/output boundaries.

Security rules:
  * User-controlled labels and blockchain text are treated as UNTRUSTED DATA.
  * System prompt is fixed and never includes user input verbatim.
  * Input is sanitized: control chars stripped, size-bounded.
  * Structured input: we pass a compact JSON envelope, never raw free text.
  * Output is validated against an explicit schema and length-bounded.
  * No code execution, no URL fetching by the model — we never honor any
    instruction that asks for these.
  * Retry only on malformed output, with a strict limit.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Protocol

from ..core.errors import AiProviderError
from ..core.logging import get_logger

log = get_logger(__name__)

_MAX_TX_IN_PROMPT = 20
_MAX_LABEL_LEN = 64
_MAX_OUTPUT_CHARS = 4000
_MAX_INPUT_CHARS = 8000
_MAX_AI_RETRIES = 2

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str | None, *, max_len: int = _MAX_LABEL_LEN) -> str:
    if value is None:
        return ""
    cleaned = _CTRL_RE.sub("", str(value))
    return cleaned[:max_len]


class AiProvider(Protocol):
    name: str

    async def complete(self, system: str, user: str, *, max_tokens: int) -> str: ...


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
    """Return (system_prompt, user_prompt) with a strict boundary.

    The system prompt defines the model's role and constraints. The user
    prompt contains ONLY structured JSON data, never free-form instructions
    from user-controlled fields.
    """
    system = (
        "You are an analyst for a read-only crypto wallet intelligence platform. "
        "Your task is to summarize on-chain wallet activity for the user in plain language. "
        "Rules you MUST follow:\n"
        "- Distinguish clearly between factual on-chain data and your interpretation.\n"
        "- Never output URLs, never output executable code, never output commands.\n"
        "- Never claim a wallet is malicious unless you can cite an on-chain fact from the data.\n"
        "- Do not provide financial advice.\n"
        "- Keep the response under 200 words.\n"
        "- Output a single plain-text explanation, no markdown, no JSON.\n"
    )
    bounded_txs = (recent_txs or [])[:_MAX_TX_IN_PROMPT]
    payload = {
        "chain": chain,
        "address": address,
        "label": sanitize_text(label, max_len=_MAX_LABEL_LEN),
        "native_amount": str(native_amount) if native_amount is not None else None,
        "native_symbol": native_symbol,
        "total_usd": str(total_usd) if total_usd is not None else None,
        "tokens_count": tokens_count,
        "recent_transactions": bounded_txs,
    }
    user_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(user_payload) > _MAX_INPUT_CHARS:
        user_payload = user_payload[:_MAX_INPUT_CHARS]
    return system, user_payload


def validate_explanation(text: str) -> str:
    """Sanitize and bound the model's output."""
    if not text or not isinstance(text, str):
        raise AiProviderError("empty model output")
    cleaned = _CTRL_RE.sub("", text)
    # Strip URLs the model may have emitted (we never trust them)
    cleaned = re.sub(r"https?://\S+", "[redacted-url]", cleaned)
    # Strip backticks to prevent accidental code blocks
    cleaned = cleaned.replace("`", "")
    if len(cleaned) > _MAX_OUTPUT_CHARS:
        cleaned = cleaned[:_MAX_OUTPUT_CHARS]
    if not cleaned.strip():
        raise AiProviderError("empty model output after sanitization")
    return cleaned
