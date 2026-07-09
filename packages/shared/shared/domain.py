"""Normalized domain models returned by blockchain providers.

Provider implementations must translate their own response formats into these
types so that the rest of the application never depends on a specific vendor's
JSON schema.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class AddressType(StrEnum):
    EVM = "evm"


class NormalizedAddress(BaseModel):
    chain: str
    address: str
    address_type: AddressType
    display: str


class TxDirection(StrEnum):
    IN = "in"
    OUT = "out"
    SELF = "self"


class WalletRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WalletBalance(BaseModel):
    native_symbol: str
    native_decimals: int
    native_amount: Decimal
    native_usd_price: Decimal | None = None
    estimated_usd_value: Decimal | None = None


class TokenHolding(BaseModel):
    contract: str
    symbol: str
    name: str
    decimals: int
    amount: Decimal
    usd_price: Decimal | None = None
    estimated_usd_value: Decimal | None = None


class ParsedTx(BaseModel):
    tx_hash: str
    block: int | None = None
    timestamp: int
    direction: TxDirection
    counterparty: str
    native_amount: Decimal
    native_symbol: str
    status: str = "ok"
    token_symbol: str | None = None
    token_amount: Decimal | None = None
    token_contract: str | None = None
    risk: WalletRiskLevel = WalletRiskLevel.LOW
    risk_reasons: list[str] = Field(default_factory=list)


class PortfolioSummary(BaseModel):
    native_usd: Decimal | None
    tokens_usd: Decimal | None
    total_usd: Decimal | None
    tokens_count: int
    as_of: int
