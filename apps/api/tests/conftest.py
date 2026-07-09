"""Test configuration: sqlite + in-memory engine per test, mock providers."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "shared"))

# Set env BEFORE importing app code
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("BLOCKCHAIN_PROVIDER", "mock")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("APP_SECRET", "test-secret-at-least-32-characters-long!!")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TESTBOTOKEN0123456789_abcdefghij")
os.environ.setdefault("DEV_BYPASS_AUTH", "false")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

from apps.api.app.core import config as config_module
from apps.api.app.db import session as db_session_module
from apps.api.app.db.session import Base
from apps.api.app.main import create_app


@pytest.fixture(scope="session")
def event_loop():  # type: ignore[no-untyped-def]
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
    # Force the app to use our test engine
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
    # Reset settings cache to pick up env
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
    """A client authenticated as a synthetic dev user (DEV_BYPASS_AUTH=true)."""
    # We bypass real Telegram auth here for API tests; identity is verified
    # in dedicated security tests.
    from apps.api.app.core import config as cfg

    cfg.get_settings().dev_bypass_auth = True  # local override for this fixture
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    cfg.get_settings().dev_bypass_auth = False
