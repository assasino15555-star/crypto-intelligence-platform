"""User service: upsert from verified Telegram identity."""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from ..models.wallet_session import WalletSession
from ..security.session import hash_token, issue_token, verify_token
from ..security.telegram import TelegramUser


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
        # Update mutable fields if changed
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
    token, exp, token_hash = issue_token(user.id)
    session = WalletSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=_exp_to_dt(exp),
    )
    db.add(session)
    await db.flush()
    return token, exp


async def get_user_from_token(db: AsyncSession, token: str) -> User | None:
    payload = verify_token(token)  # raises TokenError on invalid
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
    if session.expires_at.replace(tzinfo=None) is None:
        return None
    if session.expires_at <= _dt.datetime.now(_dt.UTC):
        return None
    user_stmt = select(User).where(User.id == uid, User.is_active.is_(True))
    ures = await db.execute(user_stmt)
    return ures.scalar_one_or_none()


def _exp_to_dt(exp_unix: int) -> _dt.datetime:
    return _dt.datetime.fromtimestamp(exp_unix, tz=_dt.UTC).replace(tzinfo=None)


async def revoke_session(db: AsyncSession, token: str) -> None:
    thash = hash_token(token)
    stmt = select(WalletSession).where(WalletSession.token_hash == thash)
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if session is not None and session.revoked_at is None:
        session.revoked_at = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
        await db.flush()
