from __future__ import annotations

import pytest

from apps.api.app.core.config import Settings, reset_settings_cache


def _base_env(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "mock")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")


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
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "k")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "short")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    with pytest.raises(ValueError, match="APP_SECRET"):
        Settings()
    reset_settings_cache()


def test_production_rejects_dev_fallback_secret(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "k")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "dev-only-ephemeral-secret-NOT-FOR-PRODUCTION-001")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    with pytest.raises(ValueError, match="dev fallback"):
        Settings()
    reset_settings_cache()


def test_production_forbids_mock_providers(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "mock")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    with pytest.raises(ValueError, match="Mock provider"):
        Settings()
    reset_settings_cache()


def test_production_forbids_wildcard_cors(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "k")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    with pytest.raises(ValueError, match="Wildcard CORS"):
        Settings()
    reset_settings_cache()


def test_production_requires_https_cors(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "k")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CORS_ORIGINS", "http://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    with pytest.raises(ValueError, match="HTTPS"):
        Settings()
    reset_settings_cache()


def test_production_requires_trusted_hosts(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "k")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "")
    with pytest.raises(ValueError, match="TRUSTED_HOSTS"):
        Settings()
    reset_settings_cache()


def test_production_forbids_dev_bypass(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "k")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    monkeypatch.setenv("DEV_BYPASS_AUTH", "true")
    with pytest.raises(ValueError, match="DEV_BYPASS_AUTH"):
        Settings()
    reset_settings_cache()


def test_etherscan_requires_api_key(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "etherscan")
    monkeypatch.setenv("BLOCKCHAIN_API_KEY", "")
    with pytest.raises(ValueError, match="BLOCKCHAIN_API_KEY"):
        Settings()
    reset_settings_cache()


def test_ttl_cannot_exceed_max_lifetime(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("SESSION_TTL_SECONDS", "999999")
    monkeypatch.setenv("SESSION_MAX_LIFETIME_SECONDS", "3600")
    with pytest.raises(ValueError, match="SESSION_TTL"):
        Settings()
    reset_settings_cache()


def test_initdata_max_age_capped(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("INITDATA_MAX_AGE_SECONDS", "99999")
    with pytest.raises(ValueError, match="INITDATA"):
        Settings()
    reset_settings_cache()
