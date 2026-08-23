"""Provide typed environment configuration for the backend."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_VERTEX_LOCATION = "asia-southeast1"


class Settings(BaseSettings):
    """Runtime settings shared by the backend entry points."""

    database_url: str = ""
    app_env: str = "local"
    allow_debug_auth: bool = False
    ai_provider: str = "stub"
    vertex_project_id: str = ""
    vertex_location: str = DEFAULT_VERTEX_LOCATION
    vertex_model: str = "gemini-3.5-flash"
    vertex_embedding_model: str = "gemini-embedding-001"
    vertex_max_output_tokens: int = Field(default=4096, ge=256)
    vertex_input_cost_per_million_usd: float = Field(default=1.65, ge=0.0)
    vertex_output_cost_per_million_usd: float = Field(default=9.90, ge=0.0)
    vertex_embedding_cost_per_million_usd: float = Field(default=0.15, ge=0.0)
    ai_circuit_failure_threshold: int = Field(default=3, ge=1)
    ai_circuit_reset_seconds: float = Field(default=60.0, gt=0.0)
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
    documents_bucket: str = "documents"
    documents_max_bytes: int = 25 * 1024 * 1024
    alert_escalate_minutes: int = 5
    overdue_notification_hour: int = Field(default=8, ge=0, le=23)
    quiz_rate_limit_per_minute: int = Field(default=30, ge=1, le=300)
    report_submission_rate_limit_per_minute: int = Field(default=10, ge=1, le=300)
    document_upload_rate_limit_per_minute: int = Field(default=5, ge=1, le=100)
    deep_health_timeout_seconds: float = Field(default=5.0, gt=0.0, le=30.0)
    slow_request_ms: int = Field(default=300, ge=1)
    log_level: str = "INFO"
    frontend_origins: str = "http://127.0.0.1:3000,http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so one request cannot observe mixed environment values."""
    return Settings()
