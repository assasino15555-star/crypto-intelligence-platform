"""Settings / configuration validation tests."""

from __future__ import annotations

import pytest

from apps.api.app.core.config import Settings, reset_settings_cache


def test_dev_defaults_allowed(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "mock")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    s = Settings()
    assert s.environment == "development"
    assert s.dev_bypass_auth is False
    reset_settings_cache()


def test_production_requires_strong_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("REDIS_URL", "redis://x:6379/0")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "k")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "short")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    with pytest.raises(ValueError, match="APP_SECRET"):
        Settings()
    reset_settings_cache()


def test_production_forbids_mock_providers(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("REDIS_URL", "redis://x:6379/0")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "mock")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    with pytest.raises(ValueError, match="Mock provider"):
        Settings()
    reset_settings_cache()


def test_production_forbids_wildcard_cors(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("REDIS_URL", "redis://x:6379/0")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "k")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="Wildcard CORS"):
        Settings()
    reset_settings_cache()


def test_etherscan_requires_api_key(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    with pytest.raises(ValueError, match="BLOCKCHAIN_API_KEY"):
        Settings()
    reset_settings_cache()


def test_cors_origins_split(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "mock")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("CORS_ORIGINS", "http://a:5173, http://b:5173")
    s = Settings()
    assert s.cors_origins == ["http://a:5173", "http://b:5173"]
    reset_settings_cache()
