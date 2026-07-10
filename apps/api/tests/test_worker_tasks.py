from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from apps.api.app.db.session import Base
from apps.api.app.models.alert import Alert
from apps.api.app.models.user import User
from apps.api.app.models.wallet import Wallet
from apps.worker.worker import tasks as worker_tasks


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def set(self, key: str, value: bytes, *, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def delete(self, key: str) -> int:
        return (self._store.pop(key, None) and 1) or 0


@pytest_asyncio.fixture
async def worker_env(db_session, monkeypatch):
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    monkeypatch.setattr(worker_tasks, "session_scope", _scope)

    fake_redis = _FakeRedis()

    def _get_redis() -> Any:
        return fake_redis

    monkeypatch.setattr("apps.api.app.db.session.get_redis", _get_redis)

    async with _scope() as s:
        user = User(telegram_id=999_111_222, telegram_username="wtest")
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
        telegram_id = user.telegram_id
    return wallet_id, telegram_id, factory


@pytest.mark.asyncio
async def test_sync_wallet_idempotent(worker_env):
    wallet_id, _, _ = worker_env
    res1 = await worker_tasks.run_task("sync_wallet", str(wallet_id))
    assert res1["status"] == "ok"
    assert res1["new_txs"] == 3

    res2 = await worker_tasks.run_task("sync_wallet", str(wallet_id))
    assert res2["status"] == "ok"
    assert res2["new_txs"] == 0


@pytest.mark.asyncio
async def test_snapshot_wallet(worker_env):
    wallet_id, _, _ = worker_env
    res = await worker_tasks.run_task("snapshot_wallet", str(wallet_id))
    assert res["status"] == "ok"
    assert "snapshot_id" in res


@pytest.mark.asyncio
async def test_sync_wallet_with_alert_fires(worker_env, monkeypatch):
    wallet_id, _, factory = worker_env

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async with _scope() as s:
        wallet = await s.get(Wallet, wallet_id)
        alert = Alert(
            user_id=wallet.user_id,
            wallet_id=wallet_id,
            kind="activity",
        )
        s.add(alert)
        await s.flush()

    sent: list[tuple[int, str]] = []

    async def fake_send(uid: str, tg_id: int, text: str) -> dict[str, str]:
        sent.append((tg_id, text))
        return {"status": "sent"}

    worker_tasks.get_broker().register("send_telegram_notification", fake_send)

    res = await worker_tasks.run_task("sync_wallet", str(wallet_id))
    assert res["status"] == "ok"
    assert res["alerts_fired"] >= 1

    res2 = await worker_tasks.run_task("sync_wallet", str(wallet_id))
    assert res2["alerts_fired"] == 0


@pytest.mark.asyncio
async def test_sync_wallet_skips_inactive(worker_env, monkeypatch):
    wallet_id, _, factory = worker_env

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
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
