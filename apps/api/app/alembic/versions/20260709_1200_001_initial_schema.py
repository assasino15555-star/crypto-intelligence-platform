"""initial schema

Revision ID: 20260709_1200_001_initial_schema
Revises:
Create Date: 2026-07-09 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260709_1200_001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(128), nullable=True),
        sa.Column("telegram_first_name", sa.String(128), nullable=True),
        sa.Column("telegram_last_name", sa.String(128), nullable=True),
        sa.Column("telegram_language_code", sa.String(16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "wallets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chain", sa.String(32), nullable=False),
        sa.Column("address", sa.String(128), nullable=False),
        sa.Column("address_type", sa.String(16), nullable=False, server_default="evm"),
        sa.Column("label", sa.String(64), nullable=True),
        sa.Column("native_symbol", sa.String(16), nullable=False, server_default="ETH"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_native_amount", sa.Numeric(36, 18), nullable=True),
        sa.Column("last_total_usd", sa.Numeric(20, 4), nullable=True),
        sa.Column("last_risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("label IS NULL OR length(label) <= 64", name="ck_wallet_label_len"),
        sa.UniqueConstraint("user_id", "chain", "address", name="uq_wallet_user_chain_address"),
    )
    op.create_index("ix_wallets_user_id", "wallets", ["user_id"])

    op.create_table(
        "wallet_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("native_amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("native_usd_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("native_usd", sa.Numeric(20, 4), nullable=True),
        sa.Column("tokens_usd", sa.Numeric(20, 4), nullable=True),
        sa.Column("total_usd", sa.Numeric(20, 4), nullable=True),
        sa.Column("tokens_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_wallet_snap_wallet_ts", "wallet_snapshots", ["wallet_id", "taken_at"])

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tx_hash", sa.String(128), nullable=False),
        sa.Column("block", sa.BigInteger(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("counterparty", sa.String(128), nullable=False),
        sa.Column("native_amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("native_symbol", sa.String(16), nullable=False),
        sa.Column("token_symbol", sa.String(64), nullable=True),
        sa.Column("token_contract", sa.String(128), nullable=True),
        sa.Column("token_amount", sa.Numeric(36, 18), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("risk_reasons", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("wallet_id", "tx_hash", name="uq_tx_wallet_hash"),
    )
    op.create_index("ix_tx_wallet_ts", "transactions", ["wallet_id", "timestamp"])

    op.create_table(
        "token_holdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("contract", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("decimals", sa.Integer(), nullable=False, server_default="18"),
        sa.Column("amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("usd_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("estimated_usd_value", sa.Numeric(20, 4), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("wallet_id", "contract", name="uq_holding_wallet_contract"),
    )
    op.create_index("ix_holding_wallet", "token_holdings", ["wallet_id"])

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("threshold_amount", sa.Numeric(36, 18), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('incoming_above','outgoing_above','activity',"
            "'balance_above','token_transfer')",
            name="ck_alert_kind",
        ),
        sa.CheckConstraint(
            "threshold_amount IS NULL OR threshold_amount >= 0", name="ck_alert_threshold"
        ),
    )
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])
    op.create_index("ix_alerts_wallet_id", "alerts", ["wallet_id"])
    op.create_index("ix_alert_user_wallet", "alerts", ["user_id", "wallet_id"])

    op.create_table(
        "alert_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "alert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("alerts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_signature", sa.String(128), nullable=False),
        sa.Column(
            "delivered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("channel", sa.String(32), nullable=False, server_default="telegram"),
        sa.Column("status", sa.String(16), nullable=False, server_default="sent"),
        sa.UniqueConstraint("alert_id", "event_signature", name="uq_alert_event_delivery"),
    )

    op.create_table(
        "provider_sync_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False, server_default="tx"),
        sa.Column("cursor_value", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "wallet_id", "provider", "scope", name="uq_psync_wallet_provider_scope"
        ),
    )

    op.create_table(
        "ai_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "tx_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("input_signature", sa.String(128), nullable=False),
        sa.Column("input_summary", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("is_cached", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ai_wallet_kind", "ai_analyses", ["wallet_id", "kind"])
    op.create_index("ix_ai_tx_id", "ai_analyses", ["tx_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_events_event", "audit_events", ["event"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])

    op.create_table(
        "wallet_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "wallet_sessions", ["user_id"])
    op.create_index("ix_sessions_token_hash", "wallet_sessions", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("wallet_sessions")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_ai_tx_id", table_name="ai_analyses")
    op.drop_index("ix_ai_wallet_kind", table_name="ai_analyses")
    op.drop_table("ai_analyses")
    op.drop_table("provider_sync_state")
    op.drop_table("alert_deliveries")
    op.drop_index("ix_alert_user_wallet", table_name="alerts")
    op.drop_index("ix_alerts_wallet_id", table_name="alerts")
    op.drop_index("ix_alerts_user_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_holding_wallet", table_name="token_holdings")
    op.drop_table("token_holdings")
    op.drop_index("ix_tx_wallet_ts", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_wallet_snap_wallet_ts", table_name="wallet_snapshots")
    op.drop_table("wallet_snapshots")
    op.drop_index("ix_wallets_user_id", table_name="wallets")
    op.drop_table("wallets")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
