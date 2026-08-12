from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        case_sensitive=False,
        extra="ignore",
    )

    name: str = "Scholarship AI Assistant API"
    env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    database_url: str = "postgresql+psycopg://scholarship:scholarship@localhost:5432/scholarship"
    jwt_secret: str = Field(
        default="local-development-secret-change-me-now",
        min_length=32,
        repr=False,
    )
    jwt_issuer: str = "scholarship-ai-assistant"
    jwt_audience: str = "scholarship-ai-api"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)
    email_verification_ttl_minutes: int = Field(default=1440, ge=15, le=10080)
    password_reset_ttl_minutes: int = Field(default=30, ge=5, le=120)
    admin_step_up_ttl_minutes: int = Field(default=10, ge=1, le=60)
    cors_origins: str = "http://localhost:3000"
    cookie_secure: bool | None = None
    reminder_worker_poll_seconds: int = Field(default=60, ge=10, le=3600)
    reminder_worker_required: bool = False
    # The default provider is deliberately deterministic and does not send student data
    # to a third party. Production integrations must remain server-side.
    assistant_provider: str = "evidence-template"
    assistant_model: str = "evidence-template-v1"
    assistant_api_key: SecretStr | None = Field(default=None, repr=False)
    assistant_prompt_version: str = "phase6.citation-first.v1"
    assistant_retrieval_version: str = "phase6.structured-official.v1"
    assistant_source_freshness_days: int = Field(default=90, ge=1, le=365)
    assistant_max_response_characters: int = Field(default=6000, ge=500, le=12000)
    assistant_max_retrieval_results: int = Field(default=8, ge=1, le=20)
    assistant_daily_user_limit: int = Field(default=30, ge=1, le=500)
    assistant_monthly_user_limit: int = Field(default=300, ge=1, le=5000)
    assistant_rate_limit_per_minute: int = Field(default=12, ge=1, le=120)
    assistant_history_retention_days: int = Field(default=30, ge=1, le=365)
    assistant_feedback_retention_days: int = Field(default=365, ge=30, le=1825)
    assistant_audit_retention_days: int = Field(default=365, ge=30, le=1825)

    # Phase 7 document lab. These controls deliberately live outside the
    # application-document coordination metadata domain.
    document_lab_enabled: bool = False
    document_lab_storage_provider: str = "local-encrypted"
    document_lab_storage_root: str = "./.document-lab-storage"
    document_lab_scanner_provider: str = "unavailable"
    document_lab_scanner_host: str = "localhost"
    document_lab_scanner_port: int = Field(default=3310, ge=1, le=65535)
    document_lab_scanner_timeout_seconds: int = Field(default=30, ge=1, le=120)
    document_lab_encryption_key: SecretStr | None = Field(default=None, repr=False)
    document_lab_max_upload_bytes: int = Field(default=10_000_000, ge=1, le=25_000_000)
    document_lab_max_pages: int = Field(default=50, ge=1, le=200)
    document_lab_max_extracted_characters: int = Field(default=100_000, ge=1_000, le=500_000)
    document_lab_upload_rate_limit_per_minute: int = Field(default=6, ge=1, le=60)
    document_lab_daily_user_limit: int = Field(default=20, ge=1, le=200)
    document_lab_retention_days: int = Field(default=30, ge=1, le=365)
    document_lab_analysis_retention_days: int = Field(default=30, ge=1, le=365)
    document_lab_provider: str = "unavailable"
    document_lab_model: str = "unconfigured"
    document_lab_api_key: SecretStr | None = Field(default=None, repr=False)
    document_lab_provider_timeout_seconds: int = Field(default=30, ge=1, le=120)
    document_lab_provider_config_version: str = "phase7.provider.v1"
    document_lab_rubric_version: str = "phase7.editorial.v1"
    document_lab_notice_version: str = "phase7.document-data-use.v1"

    @model_validator(mode="after")
    def reject_unsafe_production_settings(self) -> "Settings":
        development_secrets = {
            "local-development-secret-change-me-now",
            "local-compose-secret-change-before-any-shared-deployment",
        }
        if self.env == "production" and self.jwt_secret in development_secrets:
            raise ValueError("APP_JWT_SECRET must be replaced before production startup")
        if self.env == "production" and any(origin == "*" for origin in self.cors_origin_list):
            raise ValueError("Wildcard CORS origins are not allowed in production")
        if self.env == "production" and self.document_lab_enabled:
            if self.document_lab_encryption_key is None:
                raise ValueError("APP_DOCUMENT_LAB_ENCRYPTION_KEY is required for Document Lab")
            if self.document_lab_storage_provider == "local-encrypted":
                raise ValueError(
                    "Production Document Lab requires a reviewed remote storage provider"
                )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def refresh_cookie_secure(self) -> bool:
        return self.env == "production" if self.cookie_secure is None else self.cookie_secure


@lru_cache
def get_settings() -> Settings:
    return Settings()
