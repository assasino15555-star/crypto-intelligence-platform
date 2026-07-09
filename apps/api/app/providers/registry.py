"""Provider factory."""

from __future__ import annotations

from ..core.config import get_settings
from .base import BlockchainProvider
from .etherscan import EtherscanProvider
from .mock import MockProvider

_provider: BlockchainProvider | None = None


def get_provider() -> BlockchainProvider:
    global _provider
    if _provider is None:
        s = get_settings()
        name = s.blockchain_provider
        if name == "etherscan":
            _provider = EtherscanProvider()
        elif name == "mock":
            _provider = MockProvider()
        else:
            raise ValueError(f"unknown BLOCKCHAIN_PROVIDER: {name}")
    return _provider


def reset_provider() -> None:
    global _provider
    _provider = None
