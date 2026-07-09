"""SQLAlchemy ORM models.

Schema design notes:
  * UUIDs for all primary keys (no sequential IDs leaking scale info).
  * UTC timestamps via `DateTime(timezone=True)` and `func.now()`.
  * Unique constraints at the DB level prevent duplicates (user+chain+address,
    tx_hash per wallet, alert delivery per (alert, event_signature)).
  * ON DELETE CASCADE where children cannot exist without parent.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.session import Base

if TYPE_CHECKING:
    from .alert import Alert
    from .audit import AuditEvent
    from .wallet import Wallet
    from .wallet_session import WalletSession


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    telegram_first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    telegram_last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    telegram_language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    wallets: Mapped[list[Wallet]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    alerts: Mapped[list[Alert]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list[WalletSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


__all__ = ["User"]
