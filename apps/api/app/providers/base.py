"""Blockchain provider protocol and shared types.

Concrete providers must translate their vendor-specific response formats into
the normalized `shared.domain` types. The core domain must never depend on a
vendor's JSON schema.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from shared.domain import (
    NormalizedAddress,
    ParsedTx,
    PortfolioSummary,
    TokenHolding,
    WalletBalance,
)

from ..core.errors import ProviderError, ProviderRetryableError


@runtime_checkable
class BlockchainProvider(Protocol):
    name: str

    async def validate_address(self, chain: str, address: str) -> NormalizedAddress: ...

    async def fetch_balance(self, chain: str, address: str) -> WalletBalance: ...

    async def fetch_token_holdings(self, chain: str, address: str) -> list[TokenHolding]: ...

    async def fetch_recent_transactions(
        self, chain: str, address: str, *, limit: int = 50
    ) -> list[ParsedTx]: ...

    async def fetch_portfolio_summary(self, chain: str, address: str) -> PortfolioSummary: ...

    async def aclose(self) -> None: ...


__all__ = ["BlockchainProvider", "Iterable", "ProviderError", "ProviderRetryableError"]
