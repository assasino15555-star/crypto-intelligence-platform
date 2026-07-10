from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..models.user import User
from ..models.wallet_session import WalletSession
from ..security.session import hash_token, issue_token, verify_token
from ..security.telegram import TelegramUser

MAX_ACTIVE_SESSIONS_HARD_CAP = 10


async def upsert_user_by_telegram(db: AsyncSession, tg_user: TelegramUser) -> User:
    stmt = select(User).where(User.telegram_id == tg_user.id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=tg_user.id,
            telegram_username=tg_user.username,
            telegram_first_name=tg_user.first_name,
            telegram_last_name=tg_user.last_name,
            telegram_language_code=tg_user.language_code,
        )
        db.add(user)
        await db.flush()
    else:
        if (
            user.telegram_username != tg_user.username
            or user.telegram_first_name != tg_user.first_name
            or user.telegram_last_name != tg_user.last_name
            or user.telegram_language_code != tg_user.language_code
        ):
            user.telegram_username = tg_user.username
            user.telegram_first_name = tg_user.first_name
            user.telegram_last_name = tg_user.last_name
            user.telegram_language_code = tg_user.language_code
            await db.flush()
    return user


async def create_session(db: AsyncSession, user: User) -> tuple[str, int]:
    settings = get_settings()
    quota = min(settings.max_sessions_per_user, MAX_ACTIVE_SESSIONS_HARD_CAP)

    active_count_q = await db.execute(
        select(func.count())
        .select_from(WalletSession)
        .where(
            WalletSession.user_id == user.id,
            WalletSession.revoked_at.is_(None),
            WalletSession.expires_at > _dt.datetime.now(_dt.UTC),
        )
    )
    active_count = int(active_count_q.scalar_one() or 0)
    if active_count >= quota:
        await revoke_all_sessions(db, user_id=user.id)

    token, exp, token_hash = issue_token(user.id)
    session = WalletSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=_dt.datetime.fromtimestamp(exp, tz=_dt.UTC).replace(tzinfo=None),
    )
    db.add(session)
    await db.flush()
    return token, exp


async def get_user_from_token(db: AsyncSession, token: str) -> User | None:
    payload = verify_token(token)
    try:
        uid = uuid.UUID(payload.sub)
    except ValueError:
        return None
    thash = hash_token(token)
    stmt = select(WalletSession).where(
        WalletSession.token_hash == thash, WalletSession.revoked_at.is_(None)
    )
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if session is None:
        return None
    now = _dt.datetime.now(_dt.UTC)
    if session.expires_at <= now:
        return None
    user_stmt = select(User).where(User.id == uid, User.is_active.is_(True))
    ures = await db.execute(user_stmt)
    return ures.scalar_one_or_none()


async def revoke_session(db: AsyncSession, token: str) -> None:
    thash = hash_token(token)
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
    await db.execute(
        update(WalletSession)
        .where(
            WalletSession.token_hash == thash,
            WalletSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.flush()


async def revoke_all_sessions(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
    result = await db.execute(
        update(WalletSession)
        .where(
            WalletSession.user_id == user_id,
            WalletSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.flush()
    rowcount = getattr(result, "rowcount", 0)
    return int(rowcount or 0)


async def rotate_session(db: AsyncSession, token: str) -> tuple[str, int] | None:
    payload = verify_token(token)
    try:
        uid = uuid.UUID(payload.sub)
    except ValueError:
        return None
    await revoke_session(db, token)
    user_q = await db.execute(select(User).where(User.id == uid, User.is_active.is_(True)))
    user = user_q.scalar_one_or_none()
    if user is None:
        return None
    return await create_session(db, user)
