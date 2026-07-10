from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]

_DEV_FALLBACK_SECRET = "dev-only-ephemeral-secret-NOT-FOR-PRODUCTION-001"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = "development"
    log_level: str = "INFO"

    telegram_bot_token: str = ""
    telegram_webapp_url: str = "https://localhost"

    app_secret: str = ""
    session_ttl_seconds: int = 3600
    session_max_lifetime_seconds: int = 86400
    initdata_max_age_seconds: int = 300
    initdata_replay_window_seconds: int = 300
    cors_origins_raw: str = Field(default="", validation_alias="CORS_ORIGINS")
    trusted_hosts_raw: str = Field(default="", validation_alias="TRUSTED_HOSTS")

    database_url: str
    redis_url: RedisDsn

    blockchain_provider: Literal["etherscan", "mock"] = "mock"
    blockchain_api_key: str = ""
    blockchain_base_url: str = ""
    provider_http_timeout: float = 10.0
    provider_max_retries: int = 4
    provider_max_response_bytes: int = 1_048_576

    ai_provider: Literal["openai", "mock"] = "mock"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_http_timeout: float = 20.0
    ai_max_response_bytes: int = 262_144

    max_wallets_per_user: int = 20
    max_alerts_per_user: int = 100
    max_sessions_per_user: int = 5

    rate_limit_trusted_proxies_raw: str = Field(
        default="", validation_alias="RATE_LIMIT_TRUSTED_PROXIES"
    )

    dev_bypass_auth: bool = False

    @field_validator(
        "cors_origins_raw", "trusted_hosts_raw", "rate_limit_trusted_proxies_raw", mode="before"
    )
    @classmethod
    def _strip(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @property
    def cors_origins(self) -> list[str]:
        parts = [p.strip() for p in self.cors_origins_raw.split(",") if p.strip()]
        return parts

    @property
    def trusted_hosts(self) -> list[str]:
        return [p.strip() for p in self.trusted_hosts_raw.split(",") if p.strip()]

    @property
    def rate_limit_trusted_proxies(self) -> list[str]:
        return [p.strip() for p in self.rate_limit_trusted_proxies_raw.split(",") if p.strip()]

    @model_validator(mode="after")
    def _enforce_constraints(self) -> Settings:
        if self.session_ttl_seconds > self.session_max_lifetime_seconds:
            raise ValueError("SESSION_TTL_SECONDS cannot exceed SESSION_MAX_LIFETIME_SECONDS")
        if self.initdata_max_age_seconds > 3600:
            raise ValueError("INITDATA_MAX_AGE_SECONDS cannot exceed 3600")
        if self.dev_bypass_auth and self.is_production:
            raise ValueError("DEV_BYPASS_AUTH must be false in production")
        if self.is_production:
            self._enforce_production()
        elif self.is_dev:
            if not self.app_secret:
                self.app_secret = _DEV_FALLBACK_SECRET
        if self.blockchain_provider == "etherscan" and not self.blockchain_api_key:
            raise ValueError("BLOCKCHAIN_API_KEY required when BLOCKCHAIN_PROVIDER=etherscan")
        if self.ai_provider == "openai" and not self.ai_api_key:
            raise ValueError("AI_API_KEY required when AI_PROVIDER=openai")
        return self

    def _enforce_production(self) -> None:
        if not self.app_secret or len(self.app_secret) < 32:
            raise ValueError("APP_SECRET must be at least 32 chars in production")
        if self.app_secret == _DEV_FALLBACK_SECRET:
            raise ValueError("known dev fallback secret is not allowed in production")
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required in production")
        if not self.cors_origins:
            raise ValueError("CORS_ORIGINS must be set in production")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS is not allowed in production")
        for origin in self.cors_origins:
            if not origin.startswith("https://"):
                raise ValueError(f"CORS origin must be HTTPS in production: {origin}")
        if not self.trusted_hosts:
            raise ValueError("TRUSTED_HOSTS must be set in production")
        if self.blockchain_provider == "mock":
            raise ValueError("Mock provider is not allowed in production")
        if self.ai_provider == "mock":
            raise ValueError("Mock AI provider is not allowed in production")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
