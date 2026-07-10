from __future__ import annotations

import datetime as _dt
import hashlib
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

log = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class _InMemoryBroker:
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


@_register_task("sync_wallet")
async def sync_wallet_task(wallet_id_str: str) -> dict[str, Any]:
    configure_logging()
    wid = uuid.UUID(wallet_id_str)
    async with session_scope() as db:
        wallet = await db.get(Wallet, wid)
        if wallet is None or not wallet.is_active:
            return {"wallet_id": wallet_id_str, "status": "skipped"}

        lock_acquired = await _acquire_wallet_lock(db, wid)
        if not lock_acquired:
            return {"wallet_id": wallet_id_str, "status": "locked"}

        try:
            from apps.api.app.providers.registry import get_provider

            provider = get_provider()
            try:
                balance = await provider.fetch_balance(wallet.chain, wallet.address)
                txs = await provider.fetch_recent_transactions(
                    wallet.chain, wallet.address, limit=50
                )
            except ProviderPermanentError as exc:
                log.warning("sync_wallet permanent error wid=%s err=%s", wid, exc)
                return {"wallet_id": wallet_id_str, "status": "permanent_error"}
            except (ProviderRetryableError, ProviderError) as exc:
                log.warning("sync_wallet retryable error wid=%s err=%s", wid, exc)
                return {"wallet_id": wallet_id_str, "status": "retryable_error"}

            wallet.last_native_amount = balance.native_amount
            wallet.last_synced_at = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)

            new_txs = 0
            alerts_fired = 0
            for parsed_tx in txs:
                inserted = await _upsert_transaction(db, wallet, parsed_tx)
                if inserted is not None:
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
        finally:
            await _release_wallet_lock(wid)


@_register_task("snapshot_wallet")
async def snapshot_wallet_task(wallet_id_str: str) -> dict[str, Any]:
    configure_logging()
    wid = uuid.UUID(wallet_id_str)
    async with session_scope() as db:
        wallet = await db.get(Wallet, wid)
        if wallet is None or not wallet.is_active:
            return {"wallet_id": wallet_id_str, "status": "skipped"}
        from apps.api.app.providers.registry import get_provider

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
    configure_logging()
    from apps.bot.bot.notifications import send_message

    try:
        await send_message(telegram_id, text)
    except Exception as exc:
        log.warning("telegram send failed uid=%s tg=%s err=%s", user_id_str, telegram_id, exc)
        return {"user_id": user_id_str, "status": "send_failed"}
    return {"user_id": user_id_str, "status": "sent"}


async def _acquire_wallet_lock(db: AsyncSession, wallet_id: uuid.UUID) -> bool:
    from apps.api.app.db.session import get_redis

    redis = get_redis()
    lock_key = f"wallet_lock:{wallet_id}"
    try:
        acquired = await redis.set(lock_key, b"1", ex=120, nx=True)
        return bool(acquired)
    except Exception as exc:
        log.warning("wallet lock redis error: %s", exc)
        return True


async def _release_wallet_lock(wallet_id: uuid.UUID) -> None:
    from apps.api.app.db.session import get_redis

    redis = get_redis()
    lock_key = f"wallet_lock:{wallet_id}"
    try:
        await redis.delete(lock_key)
    except Exception as exc:
        log.warning("wallet unlock redis error: %s", exc)


async def _upsert_transaction(
    db: AsyncSession, wallet: Wallet, parsed_tx: Any
) -> Transaction | None:
    existing_q = await db.execute(
        select(Transaction).where(
            Transaction.wallet_id == wallet.id,
            Transaction.tx_hash == parsed_tx.tx_hash,
        )
    )
    if existing_q.scalar_one_or_none() is not None:
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
    alerts_q = await db.execute(
        select(Alert).where(Alert.wallet_id == wallet.id, Alert.is_active.is_(True))
    )
    alerts = list(alerts_q.scalars().all())
    fired = 0
    for alert in alerts:
        delivery = await _try_fire_alert(db, alert, tx)
        if delivery is not None:
            fired += 1
            await _enqueue_telegram_alert(db, alert, tx)
    return fired


async def _try_fire_alert(db: AsyncSession, alert: Alert, tx: Transaction) -> AlertDelivery | None:
    if not alert.is_active:
        return None
    if alert.wallet_id != tx.wallet_id:
        return None
    fires = False
    if (alert.kind == "incoming_above" and tx.direction == "in") or (
        alert.kind == "outgoing_above" and tx.direction == "out"
    ):
        if alert.threshold_amount is not None and tx.native_amount >= Decimal(
            str(alert.threshold_amount)
        ):
            fires = True
    elif alert.kind == "activity":
        fires = True
    elif alert.kind == "token_transfer":
        fires = tx.token_contract is not None
    elif alert.kind == "balance_above":
        return None
    if not fires:
        return None
    sig = _event_signature(alert.id, tx.id, alert.kind)
    existing_q = await db.execute(
        select(AlertDelivery).where(
            AlertDelivery.alert_id == alert.id,
            AlertDelivery.event_signature == sig,
        )
    )
    if existing_q.scalar_one_or_none() is not None:
        return None
    delivery = AlertDelivery(alert_id=alert.id, event_signature=sig, channel="telegram")
    db.add(delivery)
    await db.flush()
    return delivery


def _event_signature(alert_id: uuid.UUID, tx_id: uuid.UUID, kind: str) -> str:
    base = f"{alert_id}:{kind}:{tx_id}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


async def _enqueue_telegram_alert(db: AsyncSession, alert: Alert, tx: Transaction) -> None:
    from apps.api.app.models.user import User

    user = await db.get(User, alert.user_id)
    if user is None:
        return
    text = (
        f"Alert: {alert.kind}\n"
        f"Wallet: {alert.wallet_id}\n"
        f"Tx: {tx.tx_hash}\n"
        f"Direction: {tx.direction}\n"
        f"Amount: {tx.native_amount} {tx.native_symbol}\n"
        f"Risk: {tx.risk_level}"
    )
    try:
        await _broker.call("send_telegram_notification", str(user.id), user.telegram_id, text)
    except Exception as exc:
        log.warning("enqueue telegram notification failed: %s", exc)


async def run_task(name: str, *args: Any, **kwargs: Any) -> Any:
    return await _broker.call(name, *args, **kwargs)


def get_broker() -> _InMemoryBroker:
    return _broker
