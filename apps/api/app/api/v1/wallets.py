"""Wallet routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.user import User
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
from ...services.wallets import (
    create_wallet,
    delete_wallet,
    get_owned_wallet,
    list_holdings,
    list_snapshots,
    list_transactions,
    list_wallets,
    take_snapshot,
    update_wallet,
)
from ...utils.rate_limit import SNAPSHOT_LIMITER, client_key
from ..deps import Pagination, get_current_user, get_db, pagination

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.post("", response_model=WalletOut, status_code=201)
async def post_wallet(
    payload: WalletCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletOut:
    wallet = await create_wallet(
        db,
        user_id=user.id,
        chain=payload.chain,
        address=payload.address,
        label=payload.label,
    )
    await db.commit()
    await db.refresh(wallet)
    return WalletOut.model_validate(wallet)


@router.get("", response_model=Page)
async def get_wallets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pg: Pagination = Depends(pagination),
    active_only: bool = Query(default=False),
) -> Page:
    items, total = await list_wallets(db, user_id=user.id, page=pg.page, page_size=pg.page_size)
    return Page(
        items=[WalletOut.model_validate(w).model_dump() for w in items],
        meta=PageMeta(page=pg.page, page_size=pg.page_size, total=total),
    )


@router.get("/{wallet_id}", response_model=WalletWithSummary)
async def get_wallet(
    wallet_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletWithSummary:
    wallet = await get_owned_wallet(db, user_id=user.id, wallet_id=wallet_id)
    return WalletWithSummary.model_validate(wallet)


@router.patch("/{wallet_id}", response_model=WalletOut)
async def patch_wallet(
    wallet_id: UUID,
    payload: WalletUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletOut:
    wallet = await update_wallet(
        db,
        user_id=user.id,
        wallet_id=wallet_id,
        label=payload.label,
        is_active=payload.is_active,
    )
    await db.commit()
    await db.refresh(wallet)
    return WalletOut.model_validate(wallet)


@router.delete("/{wallet_id}", status_code=204)
async def delete_wallet_route(
    wallet_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await delete_wallet(db, user_id=user.id, wallet_id=wallet_id)
    await db.commit()


@router.get("/{wallet_id}/transactions", response_model=Page)
async def get_txs(
    wallet_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pg: Pagination = Depends(pagination),
    direction: str | None = Query(default=None, pattern="^(in|out|self)$"),
) -> Page:
    items, total = await list_transactions(
        db,
        user_id=user.id,
        wallet_id=wallet_id,
        page=pg.page,
        page_size=pg.page_size,
        direction=direction,
    )
    return Page(
        items=[
            TransactionOut(
                id=t.id,
                tx_hash=t.tx_hash,
                block=t.block,
                timestamp=t.timestamp,
                direction=t.direction,
                counterparty=t.counterparty,
                native_amount=t.native_amount,
                native_symbol=t.native_symbol,
                token_symbol=t.token_symbol,
                token_contract=t.token_contract,
                token_amount=t.token_amount,
                status=t.status,
                risk_level=t.risk_level,
                risk_reasons=(t.risk_reasons or "").split(",") if t.risk_reasons else [],
            ).model_dump()
            for t in items
        ],
        meta=PageMeta(page=pg.page, page_size=pg.page_size, total=total),
    )


@router.get("/{wallet_id}/holdings", response_model=list[TokenHoldingOut])
async def get_holdings(
    wallet_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TokenHoldingOut]:
    items = await list_holdings(db, user_id=user.id, wallet_id=wallet_id)
    return [TokenHoldingOut.model_validate(t) for t in items]


@router.get("/{wallet_id}/snapshots", response_model=list[WalletSnapshotOut])
async def get_snapshots(
    wallet_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[WalletSnapshotOut]:
    items = await list_snapshots(db, user_id=user.id, wallet_id=wallet_id, limit=limit)
    return [WalletSnapshotOut.model_validate(s) for s in items]


@router.post("/{wallet_id}/snapshot", response_model=WalletSnapshotOut, status_code=201)
async def post_snapshot(
    wallet_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletSnapshotOut:
    SNAPSHOT_LIMITER.consume(client_key(request))
    snap = await take_snapshot(db, user_id=user.id, wallet_id=wallet_id)
    await db.commit()
    await db.refresh(snap)
    return WalletSnapshotOut.model_validate(snap)
