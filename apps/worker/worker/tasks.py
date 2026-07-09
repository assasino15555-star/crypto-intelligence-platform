"""Taskiq broker and tasks definition.

Tasks are idempotent: re-running a sync task for the same wallet will produce
the same DB state thanks to unique constraints on (wallet_id, tx_hash) and
(alert_id, event_signature).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.errors import (
    ProviderError,
    ProviderPermanentError,
    ProviderRetryableError,
)
from apps.api.app.core.logging import configure_logging, get_logger
from apps.api.app.db.session import session_scope
from apps.api.app.models.alert import Alert, AlertDelivery
from apps.api.app.models.transaction import Transaction
from apps.api.app.models.wallet import Wallet, WalletSnapshot
from apps.api.app.providers.registry import get_provider
from apps.api.app.services.alerts import (
    evaluate_alert_for_tx,
    list_alerts_for_wallet,
)

log = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class _InMemoryBroker:
    """Minimal in-process broker for tests; production uses TaskiqRedisBroker.

    Tasks are awaited directly. This is sufficient for our test suite and for
    local single-process runs. The Redis broker is wired separately for
    production-like behavior via `apps.worker.worker.run_worker`.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, Any] = {}

    def register(self, name: str, fn: Any) -> None:
        self._tasks[name] = fn

    async def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        fn = self._tasks.get(name)
        if fn is None:
            raise RuntimeError(f"unknown task: {name}")
        return await fn(*args, **kwargs)


_broker = _InMemoryBroker()


def _register_task(name: str) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        _broker.register(name, fn)
        return fn

    return deco


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@_register_task("sync_wallet")
async def sync_wallet_task(wallet_id_str: str) -> dict[str, Any]:
    """Fetch latest balance + transactions for a wallet and persist.

    Idempotent: re-running for the same wallet state yields no new rows.
    """
    configure_logging()
    wid = uuid.UUID(wallet_id_str)
    async with session_scope() as db:
        wallet = await db.get(Wallet, wid)
        if wallet is None or not wallet.is_active:
            return {"wallet_id": wallet_id_str, "status": "skipped"}
        provider = get_provider()
        try:
            balance = await provider.fetch_balance(wallet.chain, wallet.address)
            txs = await provider.fetch_recent_transactions(wallet.chain, wallet.address, limit=50)
        except ProviderPermanentError as exc:
            log.warning("sync_wallet permanent provider error wid=%s err=%s", wid, exc)
            return {"wallet_id": wallet_id_str, "status": "permanent_error"}
        except (ProviderRetryableError, ProviderError) as exc:
            log.warning("sync_wallet retryable provider error wid=%s err=%s", wid, exc)
            return {"wallet_id": wallet_id_str, "status": "retryable_error"}

        # Update balance cache
        wallet.last_native_amount = balance.native_amount
        wallet.last_synced_at = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)

        new_txs = 0
        alerts_fired = 0
        for tx in txs:
            inserted = await _upsert_transaction(db, wallet, tx)
            if inserted:
                new_txs += 1
                alerts_fired += await _evaluate_alerts_for_tx(db, wallet, inserted)
        await db.flush()
        log.info("sync_wallet ok wid=%s new_txs=%s alerts=%s", wid, new_txs, alerts_fired)
        return {
            "wallet_id": wallet_id_str,
            "status": "ok",
            "new_txs": new_txs,
            "alerts_fired": alerts_fired,
        }


@_register_task("snapshot_wallet")
async def snapshot_wallet_task(wallet_id_str: str) -> dict[str, Any]:
    """Take a portfolio snapshot for a wallet."""
    configure_logging()
    wid = uuid.UUID(wallet_id_str)
    async with session_scope() as db:
        wallet = await db.get(Wallet, wid)
        if wallet is None or not wallet.is_active:
            return {"wallet_id": wallet_id_str, "status": "skipped"}
        provider = get_provider()
        try:
            balance = await provider.fetch_balance(wallet.chain, wallet.address)
            holdings = await provider.fetch_token_holdings(wallet.chain, wallet.address)
        except ProviderError:
            return {"wallet_id": wallet_id_str, "status": "provider_error"}
        tokens_usd = sum((h.estimated_usd_value or Decimal(0) for h in holdings), Decimal(0))
        native_usd = balance.estimated_usd_value
        total_usd = (native_usd or Decimal(0)) + tokens_usd
        snap = WalletSnapshot(
            wallet_id=wallet.id,
            taken_at=_dt.datetime.now(_dt.UTC).replace(tzinfo=None),
            native_amount=balance.native_amount,
            native_usd_price=balance.native_usd_price,
            native_usd=native_usd,
            tokens_usd=tokens_usd,
            total_usd=total_usd,
            tokens_count=len(holdings),
        )
        db.add(snap)
        wallet.last_total_usd = total_usd
        await db.flush()
        return {"wallet_id": wallet_id_str, "status": "ok", "snapshot_id": str(snap.id)}


