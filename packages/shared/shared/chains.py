"""Supported blockchain identifiers.

Adding a new chain requires:
  1. Add an enum member here.
  2. Implement a provider that maps Chain -> external API in apps/api/app/providers/.
  3. Document the chain in README under "Supported functionality".
"""

from __future__ import annotations

from enum import StrEnum


class Chain(StrEnum):
    ETHEREUM = "ethereum"
    BASE = "base"

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]
