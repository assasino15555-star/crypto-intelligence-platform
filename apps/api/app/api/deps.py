from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.errors import AuthError, ValidationError
from ..db.session import get_session
from ..models.user import User
from ..services.users import get_user_from_token


async def get_db() -> AsyncIterator[AsyncSession]:
    async for s in get_session():
        yield s


def _extract_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthError("missing authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("invalid authorization scheme")
    token = parts[1].strip()
    if not token:
        raise AuthError("empty token")
    return token


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> User:
    settings = get_settings()
    if settings.dev_bypass_auth and settings.is_dev:
        res = await db.execute(select(User).where(User.telegram_id == 999999999))
        user = res.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=999999999,
                telegram_username="dev_user",
                telegram_first_name="Dev",
                telegram_last_name="User",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user
    token = _extract_token(authorization)
    user = await get_user_from_token(db, token)
    if user is None:
        raise AuthError("invalid or expired session")
    return user


class Pagination:
    def __init__(self, page: int = 1, page_size: int = 20) -> None:
        if page < 1:
            raise ValidationError("page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("page_size must be 1..100")
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Pagination:
    return Pagination(page=page, page_size=page_size)
