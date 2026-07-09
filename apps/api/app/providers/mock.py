"""Mock provider used in tests and local development.

Never enabled in production (Settings._enforce_production_constraints rejects it).
"""

from __future__ import annotations

from decimal import Decimal

from shared.chains import Chain
from shared.domain import (
    AddressType,
    NormalizedAddress,
    ParsedTx,
    PortfolioSummary,
    TokenHolding,
    TxDirection,
    WalletBalance,
    WalletRiskLevel,
)

from ..core.errors import ProviderPermanentError
from ..utils.addresses import is_evm_address, to_eip55
from .base import BlockchainProvider


# Deterministic mock data keyed by address suffix (last 4 chars) so tests can be reproducible.
class MockProvider(BlockchainProvider):
    name = "mock"

    async def validate_address(self, chain: str, address: str) -> NormalizedAddress:
        if chain not in Chain.values():
            raise ProviderPermanentError(f"unsupported chain: {chain}")
        if not is_evm_address(address):
            raise ProviderPermanentError("invalid evm address")
        normalized = to_eip55(address)
        return NormalizedAddress(
            chain=chain,
            address=normalized,
            address_type=AddressType.EVM,
            display=normalized,
        )

    async def fetch_balance(self, chain: str, address: str) -> WalletBalance:
        return WalletBalance(
            native_symbol="ETH",
            native_decimals=18,
            native_amount=Decimal("1.234"),
            native_usd_price=Decimal("2500.00"),
            estimated_usd_value=Decimal("3085.00"),
        )

    async def fetch_token_holdings(self, chain: str, address: str) -> list[TokenHolding]:
        return [
            TokenHolding(
                contract="0x" + "11" * 20,
                symbol="USDC",
                name="USD Coin",
                decimals=6,
                amount=Decimal("100.00"),
                usd_price=Decimal("1.00"),
                estimated_usd_value=Decimal("100.00"),
            ),
            TokenHolding(
                contract="0x" + "22" * 20,
                symbol="WETH",
                name="Wrapped Ether",
                decimals=18,
                amount=Decimal("0.5"),
                usd_price=Decimal("2500.00"),
                estimated_usd_value=Decimal("1250.00"),
            ),
        ]

    async def fetch_recent_transactions(
        self, chain: str, address: str, *, limit: int = 50
    ) -> list[ParsedTx]:
        addr_l = address.lower()
        return [
            ParsedTx(
                tx_hash="0x" + "a" * 64,
                block=18_000_000,
                timestamp=1_700_000_000,
                direction=TxDirection.IN,
                counterparty="0x" + "ff" * 20,
                native_amount=Decimal("0.5"),
                native_symbol="ETH",
                status="ok",
                risk=WalletRiskLevel.LOW,
                risk_reasons=[],
            ),
            ParsedTx(
                tx_hash="0x" + "b" * 64,
                block=18_000_010,
                timestamp=1_700_000_100,
                direction=TxDirection.OUT,
                counterparty=addr_l,  # SELF to make tests cover SELF direction
                native_amount=Decimal("0.1"),
                native_symbol="ETH",
                status="ok",
                risk=WalletRiskLevel.MEDIUM,
                risk_reasons=["large_value"],
            ),
            ParsedTx(
                tx_hash="0x" + "c" * 64,
                block=18_000_020,
                timestamp=1_700_000_200,
                direction=TxDirection.OUT,
                counterparty="0x" + "ee" * 20,
                native_amount=Decimal("0.0"),
                native_symbol="ETH",
                status="failed",
                risk=WalletRiskLevel.HIGH,
                risk_reasons=["failed_transaction", "large_value"],
                token_symbol="USDC",
                token_amount=Decimal("10.0"),
                token_contract="0x" + "11" * 20,
            ),
        ]

    async def fetch_portfolio_summary(self, chain: str, address: str) -> PortfolioSummary:
        balance = await self.fetch_balance(chain, address)
        tokens = await self.fetch_token_holdings(chain, address)
        tokens_usd = sum((t.estimated_usd_value or Decimal(0) for t in tokens), Decimal(0))
        return PortfolioSummary(
            native_usd=balance.estimated_usd_value,
            tokens_usd=tokens_usd,
            total_usd=(balance.estimated_usd_value or Decimal(0)) + tokens_usd,
            tokens_count=len(tokens),
            as_of=1_700_000_200,
        )

    async def aclose(self) -> None:
        return None
