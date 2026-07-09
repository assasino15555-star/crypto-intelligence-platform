"""Wallet service: creation, ownership, queries."""

from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import ConflictError, NotFoundError, ProviderError
from ..models.token_holding import TokenHolding
from ..models.transaction import Transaction
from ..models.wallet import Wallet, WalletSnapshot
from ..providers.registry import get_provider
from ..utils.addresses import validate_address


async def create_wallet(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    chain: str,
    address: str,
    label: str | None,
) -> Wallet:
    normalized = validate_address(chain, address)

    # Check duplicate (user + chain + address)
    dup = await db.execute(
        select(Wallet).where(
            Wallet.user_id == user_id,
            Wallet.chain == chain,
            Wallet.address == normalized.address,
        )
    )
    if dup.scalar_one_or_none() is not None:
        raise ConflictError("wallet already exists for this user and chain")

    provider = get_provider()
    try:
        balance = await provider.fetch_balance(chain, normalized.address)
    except ProviderError:
        # Tolerate provider failure at creation time — user can retry sync later.
        balance = None

    wallet = Wallet(
        user_id=user_id,
        chain=chain,
        address=normalized.address,
        address_type="evm",
        label=label,
        native_symbol=balance.native_symbol if balance else "ETH",
        last_native_amount=balance.native_amount if balance else None,
    )
    db.add(wallet)
    await db.flush()
    return wallet


async def list_wallets(
    db: AsyncSession, *, user_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[Wallet], int]:
    total_q = await db.execute(
        select(func.count()).select_from(Wallet).where(Wallet.user_id == user_id)
    )
    total = int(total_q.scalar_one() or 0)
    stmt = (
        select(Wallet)
        .where(Wallet.user_id == user_id)
        .order_by(Wallet.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all()), total


async def get_owned_wallet(db: AsyncSession, *, user_id: uuid.UUID, wallet_id: uuid.UUID) -> Wallet:
    stmt = select(Wallet).where(Wallet.id == wallet_id)
    res = await db.execute(stmt)
    wallet = res.scalar_one_or_none()
    if wallet is None:
        raise NotFoundError("wallet")
    if wallet.user_id != user_id:
        # IDOR protection: return 404 to avoid leaking existence
        raise NotFoundError("wallet")
    return wallet


async def update_wallet(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    wallet_id: uuid.UUID,
    label: str | None,
    is_active: bool | None,
) -> Wallet:
    wallet = await get_owned_wallet(db, user_id=user_id, wallet_id=wallet_id)
    if label is not None:
        wallet.label = label
    if is_active is not None:
        wallet.is_active = is_active
    await db.flush()
    return wallet


async def delete_wallet(db: AsyncSession, *, user_id: uuid.UUID, wallet_id: uuid.UUID) -> None:
    wallet = await get_owned_wallet(db, user_id=user_id, wallet_id=wallet_id)
    await db.delete(wallet)
    await db.flush()


async def list_transactions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    wallet_id: uuid.UUID,
    page: int,
    page_size: int,
    direction: str | None = None,
) -> tuple[list[Transaction], int]:
    wallet = await get_owned_wallet(db, user_id=user_id, wallet_id=wallet_id)
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
        base.order_by(Transaction.timestamp.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(res.scalars().all()), total


async def list_holdings(
    db: AsyncSession, *, user_id: uuid.UUID, wallet_id: uuid.UUID
) -> list[TokenHolding]:
    wallet = await get_owned_wallet(db, user_id=user_id, wallet_id=wallet_id)
    res = await db.execute(
        select(TokenHolding)
        .where(TokenHolding.wallet_id == wallet.id)
        .order_by(TokenHolding.estimated_usd_value.desc().nullslast())
    )
    return list(res.scalars().all())


async def list_snapshots(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    wallet_id: uuid.UUID,
    limit: int = 50,
) -> list[WalletSnapshot]:
    wallet = await get_owned_wallet(db, user_id=user_id, wallet_id=wallet_id)
    res = await db.execute(
        select(WalletSnapshot)
        .where(WalletSnapshot.wallet_id == wallet.id)
        .order_by(WalletSnapshot.taken_at.desc())
        .limit(min(limit, 200))
    )
    return list(res.scalars().all())


async def take_snapshot(
    db: AsyncSession, *, user_id: uuid.UUID, wallet_id: uuid.UUID
) -> WalletSnapshot:
    wallet = await get_owned_wallet(db, user_id=user_id, wallet_id=wallet_id)
    provider = get_provider()
    try:
        balance = await provider.fetch_balance(wallet.chain, wallet.address)
        holdings = await provider.fetch_token_holdings(wallet.chain, wallet.address)
    except ProviderError as exc:
        raise ProviderError(f"snapshot failed: {exc}") from exc

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
    # Update wallet summary cache
    wallet.last_native_amount = balance.native_amount
    wallet.last_total_usd = total_usd
    wallet.last_synced_at = snap.taken_at
    await db.flush()
    return snap
