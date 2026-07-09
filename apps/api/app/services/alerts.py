"""Alert service: create, list, update, delete, evaluate."""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import NotFoundError, ValidationError
from ..models.alert import Alert, AlertDelivery
from ..models.transaction import Transaction
from .wallets import get_owned_wallet

ALLOWED_KINDS = {"incoming_above", "outgoing_above", "activity", "balance_above", "token_transfer"}


async def create_alert(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    wallet_id: uuid.UUID,
    kind: str,
    threshold_amount: float | None,
    note: str | None,
) -> Alert:
    if kind not in ALLOWED_KINDS:
        raise ValidationError(f"invalid alert kind: {kind}")
    if kind in {"incoming_above", "outgoing_above", "balance_above"} and threshold_amount is None:
        raise ValidationError(f"{kind} requires threshold_amount")
    # Verify ownership
    await get_owned_wallet(db, user_id=user_id, wallet_id=wallet_id)
    alert = Alert(
        user_id=user_id,
        wallet_id=wallet_id,
        kind=kind,
        threshold_amount=threshold_amount,
        note=note,
    )
    db.add(alert)
    await db.flush()
    return alert


async def list_alerts(
    db: AsyncSession, *, user_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[Alert], int]:
    total_q = await db.execute(
        select(func.count()).select_from(Alert).where(Alert.user_id == user_id)
    )
    total = int(total_q.scalar_one() or 0)
    res = await db.execute(
        select(Alert)
        .where(Alert.user_id == user_id)
        .order_by(Alert.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(res.scalars().all()), total


async def update_alert(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    alert_id: uuid.UUID,
    is_active: bool | None,
    threshold_amount: float | None,
    note: str | None,
) -> Alert:
    stmt = select(Alert).where(Alert.id == alert_id, Alert.user_id == user_id)
    res = await db.execute(stmt)
    alert = res.scalar_one_or_none()
    if alert is None:
        raise NotFoundError("alert")
    if is_active is not None:
        alert.is_active = is_active
    if threshold_amount is not None:
        alert.threshold_amount = threshold_amount
    if note is not None:
        alert.note = note
    await db.flush()
    return alert


async def delete_alert(db: AsyncSession, *, user_id: uuid.UUID, alert_id: uuid.UUID) -> None:
    stmt = select(Alert).where(Alert.id == alert_id, Alert.user_id == user_id)
    res = await db.execute(stmt)
    alert = res.scalar_one_or_none()
    if alert is None:
        raise NotFoundError("alert")
    await db.delete(alert)
    await db.flush()


def _event_signature(alert_id: uuid.UUID, tx_id: uuid.UUID | None, kind: str) -> str:
    base = f"{alert_id}:{kind}"
    if tx_id is not None:
        base += f":{tx_id}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


async def evaluate_alert_for_tx(
    db: AsyncSession, *, alert: Alert, tx: Transaction
) -> AlertDelivery | None:
    """Evaluate whether the alert fires for a transaction.

    Returns a delivery record if it fires and was newly inserted, or None if:
      * the alert does not apply to this tx (kind mismatch)
      * the alert was already delivered for this tx (idempotent)
    """
    if not alert.is_active:
        return None
    if alert.wallet_id != tx.wallet_id:
        return None
    fires = False
    if (alert.kind == "incoming_above" and tx.direction == "in") or (
        alert.kind == "outgoing_above" and tx.direction == "out"
    ):
        if alert.threshold_amount is not None and tx.native_amount >= Decimal(
            str(alert.threshold_amount)
        ):
            fires = True
    elif alert.kind == "activity":
        fires = True
    elif alert.kind == "token_transfer":
        fires = tx.token_contract is not None
    elif alert.kind == "balance_above":
        # Not applicable to a single tx
        return None
    if not fires:
        return None
    sig = _event_signature(alert.id, tx.id, alert.kind)
    # INSERT ... ON CONFLICT DO NOTHING (idempotent delivery)
    existing = await db.execute(
        select(AlertDelivery).where(
            AlertDelivery.alert_id == alert.id,
            AlertDelivery.event_signature == sig,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return None
    delivery = AlertDelivery(alert_id=alert.id, event_signature=sig, channel="telegram")
    db.add(delivery)
    await db.flush()
    return delivery


async def list_alerts_for_wallet(db: AsyncSession, *, wallet_id: uuid.UUID) -> list[Alert]:
    res = await db.execute(
        select(Alert).where(Alert.wallet_id == wallet_id, Alert.is_active.is_(True))
    )
    return list(res.scalars().all())
