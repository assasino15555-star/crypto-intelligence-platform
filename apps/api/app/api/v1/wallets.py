from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.errors import ConflictError
from ...core.logging import get_logger
from ...models.token_holding import TokenHolding
from ...models.transaction import Transaction
from ...models.user import User
from ...models.wallet import Wallet, WalletSnapshot
from ...providers.registry import get_provider
from ...schemas.models import (
    Page,
    PageMeta,
    TokenHoldingOut,
    TransactionOut,
    WalletCreate,
    WalletOut,
    WalletSnapshotOut,
    WalletUpdate,
    WalletWithSummary,
)
from ...utils.addresses import validate_address
from ...utils.rate_limit import SNAPSHOT_USER, WALLET_CREATE_USER, make_limiter
from ..deps import Pagination, get_current_user, get_db, pagination

log = get_logger(__name__)
router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.post("", response_model=WalletOut, status_code=201)
async def post_wallet(
    payload: WalletCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletOut:
    limiter = make_limiter(WALLET_CREATE_USER)
    await limiter.check(f"wallet_create:{user.id}")

    settings = get_settings()
    count_q = await db.execute(
        select(func.count()).select_from(Wallet).where(Wallet.user_id == user.id)
    )
    wallet_count = int(count_q.scalar_one() or 0)
    if wallet_count >= settings.max_wallets_per_user:
        raise ConflictError("wallet quota exceeded")

    normalized = validate_address(payload.chain, payload.address)

    dup_q = await db.execute(
        select(Wallet).where(
            Wallet.user_id == user.id,
            Wallet.chain == payload.chain,
            Wallet.address == normalized.address,
        )
    )
    if dup_q.scalar_one_or_none() is not None:
        raise ConflictError("wallet already exists for this user and chain")

    provider = get_provider()
    try:
        balance = await provider.fetch_balance(payload.chain, normalized.address)
    except Exception:
        log.warning(
            "wallet create provider error chain=%s addr=%s", payload.chain, normalized.address
        )
        balance = None

    wallet = Wallet(
        user_id=user.id,
        chain=payload.chain,
        address=normalized.address,
        address_type="evm",
        label=payload.label,
        native_symbol=balance.native_symbol if balance else "ETH",
        last_native_amount=balance.native_amount if balance else None,
    )
    db.add(wallet)
    await db.flush()
    await db.commit()
    await db.refresh(wallet)
    log.info("wallet created uid=%s wid=%s chain=%s", user.id, wallet.id, payload.chain)
    return WalletOut.model_validate(wallet)


@router.get("", response_model=Page)
async def get_wallets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pg: Pagination = Depends(pagination),
    active_only: bool = Query(default=False),
) -> Page:
    conditions = [Wallet.user_id == user.id]
    if active_only:
        conditions.append(Wallet.is_active.is_(True))
    total_q = await db.execute(select(func.count()).select_from(Wallet).where(*conditions))
    total = int(total_q.scalar_one() or 0)
    stmt = (
        select(Wallet)
        .where(*conditions)
        .order_by(Wallet.created_at.desc())
        .offset(pg.offset)
        .limit(pg.page_size)
    )
    res = await db.execute(stmt)
    items = list(res.scalars().all())
    return Page(
        items=[WalletOut.model_validate(w).model_dump() for w in items],
        meta=PageMeta(page=pg.page, page_size=pg.page_size, total=total),
    )


