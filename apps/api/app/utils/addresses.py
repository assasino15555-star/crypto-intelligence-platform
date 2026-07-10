from __future__ import annotations

import re

from shared.chains import Chain
from shared.domain import AddressType, NormalizedAddress

from ..core.errors import ValidationError

_EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def is_evm_address(address: str) -> bool:
    return bool(address and _EVM_RE.match(address))


def to_eip55(address: str) -> str:
    if not is_evm_address(address):
        raise ValidationError("invalid evm address")
    addr_lower = address.lower().removeprefix("0x")
    from eth_hash.auto import keccak

    hash_hex = keccak(addr_lower.encode("ascii")).hex()
    out = ["0x"]
    for i, ch in enumerate(addr_lower):
        if ch in "0123456789":
            out.append(ch)
        else:
            out.append(ch.upper() if int(hash_hex[i], 16) >= 8 else ch)
    return "".join(out)


def validate_address(chain: str, address: str) -> NormalizedAddress:
    if not address or not isinstance(address, str):
        raise ValidationError("empty address")
    if chain not in Chain.values():
        raise ValidationError(f"unsupported chain: {chain}")
    if not is_evm_address(address):
        raise ValidationError("address must be a 0x-prefixed 40-hex EVM address")
    normalized = to_eip55(address)
    return NormalizedAddress(
        chain=chain,
        address=normalized,
        address_type=AddressType.EVM,
        display=normalized,
    )
