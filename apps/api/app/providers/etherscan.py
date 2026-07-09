"""Etherscan provider (Ethereum mainnet and Base via API subdomain).

API key is required and read from settings.BLOCKCHAIN_API_KEY.
Base URL defaults to https://api.etherscan.io/api but can be overridden per
chain via BLOCKCHAIN_BASE_URL_<CHAIN_UPPER>. The override URL must be HTTPS,
no credentials, and must NOT point to private/loopback ranges — see
apps/api/app/utils/url_safety.py.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import httpx
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

from ..core.config import get_settings
from ..core.errors import ProviderPermanentError, ProviderRetryableError
from ..core.logging import get_logger
from ..utils.addresses import is_evm_address, to_eip55
from ..utils.http_retry import HttpRetry
from ..utils.url_safety import assert_safe_outbound_url
from .base import BlockchainProvider

log = get_logger(__name__)

_BASE_URLS: dict[str, str] = {
    Chain.ETHEREUM.value: "https://api.etherscan.io/api",
    Chain.BASE.value: "https://api.basescan.org/api",
}


class EtherscanProvider(BlockchainProvider):
    name = "etherscan"

    def __init__(self) -> None:
        s = get_settings()
        self._api_key = s.blockchain_api_key
        if not self._api_key:
            raise ProviderPermanentError("etherscan requires BLOCKCHAIN_API_KEY")
        self._retry = HttpRetry()
        override = (s.blockchain_base_url or "").strip()
        if override:
            assert_safe_outbound_url(override)
            # Apply the same override to all supported chains (configured deployment)
            for k in _BASE_URLS:
                _BASE_URLS[k] = override
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                follow_redirects=False,  # prevent SSRF via redirect
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _url(self, chain: str) -> str:
        base = _BASE_URLS.get(chain)
        if not base:
            raise ProviderPermanentError(f"unsupported chain for etherscan: {chain}")
        return base

    async def _get(self, chain: str, params: dict[str, str]) -> dict[str, Any]:
        client = await self._get_client()
        params = {**params, "apikey": self._api_key}
        resp = await self._retry.request(client, "GET", self._url(chain), params=params)
        try:
            data: dict[str, Any] = resp.json()
        except ValueError as exc:
            raise ProviderPermanentError("non-json provider response") from exc
        status = data.get("status")
        if str(status) == "0" and data.get("message") == "NOTOK":
            # Etherscan returns status=0 with NOTOK for rate limit / errors
            result_text = str(data.get("result", "")).lower()
            if "rate limit" in result_text:
                raise ProviderRetryableError("etherscan rate limited")
            raise ProviderPermanentError(f"etherscan error: {data.get('result', '')[:200]}")
        return data

    async def validate_address(self, chain: str, address: str) -> NormalizedAddress:
        if chain not in _BASE_URLS:
            raise ProviderPermanentError(f"unsupported chain for etherscan: {chain}")
        if not is_evm_address(address):
            raise ProviderPermanentError("invalid evm address")
        return NormalizedAddress(
            chain=chain,
            address=to_eip55(address),
            address_type=AddressType.EVM,
            display=to_eip55(address),
        )

    async def fetch_balance(self, chain: str, address: str) -> WalletBalance:
        data = await self._get(
            chain,
            {
                "module": "account",
                "action": "balance",
                "address": address,
                "tag": "latest",
            },
        )
        raw = data.get("result", "0")
        try:
            wei = int(raw)
        except (TypeError, ValueError) as exc:
            raise ProviderPermanentError("invalid balance response") from exc
        amount = Decimal(wei) / Decimal(10) ** 18
        return WalletBalance(
            native_symbol="ETH",
            native_decimals=18,
            native_amount=amount,
            native_usd_price=None,
            estimated_usd_value=None,
        )

    async def fetch_token_holdings(self, chain: str, address: str) -> list[TokenHolding]:
        data = await self._get(
            chain,
            {
                "module": "account",
                "action": "tokentx",
                "address": address,
                "page": "1",
                "offset": "100",
                "sort": "desc",
            },
        )
        items = data.get("result")
        if not isinstance(items, list):
            return []
        # Aggregate transfers into net balance per token contract.
        per_token: dict[str, dict[str, Any]] = {}
        for it in items:
            contract = it.get("contractAddress")
            if not contract:
                continue
            decimals = int(it.get("tokenDecimal", "18") or "18")
            try:
                value = int(it.get("value", "0"))
            except ValueError:
                continue
            entry = per_token.setdefault(
                contract,
                {
                    "amount": Decimal(0),
                    "symbol": it.get("tokenSymbol", "?"),
                    "name": it.get("tokenName", ""),
                    "decimals": decimals,
                },
            )
            if (it.get("to") or "").lower() == address.lower():
                entry["amount"] += Decimal(value) / Decimal(10) ** decimals
            else:
                entry["amount"] -= Decimal(value) / Decimal(10) ** decimals
        holdings: list[TokenHolding] = []
        for contract, e in per_token.items():
            if e["amount"] <= 0:
                continue
            holdings.append(
                TokenHolding(
                    contract=to_eip55(contract),
                    symbol=str(e["symbol"])[:64],
                    name=str(e["name"])[:128],
                    decimals=int(e["decimals"]),
                    amount=e["amount"],
                )
            )
        return holdings

    async def fetch_recent_transactions(
        self, chain: str, address: str, *, limit: int = 50
    ) -> list[ParsedTx]:
        # Native ETH transactions
        normal = await self._get(
            chain,
            {
                "module": "account",
                "action": "txlist",
                "address": address,
                "page": "1",
                "offset": str(min(limit, 200)),
                "sort": "desc",
            },
        )
        items = normal.get("result")
        out: list[ParsedTx] = []
        if not isinstance(items, list):
            return out
        addr_l = address.lower()
        for it in items:
            try:
                value_wei = int(it.get("value", "0"))
            except ValueError:
                continue
            if value_wei <= 0:
                continue
            amount = Decimal(value_wei) / Decimal(10) ** 18
            frm = it.get("from", "")
            to = it.get("to", "")
            if frm.lower() == addr_l and to.lower() == addr_l:
                direction = TxDirection.SELF
                counterparty = to
            elif frm.lower() == addr_l:
                direction = TxDirection.OUT
                counterparty = to
            else:
                direction = TxDirection.IN
                counterparty = frm
            ts = int(it.get("timeStamp", "0"))
            status = "ok" if it.get("isError") == "0" else "failed"
            risk, reasons = _assess_risk(it, amount)
            out.append(
                ParsedTx(
                    tx_hash=str(it.get("hash", "")),
                    block=int(it.get("blockNumber", "0") or "0"),
                    timestamp=ts,
                    direction=direction,
                    counterparty=counterparty,
                    native_amount=amount,
                    native_symbol="ETH",
                    status=status,
                    risk=risk,
                    risk_reasons=reasons,
                )
            )
        return out[:limit]

    async def fetch_portfolio_summary(self, chain: str, address: str) -> PortfolioSummary:
        balance, holdings = await asyncio.gather(
            self.fetch_balance(chain, address),
            self.fetch_token_holdings(chain, address),
        )
        tokens_usd: Decimal | None = None
        native_usd = balance.estimated_usd_value
        return PortfolioSummary(
            native_usd=native_usd,
            tokens_usd=tokens_usd,
            total_usd=native_usd if tokens_usd is None else (native_usd or Decimal(0)) + tokens_usd,
            tokens_count=len(holdings),
            as_of=0,
        )


def _assess_risk(tx: dict[str, Any], amount: Decimal) -> tuple[WalletRiskLevel, list[str]]:
    reasons: list[str] = []
    if tx.get("isError") and tx.get("isError") != "0":
        reasons.append("failed_transaction")
    if amount > Decimal("1000"):
        reasons.append("large_value")
    # Heuristic: counterparty is a known mixer / suspicious pattern would require external data
    # We avoid faking risk — only flag clear on-chain anomalies.
    if len(reasons) >= 2:
        return WalletRiskLevel.HIGH, reasons
    if reasons:
        return WalletRiskLevel.MEDIUM, reasons
    return WalletRiskLevel.LOW, reasons