@router.get("/{wallet_id}", response_model=WalletWithSummary)
async def get_wallet(
    wallet_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletWithSummary:
    wallet = await _get_owned_wallet(db, user_id=user.id, wallet_id=wallet_id)
    return WalletWithSummary.model_validate(wallet)


@router.patch("/{wallet_id}", response_model=WalletOut)
async def patch_wallet(
    wallet_id: uuid.UUID,
    payload: WalletUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletOut:
    wallet = await _get_owned_wallet(db, user_id=user.id, wallet_id=wallet_id)
    if payload.label is not None:
        wallet.label = payload.label
    if payload.is_active is not None:
        wallet.is_active = payload.is_active
    await db.flush()
    await db.commit()
    await db.refresh(wallet)
    return WalletOut.model_validate(wallet)


@router.delete("/{wallet_id}", status_code=204)
async def delete_wallet_route(
    wallet_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    wallet = await _get_owned_wallet(db, user_id=user.id, wallet_id=wallet_id)
    await db.delete(wallet)
    await db.flush()
    await db.commit()


@router.get("/{wallet_id}/transactions", response_model=Page)
async def get_txs(
    wallet_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pg: Pagination = Depends(pagination),
    direction: str | None = Query(default=None, pattern="^(in|out|self)$"),
) -> Page:
    wallet = await _get_owned_wallet(db, user_id=user.id, wallet_id=wallet_id)
    base = select(Transaction).where(Transaction.wallet_id == wallet.id)
    cnt_base = (
        select(func.count()).select_from(Transaction).where(Transaction.wallet_id == wallet.id)
    )
    if direction:
        base = base.where(Transaction.direction == direction)
        cnt_base = cnt_base.where(Transaction.direction == direction)
    total_q = await db.execute(cnt_base)
    total = int(total_q.scalar_one() or 0)
    res = await db.execute(
        base.order_by(Transaction.timestamp.desc()).offset(pg.offset).limit(pg.page_size)
    )
    items = list(res.scalars().all())
    return Page(
        items=[_tx_to_dict(t) for t in items],
        meta=PageMeta(page=pg.page, page_size=pg.page_size, total=total),
    )


@router.get("/{wallet_id}/holdings", response_model=list[TokenHoldingOut])
async def get_holdings(
    wallet_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TokenHoldingOut]:
    wallet = await _get_owned_wallet(db, user_id=user.id, wallet_id=wallet_id)
    res = await db.execute(
        select(TokenHolding)
        .where(TokenHolding.wallet_id == wallet.id)
        .order_by(TokenHolding.estimated_usd_value.desc().nullslast())
    )
    return [TokenHoldingOut.model_validate(t) for t in res.scalars().all()]


@router.get("/{wallet_id}/snapshots", response_model=list[WalletSnapshotOut])
async def get_snapshots(
    wallet_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[WalletSnapshotOut]:
    wallet = await _get_owned_wallet(db, user_id=user.id, wallet_id=wallet_id)
    res = await db.execute(
        select(WalletSnapshot)
        .where(WalletSnapshot.wallet_id == wallet.id)
        .order_by(WalletSnapshot.taken_at.desc())
        .limit(min(limit, 200))
    )
    return [WalletSnapshotOut.model_validate(s) for s in res.scalars().all()]


@router.post("/{wallet_id}/snapshot", response_model=WalletSnapshotOut, status_code=201)
async def post_snapshot(
    wallet_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletSnapshotOut:
    limiter = make_limiter(SNAPSHOT_USER)
    await limiter.check(f"snapshot:{user.id}")
    wallet = await _get_owned_wallet(db, user_id=user.id, wallet_id=wallet_id)
    provider = get_provider()
    try:
        balance = await provider.fetch_balance(wallet.chain, wallet.address)
        holdings = await provider.fetch_token_holdings(wallet.chain, wallet.address)
    except Exception as exc:
        raise ConflictError(f"snapshot failed: {exc}") from exc

    import datetime as _dt

    tokens_usd = sum((h.estimated_usd_value or Decimal(0) for h in holdings), Decimal(0))
    native_usd = balance.estimated_usd_value
    total_usd = (native_usd or Decimal(0)) + tokens_usd
    snap = WalletSnapshot(
        wallet_id=wallet.id,
        taken_at=_dt.datetime.now(_dt.UTC).replace(tzinfo=None),
        native_amount=balance.native_amount,
        native_usd_price=balance.native_usd_price,
        native_usd=native_usd,
        tokens_usd=tokens_usd,
        total_usd=total_usd,
        tokens_count=len(holdings),
    )
    db.add(snap)
    wallet.last_native_amount = balance.native_amount
    wallet.last_total_usd = total_usd
    wallet.last_synced_at = snap.taken_at
    await db.flush()
    await db.commit()
    await db.refresh(snap)
    return WalletSnapshotOut.model_validate(snap)


async def _get_owned_wallet(
    db: AsyncSession, *, user_id: uuid.UUID, wallet_id: uuid.UUID
) -> Wallet:
    res = await db.execute(select(Wallet).where(Wallet.id == wallet_id))
    wallet = res.scalar_one_or_none()
    if wallet is None or wallet.user_id != user_id:
        from ...core.errors import NotFoundError

        raise NotFoundError("wallet")
    return wallet


def _tx_to_dict(tx: Transaction) -> dict[str, Any]:
    return TransactionOut(
        id=tx.id,
        tx_hash=tx.tx_hash,
        block=tx.block,
        timestamp=tx.timestamp,
        direction=tx.direction,
        counterparty=tx.counterparty,
        native_amount=tx.native_amount,
        native_symbol=tx.native_symbol,
        token_symbol=tx.token_symbol,
        token_contract=tx.token_contract,
        token_amount=tx.token_amount,
        status=tx.status,
        risk_level=tx.risk_level,
        risk_reasons=tx.risk_reasons.split(",") if tx.risk_reasons else [],
    ).model_dump()
