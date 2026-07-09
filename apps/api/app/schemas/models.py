from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Auth ----
class InitDataLogin(BaseModel):
    init_data: str = Field(min_length=10, max_length=8192)


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class CurrentUser(ORMModel):
    id: UUID
    telegram_id: int
    telegram_username: str | None
    telegram_first_name: str | None
    telegram_last_name: str | None
    is_active: bool


# ---- Wallets ----
class WalletCreate(BaseModel):
    chain: str = Field(min_length=1, max_length=32)
    address: str = Field(min_length=4, max_length=128)
    label: str | None = Field(default=None, max_length=64)


class WalletUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class WalletOut(ORMModel):
    id: UUID
    chain: str
    address: str
    label: str | None
    native_symbol: str
    is_active: bool
    last_synced_at: datetime | None
    last_native_amount: Decimal | None
    last_total_usd: Decimal | None
    last_risk_level: str
    created_at: datetime
    updated_at: datetime


class WalletWithSummary(WalletOut):
    native_amount: Decimal | None = None
    native_usd: Decimal | None = None
    total_usd: Decimal | None = None
    tokens_count: int = 0
    risk_level: str = "low"


class TokenHoldingOut(ORMModel):
    contract: str
    symbol: str
    name: str
    decimals: int
    amount: Decimal
    usd_price: Decimal | None
    estimated_usd_value: Decimal | None
    updated_at: datetime


class TransactionOut(ORMModel):
    id: UUID
    tx_hash: str
    block: int | None
    timestamp: datetime
    direction: str
    counterparty: str
    native_amount: Decimal
    native_symbol: str
    token_symbol: str | None
    token_contract: str | None
    token_amount: Decimal | None
    status: str
    risk_level: str
    risk_reasons: list[str] = Field(default_factory=list)


class WalletSnapshotOut(ORMModel):
    id: UUID
    taken_at: datetime
    native_amount: Decimal
    native_usd: Decimal | None
    tokens_usd: Decimal | None
    total_usd: Decimal | None
    tokens_count: int


# ---- Alerts ----
class AlertCreate(BaseModel):
    wallet_id: UUID
    kind: str = Field(min_length=1, max_length=32)
    threshold_amount: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=512)


class AlertUpdate(BaseModel):
    is_active: bool | None = None
    threshold_amount: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=512)


class AlertOut(ORMModel):
    id: UUID
    wallet_id: UUID
    kind: str
    threshold_amount: float | None
    is_active: bool
    note: str | None
    created_at: datetime
    updated_at: datetime


# ---- AI ----
class AiExplainRequest(BaseModel):
    wallet_id: UUID | None = None
    tx_id: UUID | None = None
    kind: str = Field(default="wallet_summary", min_length=1, max_length=32)


class AiExplanationOut(BaseModel):
    explanation: str
    model: str
    is_cached: bool
    input_summary: str


# ---- Pagination ----
class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int


class Page(BaseModel):
    items: list[object]
    meta: PageMeta
