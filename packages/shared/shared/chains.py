from __future__ import annotations

from enum import StrEnum


class Chain(StrEnum):
    ETHEREUM = "ethereum"
    BASE = "base"

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]