@_register_task("send_telegram_notification")
async def send_telegram_notification_task(
    user_id_str: str, telegram_id: int, text: str
) -> dict[str, Any]:
    """Send a Telegram message via bot. Idempotent at the delivery layer."""
    configure_logging()
    from apps.bot.bot.notifications import send_message  # local import to avoid startup cycle

    try:
        await send_message(telegram_id, text)
    except Exception as exc:
        log.warning("telegram send failed uid=%s tg=%s err=%s", user_id_str, telegram_id, exc)
        return {"user_id": user_id_str, "status": "send_failed"}
    return {"user_id": user_id_str, "status": "sent"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _upsert_transaction(
    db: AsyncSession, wallet: Wallet, parsed_tx: Any
) -> Transaction | None:
    """Insert a transaction if (wallet_id, tx_hash) is not already present."""
    existing = await db.execute(
        select(Transaction).where(
            Transaction.wallet_id == wallet.id,
            Transaction.tx_hash == parsed_tx.tx_hash,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return None
    direction = (
        parsed_tx.direction.value
        if hasattr(parsed_tx.direction, "value")
        else str(parsed_tx.direction)
    )
    risk = parsed_tx.risk.value if hasattr(parsed_tx.risk, "value") else str(parsed_tx.risk)
    tx = Transaction(
        wallet_id=wallet.id,
        tx_hash=parsed_tx.tx_hash,
        block=parsed_tx.block,
        timestamp=_dt.datetime.fromtimestamp(parsed_tx.timestamp, tz=_dt.UTC).replace(tzinfo=None),
        direction=direction,
        counterparty=parsed_tx.counterparty,
        native_amount=parsed_tx.native_amount,
        native_symbol=parsed_tx.native_symbol,
        token_symbol=parsed_tx.token_symbol,
        token_contract=parsed_tx.token_contract,
        token_amount=parsed_tx.token_amount,
        status=parsed_tx.status,
        risk_level=risk,
        risk_reasons=",".join(parsed_tx.risk_reasons) if parsed_tx.risk_reasons else None,
    )
    db.add(tx)
    await db.flush()
    return tx


async def _evaluate_alerts_for_tx(db: AsyncSession, wallet: Wallet, tx: Transaction) -> int:
    alerts = await list_alerts_for_wallet(db, wallet_id=wallet.id)
    fired = 0
    for alert in alerts:
        delivery = await evaluate_alert_for_tx(db, alert=alert, tx=tx)
        if delivery is not None:
            fired += 1
            await _enqueue_telegram_alert(db, alert, delivery, tx)
    return fired


async def _enqueue_telegram_alert(
    db: AsyncSession, alert: Alert, delivery: AlertDelivery, tx: Transaction
) -> None:
    """Trigger Telegram notification. In production this enqueues a Taskiq job.

    For local/test, we attempt to send via the bot directly (best-effort).
    """
    text = (
        f"🔔 Alert fired\n"
        f"Kind: {alert.kind}\n"
        f"Wallet: {alert.wallet_id}\n"
        f"Tx: {tx.tx_hash}\n"
        f"Direction: {tx.direction}\n"
        f"Amount: {tx.native_amount} {tx.native_symbol}\n"
        f"Risk: {tx.risk_level}\n"
    )
    # Resolve the user's telegram_id
    from apps.api.app.models.user import User

    user = await db.get(User, alert.user_id)
    if user is None:
        return
    # Best-effort: enqueue via broker. The real worker picks this up.
    try:
        await _broker.call("send_telegram_notification", str(user.id), user.telegram_id, text)
    except Exception as exc:  # pragma: no cover
        log.warning("enqueue telegram notification failed: %s", exc)


async def run_task(name: str, *args: Any, **kwargs: Any) -> Any:
    """Helper used by tests and by the API enqueue path."""
    return await _broker.call(name, *args, **kwargs)


def get_broker() -> _InMemoryBroker:
    return _broker
