"""Provide typed environment configuration for the backend."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by the backend entry points."""

    database_url: str = ""
    app_env: str = "local"
    allow_debug_auth: bool = False
    ai_provider: str = "stub"
    site_timezone: str = "Asia/Singapore"
    supported_locales: str = "en,zh-CN"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so one request cannot observe mixed environment values."""
    return Settings()
