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
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    report_media_bucket: str = "report-media"
    report_media_allowed_mime_types: str = "image/jpeg,image/png,image/webp"
    report_media_max_bytes: int = 10 * 1024 * 1024
    report_media_signed_url_ttl_seconds: int = 600
    frontend_origins: str = "http://127.0.0.1:3000,http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so one request cannot observe mixed environment values."""
    return Settings()
