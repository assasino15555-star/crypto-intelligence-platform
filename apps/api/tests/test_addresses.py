"""Address validation and EIP-55 normalization tests."""

from __future__ import annotations

import pytest

from apps.api.app.core.errors import ValidationError
from apps.api.app.utils.addresses import is_evm_address, to_eip55, validate_address


def test_is_evm_address_accepts_valid():
    assert is_evm_address("0x" + "ab" * 20)


def test_is_evm_address_rejects_short():
    assert not is_evm_address("0x1234")


def test_is_evm_address_rejects_non_hex():
    assert not is_evm_address("0x" + "zz" * 20)


def test_is_evm_address_rejects_empty():
    assert not is_evm_address("")
    assert not is_evm_address(None)  # type: ignore[arg-type]


def test_to_eip55_matches_known_vector():
    # Vitalik's address — known EIP-55 checksum from the spec
    addr = "0x52908400098527886e0f7030069857d2e4169ee7"
    expected = "0x52908400098527886E0F7030069857D2E4169EE7"
    assert to_eip55(addr) == expected


def test_validate_address_normalizes():
    addr = "0x" + "ab" * 20
    res = validate_address("ethereum", addr)
    assert res.chain == "ethereum"
    assert res.address == to_eip55(addr)
    assert res.address_type == "evm"


def test_validate_address_rejects_unsupported_chain():
    with pytest.raises(ValidationError):
        validate_address("solana", "0x" + "ab" * 20)


def test_validate_address_rejects_invalid_format():
    with pytest.raises(ValidationError):
        validate_address("ethereum", "not-an-address")


def test_validate_address_rejects_empty():
    with pytest.raises(ValidationError):
        validate_address("ethereum", "")
