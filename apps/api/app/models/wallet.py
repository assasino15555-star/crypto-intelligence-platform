from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.session import Base

if TYPE_CHECKING:
    from .token_holding import TokenHolding
    from .transaction import Transaction
    from .user import User


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", "chain", "address", name="uq_wallet_user_chain_address"),
        CheckConstraint("label IS NULL OR length(label) <= 64", name="ck_wallet_label_len"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    address_type: Mapped[str] = mapped_column(String(16), nullable=False, default="evm")
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    native_symbol: Mapped[str] = mapped_column(String(16), nullable=False, default="ETH")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_native_amount: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    last_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    last_risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="wallets")
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan"
    )
    holdings: Mapped[list[TokenHolding]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list[WalletSnapshot]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan"
    )


class WalletSnapshot(Base):
    __tablename__ = "wallet_snapshots"
    __table_args__ = (Index("ix_wallet_snap_wallet_ts", "wallet_id", "taken_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    native_amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    native_usd_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    native_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    tokens_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    total_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    tokens_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    wallet: Mapped[Wallet] = relationship(back_populates="snapshots")
