"""Alert evaluation logic tests (deduplication, idempotency)."""

from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from apps.api.app.models.alert import Alert, AlertDelivery
from apps.api.app.models.transaction import Transaction
from apps.api.app.models.wallet import Wallet
from apps.api.app.services.alerts import evaluate_alert_for_tx, list_alerts_for_wallet


@pytest_asyncio.fixture
async def wallet_with_alert(db_session):
    uuid.uuid4()
    # Use raw inserts to keep the test isolated from auth
    from apps.api.app.models.user import User

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


@pytest.mark.asyncio
async def test_incoming_above_fires_once(db_session, wallet_with_alert):
    _, wallet, alert = wallet_with_alert
    tx = Transaction(
        wallet_id=wallet.id,
        tx_hash="0x" + "a" * 64,
        timestamp=_dt.datetime.now(_dt.UTC).replace(tzinfo=None),
        direction="in",
        counterparty="0x" + "ff" * 20,
        native_amount=Decimal("1.0"),
        native_symbol="ETH",
        status="ok",
        risk_level="low",
    )
    db_session.add(tx)
    await db_session.flush()
    delivery1 = await evaluate_alert_for_tx(db_session, alert=alert, tx=tx)
    assert delivery1 is not None
    delivery2 = await evaluate_alert_for_tx(db_session, alert=alert, tx=tx)
    assert delivery2 is None  # idempotent: same tx, no second delivery
    # Verify only one delivery row
    res = await db_session.execute(select(AlertDelivery).where(AlertDelivery.alert_id == alert.id))
    assert len(list(res.scalars().all())) == 1


@pytest.mark.asyncio
async def test_incoming_above_below_threshold_no_fire(db_session, wallet_with_alert):
    _, wallet, alert = wallet_with_alert
    tx = Transaction(
        wallet_id=wallet.id,
        tx_hash="0x" + "b" * 64,
        timestamp=_dt.datetime.now(_dt.UTC).replace(tzinfo=None),
        direction="in",
        counterparty="0x" + "ee" * 20,
        native_amount=Decimal("0.1"),  # below 0.5 threshold
        native_symbol="ETH",
        status="ok",
        risk_level="low",
    )
    db_session.add(tx)
    await db_session.flush()
    delivery = await evaluate_alert_for_tx(db_session, alert=alert, tx=tx)
    assert delivery is None


@pytest.mark.asyncio
async def test_outgoing_does_not_fire_incoming_alert(db_session, wallet_with_alert):
    _, wallet, alert = wallet_with_alert
    tx = Transaction(
        wallet_id=wallet.id,
        tx_hash="0x" + "c" * 64,
        timestamp=_dt.datetime.now(_dt.UTC).replace(tzinfo=None),
        direction="out",
        counterparty="0x" + "dd" * 20,
        native_amount=Decimal("100.0"),
        native_symbol="ETH",
        status="ok",
        risk_level="low",
    )
    db_session.add(tx)
    await db_session.flush()
    delivery = await evaluate_alert_for_tx(db_session, alert=alert, tx=tx)
    assert delivery is None


@pytest.mark.asyncio
async def test_inactive_alert_does_not_fire(db_session, wallet_with_alert):
    _, wallet, alert = wallet_with_alert
    alert.is_active = False
    await db_session.flush()
    tx = Transaction(
        wallet_id=wallet.id,
        tx_hash="0x" + "d" * 64,
        timestamp=_dt.datetime.now(_dt.UTC).replace(tzinfo=None),
        direction="in",
        counterparty="0x" + "cc" * 20,
        native_amount=Decimal("10.0"),
        native_symbol="ETH",
        status="ok",
        risk_level="low",
    )
    db_session.add(tx)
    await db_session.flush()
    delivery = await evaluate_alert_for_tx(db_session, alert=alert, tx=tx)
    assert delivery is None


@pytest.mark.asyncio
async def test_list_alerts_for_wallet(db_session, wallet_with_alert):
    _, wallet, alert = wallet_with_alert
    alerts = await list_alerts_for_wallet(db_session, wallet_id=wallet.id)
    assert len(alerts) == 1
    assert alerts[0].id == alert.id
