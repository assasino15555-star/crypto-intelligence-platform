from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from apps.api.app.models.alert import Alert, AlertDelivery
from apps.api.app.models.transaction import Transaction
from apps.api.app.models.user import User
from apps.api.app.models.wallet import Wallet
from apps.worker.worker.tasks import _event_signature, _try_fire_alert


@pytest_asyncio.fixture
async def wallet_with_alert(db_session):
    user = User(telegram_id=999_000_001, telegram_username="tester")
    db_session.add(user)
    await db_session.flush()
    wallet = Wallet(
        user_id=user.id,
        chain="ethereum",
        address="0x" + "ab" * 20,
        native_symbol="ETH",
    )
    db_session.add(wallet)
    await db_session.flush()
    alert = Alert(
        user_id=user.id,
        wallet_id=wallet.id,
        kind="incoming_above",
        threshold_amount=Decimal("0.5"),
    )
    db_session.add(alert)
    await db_session.flush()
    return user, wallet, alert


async def _make_tx(wallet: Wallet, amount: str, direction: str, tx_hash: str) -> Transaction:
    return Transaction(
        wallet_id=wallet.id,
        tx_hash=tx_hash,
        timestamp=_dt.datetime.now(_dt.UTC).replace(tzinfo=None),
        direction=direction,
        counterparty="0x" + "ff" * 20,
        native_amount=Decimal(amount),
        native_symbol="ETH",
        status="ok",
        risk_level="low",
    )


@pytest.mark.asyncio
async def test_incoming_above_fires_once(db_session, wallet_with_alert):
    _, wallet, alert = wallet_with_alert
    tx = await _make_tx(wallet, "1.0", "in", "0x" + "a" * 64)
    db_session.add(tx)
    await db_session.flush()
    delivery1 = await _try_fire_alert(db_session, alert, tx)
    assert delivery1 is not None
    delivery2 = await _try_fire_alert(db_session, alert, tx)
    assert delivery2 is None
    res = await db_session.execute(select(AlertDelivery).where(AlertDelivery.alert_id == alert.id))
    assert len(list(res.scalars().all())) == 1


@pytest.mark.asyncio
async def test_incoming_above_below_threshold_no_fire(db_session, wallet_with_alert):
    _, wallet, alert = wallet_with_alert
    tx = await _make_tx(wallet, "0.1", "in", "0x" + "b" * 64)
    db_session.add(tx)
    await db_session.flush()
    delivery = await _try_fire_alert(db_session, alert, tx)
    assert delivery is None


@pytest.mark.asyncio
async def test_outgoing_does_not_fire_incoming_alert(db_session, wallet_with_alert):
    _, wallet, alert = wallet_with_alert
    tx = await _make_tx(wallet, "100.0", "out", "0x" + "c" * 64)
    db_session.add(tx)
    await db_session.flush()
    delivery = await _try_fire_alert(db_session, alert, tx)
    assert delivery is None


@pytest.mark.asyncio
async def test_inactive_alert_does_not_fire(db_session, wallet_with_alert):
    _, wallet, alert = wallet_with_alert
    alert.is_active = False
    await db_session.flush()
    tx = await _make_tx(wallet, "10.0", "in", "0x" + "d" * 64)
    db_session.add(tx)
    await db_session.flush()
    delivery = await _try_fire_alert(db_session, alert, tx)
    assert delivery is None


def test_event_signature_is_deterministic():
    aid = uuid.uuid4()
    tid = uuid.uuid4()
    sig1 = _event_signature(aid, tid, "activity")
    sig2 = _event_signature(aid, tid, "activity")
    assert sig1 == sig2
    sig3 = _event_signature(aid, tid, "incoming_above")
    assert sig1 != sig3
