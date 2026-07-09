"""Worker task tests: sync_wallet idempotency, snapshot, alert firing."""

from __future__ import annotations

import pytest
import pytest_asyncio

from apps.api.app.models.alert import Alert
from apps.api.app.models.user import User
from apps.api.app.models.wallet import Wallet
from apps.worker.worker import tasks as worker_tasks


@pytest_asyncio.fixture
async def setup_wallet(db_session, monkeypatch):
    """Insert a user + wallet, monkeypatch the worker's session_scope to use the test engine."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from apps.api.app.db import session as db_session_module
    from apps.api.app.db.session import Base

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _scope():
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    monkeypatch.setattr(worker_tasks, "session_scope", _scope)
    monkeypatch.setattr(db_session_module, "get_engine", lambda: eng)
    monkeypatch.setattr(db_session_module, "get_session_factory", lambda: factory)

    # Insert user + wallet via the worker's scope
    async with _scope() as s:
        user = User(telegram_id=999_111_222, telegram_username="worker_test")
        s.add(user)
        await s.flush()
        wallet = Wallet(
            user_id=user.id,
            chain="ethereum",
            address="0x" + "ab" * 20,
            native_symbol="ETH",
        )
        s.add(wallet)
        await s.flush()
        wallet_id = wallet.id
        user_telegram_id = user.telegram_id
    return wallet_id, user_telegram_id, factory


@pytest.mark.asyncio
async def test_sync_wallet_idempotent(setup_wallet):
    wallet_id, _, _ = setup_wallet
    # First sync: 3 mock txs inserted
    res1 = await worker_tasks.run_task("sync_wallet", str(wallet_id))
    assert res1["status"] == "ok"
    assert res1["new_txs"] == 3

    # Second sync: same mock txs already present
    res2 = await worker_tasks.run_task("sync_wallet", str(wallet_id))
    assert res2["status"] == "ok"
    assert res2["new_txs"] == 0


@pytest.mark.asyncio
async def test_snapshot_wallet(setup_wallet):
    wallet_id, _, _ = setup_wallet
    res = await worker_tasks.run_task("snapshot_wallet", str(wallet_id))
    assert res["status"] == "ok"
    assert "snapshot_id" in res


@pytest.mark.asyncio
async def test_sync_wallet_with_alert_fires(setup_wallet, monkeypatch):
    """A sync_wallet run that fetches a tx matching an alert should produce a delivery row."""
    wallet_id, _, factory = setup_wallet
    # Add an alert for this wallet via the worker's session_scope
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _scope():
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    # we need to monkeypatch session_scope here again to use the same engine
    async with _scope() as s:
        wallet = await s.get(Wallet, wallet_id)
        alert = Alert(
            user_id=wallet.user_id,
            wallet_id=wallet_id,
            kind="activity",  # fires on any tx
        )
        s.add(alert)
        await s.flush()

    # Stub out telegram notification to avoid network calls
    sent: list[tuple[int, str]] = []

    async def fake_send(uid: str, tg_id: int, text: str) -> dict:
        sent.append((tg_id, text))
        return {"status": "sent"}

    # The worker calls `_broker.call("send_telegram_notification", ...)`, which looks up the
    # function in `_broker._tasks`. Replace it.
    worker_tasks.get_broker().register("send_telegram_notification", fake_send)

    res = await worker_tasks.run_task("sync_wallet", str(wallet_id))
    assert res["status"] == "ok"
    assert res["alerts_fired"] >= 1
    # Re-running must not re-fire deliveries (idempotent)
    res2 = await worker_tasks.run_task("sync_wallet", str(wallet_id))
    assert res2["alerts_fired"] == 0


@pytest.mark.asyncio
async def test_sync_wallet_skips_inactive(setup_wallet, monkeypatch):
    wallet_id, _, factory = setup_wallet
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _scope():
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async with _scope() as s:
        wallet = await s.get(Wallet, wallet_id)
        wallet.is_active = False
        await s.flush()

    res = await worker_tasks.run_task("sync_wallet", str(wallet_id))
    assert res["status"] == "skipped"
