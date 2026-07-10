from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai.prompt import (
    _MAX_AI_RETRIES,
    build_wallet_prompt,
    sanitize_text,
    validate_explanation,
)
from ..ai.providers import get_ai_provider
from ..core.config import get_settings
from ..core.errors import AiProviderError, NotFoundError
from ..core.logging import get_logger
from ..models.ai_cache import AiAnalysis
from ..models.transaction import Transaction
from ..models.wallet import Wallet

log = get_logger(__name__)


async def explain_wallet(
    db: AsyncSession, *, user_id: uuid.UUID, wallet_id: uuid.UUID
) -> AiAnalysis:
    wallet = await _get_owned_wallet(db, user_id=user_id, wallet_id=wallet_id)
    txs_q = await db.execute(
        select(Transaction)
        .where(Transaction.wallet_id == wallet.id)
        .order_by(Transaction.timestamp.desc())
        .limit(20)
    )
    txs = list(txs_q.scalars().all())
    txs_data = [_tx_to_dict(t) for t in txs]
    system, user_prompt = build_wallet_prompt(
        chain=wallet.chain,
        address=wallet.address,
        label=wallet.label,
        native_amount=wallet.last_native_amount,
        native_symbol=wallet.native_symbol,
        total_usd=wallet.last_total_usd,
        recent_txs=txs_data,
        tokens_count=0,
    )
    input_signature = _signature(system + user_prompt)
    cached_q = await db.execute(
        select(AiAnalysis).where(
            AiAnalysis.wallet_id == wallet.id,
            AiAnalysis.kind == "wallet_summary",
            AiAnalysis.input_signature == input_signature,
        )
    )
    cached_row = cached_q.scalar_one_or_none()
    if cached_row is not None:
        return cached_row

    explanation = await _call_with_retries(system, user_prompt, max_tokens=400)
    row = AiAnalysis(
        wallet_id=wallet.id,
        tx_id=None,
        kind="wallet_summary",
        input_signature=input_signature,
        input_summary=_summary(wallet, txs_data),
        explanation=explanation,
        model=_model_name(),
        is_cached=False,
    )
    db.add(row)
    await db.flush()
    return row


async def explain_transaction(
    db: AsyncSession, *, user_id: uuid.UUID, tx_id: uuid.UUID
) -> AiAnalysis:
    tx_q = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    tx = tx_q.scalar_one_or_none()
    if tx is None:
        raise NotFoundError("transaction")
    wallet_q = await db.execute(select(Wallet).where(Wallet.id == tx.wallet_id))
    wallet = wallet_q.scalar_one_or_none()
    if wallet is None or wallet.user_id != user_id:
        raise NotFoundError("transaction")
    txs_data = [_tx_to_dict(tx)]
    system, user_prompt = build_wallet_prompt(
        chain=wallet.chain,
        address=wallet.address,
        label=wallet.label,
        native_amount=wallet.last_native_amount,
        native_symbol=wallet.native_symbol,
        total_usd=wallet.last_total_usd,
        recent_txs=txs_data,
        tokens_count=0,
    )
    input_signature = _signature(system + user_prompt + str(tx_id))
    cached_q = await db.execute(
        select(AiAnalysis).where(
            AiAnalysis.tx_id == tx.id,
            AiAnalysis.kind == "tx_explain",
            AiAnalysis.input_signature == input_signature,
        )
    )
    cached_row = cached_q.scalar_one_or_none()
    if cached_row is not None:
        return cached_row
    explanation = await _call_with_retries(system, user_prompt, max_tokens=300)
    row = AiAnalysis(
        wallet_id=wallet.id,
        tx_id=tx.id,
        kind="tx_explain",
        input_signature=input_signature,
        input_summary=_summary(wallet, txs_data),
        explanation=explanation,
        model=_model_name(),
        is_cached=False,
    )
    db.add(row)
    await db.flush()
    return row


async def _get_owned_wallet(
    db: AsyncSession, *, user_id: uuid.UUID, wallet_id: uuid.UUID
) -> Wallet:
    res = await db.execute(select(Wallet).where(Wallet.id == wallet_id))
    wallet = res.scalar_one_or_none()
    if wallet is None or wallet.user_id != user_id:
        raise NotFoundError("wallet")
    return wallet


async def _call_with_retries(system: str, user_prompt: str, *, max_tokens: int) -> str:
    provider = get_ai_provider()
    last_exc: Exception | None = None
    for attempt in range(_MAX_AI_RETRIES + 1):
        try:
            raw = await provider.complete(system, user_prompt, max_tokens=max_tokens)
            return validate_explanation(raw)
        except AiProviderError as exc:
            last_exc = exc
            if attempt >= _MAX_AI_RETRIES:
                raise
    raise AiProviderError(f"unreachable ai state: {last_exc}")


def _signature(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:32]


def _model_name() -> str:
    settings = get_settings()
    return settings.ai_model if settings.ai_provider == "openai" else "mock"


def _tx_to_dict(tx: Transaction) -> dict[str, Any]:
    return {
        "hash": tx.tx_hash,
        "direction": tx.direction,
        "counterparty": tx.counterparty,
        "amount": str(tx.native_amount),
        "symbol": tx.native_symbol,
        "status": tx.status,
        "risk_level": tx.risk_level,
        "risk_reasons": (tx.risk_reasons or "").split(",") if tx.risk_reasons else [],
        "token_symbol": tx.token_symbol,
        "token_amount": str(tx.token_amount) if tx.token_amount is not None else None,
    }


def _summary(wallet: Wallet, txs_data: list[dict[str, Any]]) -> str:
    s = f"{wallet.chain}:{wallet.address} txs={len(txs_data)}"
    return sanitize_text(s, max_len=128)
