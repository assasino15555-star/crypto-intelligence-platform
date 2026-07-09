"""SQLAlchemy ORM models.

Schema design notes:
  * UUIDs for all primary keys (no sequential IDs leaking scale info).
  * UTC timestamps via `DateTime(timezone=True)` and `func.now()`.
  * Unique constraints at the DB level prevent duplicates (user+chain+address,
    tx_hash per wallet, alert delivery per (alert, event_signature)).
  * ON DELETE CASCADE where children cannot exist without parent.
"""

from __future__ import annotations

from .ai_cache import AiAnalysis
from .alert import Alert, AlertDelivery
from .audit import AuditEvent
from .provider_sync import ProviderSyncState
from .token_holding import TokenHolding
from .transaction import Transaction
from .user import User
from .wallet import Wallet, WalletSnapshot
from .wallet_session import WalletSession

__all__ = [
    "AiAnalysis",
    "Alert",
    "AlertDelivery",
    "AuditEvent",
    "ProviderSyncState",
    "TokenHolding",
    "Transaction",
    "User",
    "Wallet",
    "WalletSession",
    "WalletSnapshot",
]
