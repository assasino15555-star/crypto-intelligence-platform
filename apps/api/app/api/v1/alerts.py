"""Alert routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.user import User
from ...schemas.models import AlertCreate, AlertOut, AlertUpdate, Page, PageMeta
from ...services.alerts import (
    ALLOWED_KINDS,
    create_alert,
    delete_alert,
    list_alerts,
    update_alert,
)
from ..deps import Pagination, get_current_user, get_db, pagination

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("", response_model=AlertOut, status_code=201)
async def post_alert(
    payload: AlertCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertOut:
    alert = await create_alert(
        db,
        user_id=user.id,
        wallet_id=payload.wallet_id,
        kind=payload.kind,
        threshold_amount=payload.threshold_amount,
        note=payload.note,
    )
    await db.commit()
    await db.refresh(alert)
    return AlertOut.model_validate(alert)


@router.get("", response_model=Page)
async def get_alerts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pg: Pagination = Depends(pagination),
) -> Page:
    items, total = await list_alerts(db, user_id=user.id, page=pg.page, page_size=pg.page_size)
    return Page(
        items=[AlertOut.model_validate(a).model_dump() for a in items],
        meta=PageMeta(page=pg.page, page_size=pg.page_size, total=total),
    )


@router.patch("/{alert_id}", response_model=AlertOut)
async def patch_alert(
    alert_id: UUID,
    payload: AlertUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertOut:
    alert = await update_alert(
        db,
        user_id=user.id,
        alert_id=alert_id,
        is_active=payload.is_active,
        threshold_amount=payload.threshold_amount,
        note=payload.note,
    )
    await db.commit()
    await db.refresh(alert)
    return AlertOut.model_validate(alert)


@router.delete("/{alert_id}", status_code=204)
async def delete_alert_route(
    alert_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await delete_alert(db, user_id=user.id, alert_id=alert_id)
    await db.commit()


@router.get("/kinds", response_model=list[str])
async def list_kinds() -> list[str]:
    return sorted(ALLOWED_KINDS)
