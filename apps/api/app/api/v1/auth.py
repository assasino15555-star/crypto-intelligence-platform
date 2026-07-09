"""Auth routes: Telegram initData login + logout + current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.errors import AuthError
from ...core.logging import get_logger
from ...models.user import User
from ...schemas.models import CurrentUser, InitDataLogin, SessionOut
from ...security.telegram import InitDataError, verify_init_data
from ...services.users import create_session, revoke_session, upsert_user_by_telegram
from ...utils.rate_limit import LOGIN_LIMITER, client_key
from ..deps import get_current_user, get_db
from ..middleware import get_request_id

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)


@router.post("/login", response_model=SessionOut)
async def login(
    payload: InitDataLogin, request: Request, db: AsyncSession = Depends(get_db)
) -> SessionOut:
    rid = get_request_id()
    LOGIN_LIMITER.consume(client_key(request))
    try:
        verified = verify_init_data(payload.init_data)
    except InitDataError as exc:
        log.info("auth failed rid=%s reason=%s", rid, exc)
        raise AuthError(str(exc)) from exc
    user = await upsert_user_by_telegram(db, verified.user)
    token, exp = await create_session(db, user)
    await db.commit()
    log.info("auth ok rid=%s uid=%s tg=%s", rid, user.id, user.telegram_id)
    return SessionOut(access_token=token, expires_in=exp)


@router.get("/me", response_model=CurrentUser)
async def me(user: User = Depends(get_current_user)) -> CurrentUser:
    return CurrentUser.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    auth_header = request.headers.get("Authorization", "")
    parts = auth_header.split(" ", 1)
    if len(parts) == 2:
        await revoke_session(db, parts[1].strip())
        await db.commit()
