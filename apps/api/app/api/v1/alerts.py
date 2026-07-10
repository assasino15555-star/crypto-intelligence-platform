from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.errors import ConflictError, NotFoundError, ValidationError
from ...models.alert import Alert
from ...models.user import User
from ...schemas.models import AlertCreate, AlertOut, AlertUpdate, Page, PageMeta
from ...utils.rate_limit import ALERT_CREATE_USER, make_limiter
from ..deps import Pagination, get_current_user, get_db, pagination
from ..v1.wallets import _get_owned_wallet

router = APIRouter(prefix="/alerts", tags=["alerts"])

ALLOWED_KINDS = {"incoming_above", "outgoing_above", "activity", "balance_above", "token_transfer"}


@router.post("", response_model=AlertOut, status_code=201)
async def post_alert(
    payload: AlertCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertOut:
    if payload.kind not in ALLOWED_KINDS:
        raise ValidationError(f"invalid alert kind: {payload.kind}")
    if (
        payload.kind in {"incoming_above", "outgoing_above", "balance_above"}
        and payload.threshold_amount is None
    ):
        raise ValidationError(f"{payload.kind} requires threshold_amount")

    limiter = make_limiter(ALERT_CREATE_USER)
    await limiter.check(f"alert_create:{user.id}")

    await _get_owned_wallet(db, user_id=user.id, wallet_id=payload.wallet_id)

    settings = get_settings()
    count_q = await db.execute(
        select(func.count()).select_from(Alert).where(Alert.user_id == user.id)
    )
    alert_count = int(count_q.scalar_one() or 0)
    if alert_count >= settings.max_alerts_per_user:
        raise ConflictError("alert quota exceeded")

    alert = Alert(
        user_id=user.id,
        wallet_id=payload.wallet_id,
        kind=payload.kind,
        threshold_amount=payload.threshold_amount,
        note=payload.note,
    )
    db.add(alert)
    await db.flush()
    await db.commit()
    await db.refresh(alert)
    return AlertOut.model_validate(alert)


@router.get("", response_model=Page)
async def get_alerts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pg: Pagination = Depends(pagination),
) -> Page:
    total_q = await db.execute(
        select(func.count()).select_from(Alert).where(Alert.user_id == user.id)
    )
    total = int(total_q.scalar_one() or 0)
    res = await db.execute(
        select(Alert)
        .where(Alert.user_id == user.id)
        .order_by(Alert.created_at.desc())
        .offset(pg.offset)
        .limit(pg.page_size)
    )
    items = list(res.scalars().all())
    return Page(
        items=[AlertOut.model_validate(a).model_dump() for a in items],
        meta=PageMeta(page=pg.page, page_size=pg.page_size, total=total),
    )


@router.patch("/{alert_id}", response_model=AlertOut)
async def patch_alert(
    alert_id: uuid.UUID,
    payload: AlertUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertOut:
    res = await db.execute(select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id))
    alert = res.scalar_one_or_none()
    if alert is None:
        raise NotFoundError("alert")
    if payload.is_active is not None:
        alert.is_active = payload.is_active
    if payload.threshold_amount is not None:
        alert.threshold_amount = payload.threshold_amount
    if payload.note is not None:
        alert.note = payload.note
    await db.flush()
    await db.commit()
    await db.refresh(alert)
    return AlertOut.model_validate(alert)


@router.delete("/{alert_id}", status_code=204)
async def delete_alert_route(
    alert_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    res = await db.execute(select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id))
    alert = res.scalar_one_or_none()
    if alert is None:
        raise NotFoundError("alert")
    await db.delete(alert)
    await db.flush()
    await db.commit()


@router.get("/kinds", response_model=list[str])
async def list_kinds() -> list[str]:
    return sorted(ALLOWED_KINDS)
