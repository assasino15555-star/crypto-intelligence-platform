from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "shared"))

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("BLOCKCHAIN_PROVIDER", "mock")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("APP_SECRET", "test-secret-at-least-32-characters-long!!")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TESTBOTOKEN0123456789_abcdefghij")
os.environ.setdefault("DEV_BYPASS_AUTH", "false")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
os.environ.setdefault("MAX_WALLETS_PER_USER", "20")
os.environ.setdefault("MAX_ALERTS_PER_USER", "100")
os.environ.setdefault("MAX_SESSIONS_PER_USER", "5")
os.environ.setdefault("INITDATA_MAX_AGE_SECONDS", "300")
os.environ.setdefault("SESSION_MAX_LIFETIME_SECONDS", "86400")

from apps.api.app.core import config as config_module
from apps.api.app.db import session as db_session_module
from apps.api.app.db.session import Base
from apps.api.app.main import create_app


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._ttl: dict[str, float] = {}

    async def set(self, key: str, value: bytes, *, ex: int | None = None, nx: bool = False) -> bool:
        import time

        if nx and key in self._store:
            if self._ttl.get(key, 0) > time.time():
                return False
        self._store[key] = value
        self._ttl[key] = (time.time() + ex) if ex else float("inf")
        return True

    async def get(self, key: str) -> bytes | None:
        import time

        if key not in self._store:
            return None
        if self._ttl.get(key, 0) <= time.time():
            self._store.pop(key, None)
            self._ttl.pop(key, None)
            return None
        return self._store[key]

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        return 1

    async def zcard(self, key: str) -> int:
        return 0

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        return 0

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def pipeline(self, transaction: bool = True) -> Any:
        return self

    async def execute(self) -> list[Any]:
        return [0, 0, 1, True]

    async def disconnect(self) -> None:
        pass

    async def close(self) -> None:
        pass


_fake_redis = FakeRedis()


def _get_fake_redis() -> Any:
    return _fake_redis


@pytest.fixture(scope="session")
def event_loop() -> Any:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def app(monkeypatch, engine):
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise

    monkeypatch.setattr(db_session_module, "get_engine", lambda: engine)
    monkeypatch.setattr(db_session_module, "get_session_factory", lambda: factory)
    monkeypatch.setattr(db_session_module, "get_session", _get_session)
    monkeypatch.setattr(db_session_module, "get_redis", _get_fake_redis)
    from apps.api.app.utils import rate_limit as rl_module

    monkeypatch.setattr(rl_module, "_get_redis", _get_fake_redis)
    config_module.reset_settings_cache()
    application = create_app()
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def authed_client(app, db_session) -> AsyncIterator[AsyncClient]:
    from apps.api.app.core import config as cfg

    cfg.get_settings().dev_bypass_auth = True
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    cfg.get_settings().dev_bypass_auth = False
