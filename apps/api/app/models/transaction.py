from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.session import Base

if TYPE_CHECKING:
    from .wallet import Wallet


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("wallet_id", "tx_hash", name="uq_tx_wallet_hash"),
        Index("ix_tx_wallet_ts", "wallet_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tx_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    block: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    counterparty: Mapped[str] = mapped_column(String(128), nullable=False)
    native_amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    native_symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    token_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_contract: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_amount: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    risk_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    wallet: Mapped[Wallet] = relationship(back_populates="transactions")
