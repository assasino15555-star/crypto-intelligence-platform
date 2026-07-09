from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
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
    from .wallet import Wallet


class TokenHolding(Base):
    __tablename__ = "token_holdings"
    __table_args__ = (
        UniqueConstraint("wallet_id", "contract", name="uq_holding_wallet_contract"),
        Index("ix_holding_wallet", "wallet_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False
    )
    contract: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    decimals: Mapped[int] = mapped_column(Integer, nullable=False, default=18)
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    usd_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    estimated_usd_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    wallet: Mapped[Wallet] = relationship(back_populates="holdings")
