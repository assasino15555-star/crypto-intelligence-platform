from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.session import Base


class AiAnalysis(Base):
    """Bounded cache of AI explanations keyed by an idempotent input signature.

    Storing AI output here lets us:
      * avoid re-calling the model for the same wallet+state,
      * provide audit trail for what was sent and returned,
      * enforce size limits on stored output.
    """

    __tablename__ = "ai_analyses"
    __table_args__ = (Index("ix_ai_wallet_kind", "wallet_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    tx_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    input_signature: Mapped[str] = mapped_column(String(128), nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    is_cached: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
