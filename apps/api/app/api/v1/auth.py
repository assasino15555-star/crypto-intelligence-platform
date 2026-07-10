from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.errors import AuthError, RateLimitError
from ...core.logging import get_logger
from ...db.session import get_redis
from ...models.user import User
from ...schemas.models import CurrentUser, InitDataLogin, SessionOut
from ...security.telegram import InitDataError, init_data_replay_key, verify_init_data
from ...services.users import (
    create_session,
    revoke_all_sessions,
    revoke_session,
    upsert_user_by_telegram,
)
from ...utils.rate_limit import LOGIN_IP, LOGIN_USER, make_limiter, trusted_client_ip
from ..deps import get_current_user, get_db
from ..middleware import get_request_id

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)


@router.post("/login", response_model=SessionOut)
async def login(
    payload: InitDataLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    rid = get_request_id()
    ip_limiter = make_limiter(LOGIN_IP)
    await ip_limiter.check(f"login:ip:{trusted_client_ip(request)}")

    try:
        verified = verify_init_data(payload.init_data)
    except InitDataError:
        log.info("auth failed rid=%s", rid)
        raise AuthError("authentication failed") from None

    redis = get_redis()
    replay_key = f"initdata:used:{init_data_replay_key(verified)}"
    try:
        set_result = await redis.set(replay_key, b"1", ex=300, nx=True)
    except Exception as exc:
        log.warning("replay check redis error: %s", exc)
        raise RateLimitError("replay check unavailable", retry_after=5) from exc
    if not set_result:
        log.info("auth replay blocked rid=%s uid=%s", rid, verified.user.id)
        raise AuthError("authentication failed")

    user_limiter = make_limiter(LOGIN_USER)
    await user_limiter.check(f"login:user:{verified.user.id}")

    user = await upsert_user_by_telegram(db, verified.user)
    token, exp = await create_session(db, user)
    await db.commit()
    log.info("auth ok rid=%s uid=%s tg=%s", rid, user.id, user.telegram_id)
    return SessionOut(access_token=token, expires_in=exp - int(time.time()))


@router.get("/me", response_model=CurrentUser)
async def me(user: User = Depends(get_current_user)) -> CurrentUser:
    return CurrentUser.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    from ..deps import _extract_token

    token = _extract_token(request.headers.get("Authorization", ""))
    await revoke_session(db, token)
    await db.commit()


@router.post("/revoke-all", status_code=204)
async def revoke_all(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await revoke_all_sessions(db, user_id=user.id)
    await db.commit()
