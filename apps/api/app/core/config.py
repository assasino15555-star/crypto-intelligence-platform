"""Typed application settings loaded from environment.

Production-safety rules:
  * Required secrets (APP_SECRET, TELEGRAM_BOT_TOKEN) must be present when
    ENVIRONMENT == "production".
  * DEV_BYPASS_AUTH may only be true in non-production environments.
  * CORS_ORIGINS, TRUSTED_HOSTS are validated and never defaulted to "*".
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = "development"
    log_level: str = "INFO"

    # Telegram
    telegram_bot_token: str = ""
    telegram_webapp_url: str = "http://localhost:5173"

    # App / sessions
    app_secret: str = ""
    session_ttl_seconds: int = 3600
    initdata_max_age_seconds: int = 3600
    cors_origins_raw: str = Field(default="http://localhost:5173", validation_alias="CORS_ORIGINS")
    trusted_hosts_raw: str = Field(default="", validation_alias="TRUSTED_HOSTS")

    # Database / Redis
    database_url: str
    redis_url: RedisDsn

    # Blockchain provider
    blockchain_provider: Literal["etherscan", "mock"] = "mock"
    blockchain_api_key: str = ""
    blockchain_base_url: str = ""
    provider_http_timeout: float = 10.0
    provider_max_retries: int = 4

    # AI provider
    ai_provider: Literal["openai", "mock"] = "mock"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_http_timeout: float = 20.0

    # Dev-only flags
    dev_bypass_auth: bool = False

    @field_validator("cors_origins_raw", "trusted_hosts_raw", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @property
    def cors_origins(self) -> list[str]:
        parts = [p.strip() for p in self.cors_origins_raw.split(",") if p.strip()]
        return parts or ["http://localhost:5173"]

    @property
    def trusted_hosts(self) -> list[str]:
        return [p.strip() for p in self.trusted_hosts_raw.split(",") if p.strip()]

    @model_validator(mode="after")
    def _enforce_production_constraints(self) -> Settings:
        if self.environment == "production":
            if not self.app_secret or len(self.app_secret) < 32:
                raise ValueError("APP_SECRET must be at least 32 chars in production")
            if not self.telegram_bot_token:
                raise ValueError("TELEGRAM_BOT_TOKEN is required in production")
            if self.dev_bypass_auth:
                raise ValueError("DEV_BYPASS_AUTH must be false in production")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS is not allowed in production")
            if self.blockchain_provider == "mock":
                raise ValueError("Mock provider is not allowed in production")
            if self.ai_provider == "mock":
                raise ValueError("Mock AI provider is not allowed in production")
        else:
            if not self.app_secret:
                # dev-only default so the app can boot without configuration
                self.app_secret = "dev-only-secret-do-not-use-in-production-32chars"
        if self.blockchain_provider == "etherscan" and not self.blockchain_api_key:
            raise ValueError("BLOCKCHAIN_API_KEY required when BLOCKCHAIN_PROVIDER=etherscan")
        if self.ai_provider == "openai" and not self.ai_api_key:
            raise ValueError("AI_API_KEY required when AI_PROVIDER=openai")
        return self

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
