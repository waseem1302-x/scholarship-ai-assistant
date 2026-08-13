from functools import lru_cache
from ipaddress import ip_network
from typing import Literal
from urllib.parse import urlparse

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
    migration_database_url: SecretStr | None = Field(default=None, repr=False)
    # The isolated Alembic job must not need the API, SMTP, Redis, or JWT
    # secrets merely because it imports the application's settings.
    migration_only: bool = False
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
    release_version: str = "development"
    trusted_proxy_ips: str = ""
    trusted_proxy_mode: Literal["explicit", "azure-container-apps"] = "explicit"
    operational_job_stale_minutes: int = Field(default=15, ge=1, le=1440)

    # Phase 9 beta and capability controls. These remain server-side so that a
    # high-risk capability can be paused without a frontend release.
    beta_enabled: bool = False
    beta_registration_open: bool = False
    beta_max_active_students: int = Field(default=25, ge=1, le=10_000)
    beta_product_owner_contact: str | None = None
    beta_support_contact: str | None = None
    beta_moderation_contact: str | None = None
    beta_data_quality_contact: str | None = None
    beta_incident_contact: str | None = None
    beta_terms_version: str = "phase9.beta-terms.v1"
    beta_privacy_notice_version: str = "phase9.beta-privacy.v1"
    catalogue_maintenance_mode: bool = False
    # High-risk capabilities begin disabled. A beta deployment opts in only
    # after the corresponding release gate has been evidenced.
    assistant_enabled: bool = False
    community_enabled: bool = False

    # Production account-token delivery. Local/test runs intentionally use no
    # network mailer and surface a debug token only outside production.
    email_provider: Literal["unconfigured", "smtp"] = "unconfigured"
    email_from: str | None = None
    email_smtp_host: str | None = None
    email_smtp_port: int = Field(default=587, ge=1, le=65535)
    email_smtp_username: str | None = None
    email_smtp_password: SecretStr | None = Field(default=None, repr=False)
    email_smtp_starttls: bool = True

    # Authentication, high-cost, and write routes need a shared atomic store
    # before a production deployment can run more than one API instance.
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_redis_url: SecretStr | None = Field(default=None, repr=False)
    rate_limit_redis_timeout_seconds: int = Field(default=2, ge=1, le=10)
    auth_login_rate_limit_per_minute: int = Field(default=10, ge=1, le=120)
    auth_login_global_rate_limit_per_minute: int = Field(default=300, ge=1, le=10_000)
    auth_registration_rate_limit_per_minute: int = Field(default=5, ge=1, le=120)
    account_recovery_rate_limit_per_minute: int = Field(default=5, ge=1, le=120)
    account_verification_rate_limit_per_minute: int = Field(default=10, ge=1, le=120)
    admin_reauthentication_rate_limit_per_minute: int = Field(default=5, ge=1, le=120)
    webauthn_rate_limit_per_minute: int = Field(default=10, ge=1, le=120)

    # WebAuthn is administrator-only. The RP values deliberately cannot be
    # inferred from a request Host header in production.
    webauthn_rp_id: str | None = None
    webauthn_rp_name: str = "Scholarship AI Assistant"
    webauthn_origins: str = ""
    webauthn_challenge_ttl_minutes: int = Field(default=5, ge=1, le=15)
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
    document_lab_storage_provider: Literal["local-encrypted", "s3-compatible", "test"] = (
        "local-encrypted"
    )
    document_lab_storage_root: str = "./.document-lab-storage"
    document_lab_s3_bucket: str | None = None
    document_lab_s3_region: str | None = None
    document_lab_s3_endpoint_url: str | None = None
    document_lab_s3_kms_key_id: str | None = None
    document_lab_scanner_provider: str = "unavailable"
    document_lab_scanner_host: str = "localhost"
    document_lab_scanner_port: int = Field(default=3310, ge=1, le=65535)
    document_lab_scanner_timeout_seconds: int = Field(default=30, ge=1, le=120)
    document_lab_parser_isolation_enabled: bool = False
    document_lab_remote_analysis_approved: bool = False
    document_lab_encryption_key: SecretStr | None = Field(default=None, repr=False)
    document_lab_max_upload_bytes: int = Field(default=10_000_000, ge=1, le=25_000_000)
    document_lab_max_pages: int = Field(default=50, ge=1, le=200)
    document_lab_max_extracted_characters: int = Field(default=100_000, ge=1_000, le=500_000)
    document_lab_upload_rate_limit_per_minute: int = Field(default=6, ge=1, le=60)
    document_lab_daily_user_limit: int = Field(default=20, ge=1, le=200)
    document_lab_daily_analysis_limit: int = Field(default=10, ge=1, le=100)
    document_lab_retention_days: int = Field(default=30, ge=1, le=365)
    document_lab_analysis_retention_days: int = Field(default=30, ge=1, le=365)
    document_lab_provider: str = "unavailable"
    document_lab_model: str = "unconfigured"
    document_lab_api_key: SecretStr | None = Field(default=None, repr=False)
    document_lab_provider_timeout_seconds: int = Field(default=30, ge=1, le=120)
    document_lab_provider_config_version: str = "phase7.provider.v1"
    document_lab_rubric_version: str = "phase7.editorial.v1"
    document_lab_notice_version: str = "phase7.document-data-use.v1"

    # Phase 8 scholarship-only community. The single-instance limiter is a
    # deliberate interim control; a shared limiter is required before scaling.
    community_write_rate_limit_per_minute: int = Field(default=10, ge=1, le=120)

    @model_validator(mode="after")
    def reject_unsafe_production_settings(self) -> "Settings":
        if self.env == "production" and self.migration_only:
            if self.debug:
                raise ValueError("APP_DEBUG must be false in production migration mode")
            if self.migration_database_url is None:
                raise ValueError(
                    "APP_MIGRATION_DATABASE_URL is required in production migration mode"
                )
            return self

        development_secrets = {
            "local-development-secret-change-me-now",
            "local-compose-secret-change-before-any-shared-deployment",
        }
        if self.env == "production" and self.jwt_secret in development_secrets:
            raise ValueError("APP_JWT_SECRET must be replaced before production startup")
        if self.env == "production" and any(origin == "*" for origin in self.cors_origin_list):
            raise ValueError("Wildcard CORS origins are not allowed in production")
        if self.env == "production" and not self.cors_origin_list:
            raise ValueError("Production requires an explicit APP_CORS_ORIGINS allowlist")
        if self.env == "production" and self.debug:
            raise ValueError("APP_DEBUG must be false in production")
        if self.env == "production" and self.cookie_secure is False:
            raise ValueError("APP_COOKIE_SECURE cannot be false in production")
        if self.env == "production" and any(
            not origin.startswith("https://") for origin in self.cors_origin_list
        ):
            raise ValueError("Production CORS origins must use HTTPS")
        if self.env == "production" and self.trusted_proxy_mode == "explicit":
            if not self.trusted_proxy_ip_list:
                raise ValueError("Production requires explicit APP_TRUSTED_PROXY_IPS")
            try:
                for address_or_network in self.trusted_proxy_ip_list:
                    ip_network(address_or_network, strict=False)
            except ValueError as exc:
                raise ValueError(
                    "APP_TRUSTED_PROXY_IPS must contain only explicit IP addresses or CIDR ranges"
                ) from exc
        if (
            self.env == "production"
            and self.trusted_proxy_mode == "azure-container-apps"
            and self.trusted_proxy_ip_list
        ):
            raise ValueError("Azure Container Apps proxy mode must not set APP_TRUSTED_PROXY_IPS")
        if self.env == "production" and self.document_lab_enabled:
            if self.document_lab_encryption_key is None:
                raise ValueError("APP_DOCUMENT_LAB_ENCRYPTION_KEY is required for Document Lab")
            if self.document_lab_storage_provider == "local-encrypted":
                raise ValueError(
                    "Production Document Lab requires a reviewed remote storage provider"
                )
            if self.document_lab_storage_provider != "s3-compatible" or not all(
                [
                    self.document_lab_s3_bucket,
                    self.document_lab_s3_region,
                    self.document_lab_s3_kms_key_id,
                ]
            ):
                raise ValueError(
                    "Production Document Lab requires S3 bucket, region, and "
                    "managed KMS key configuration"
                )
            if self.document_lab_scanner_provider != "clamav":
                raise ValueError("Production Document Lab requires an available ClamAV scanner")
            if not self.document_lab_parser_isolation_enabled:
                raise ValueError(
                    "Production Document Lab requires isolated no-network parser workers"
                )
            if (
                self.document_lab_provider != "unavailable"
                and not self.document_lab_remote_analysis_approved
            ):
                raise ValueError(
                    "Remote Document Lab analysis requires explicit privacy and vendor approval"
                )
        if self.env == "production":
            if self.rate_limit_backend != "redis" or self.rate_limit_redis_url is None:
                raise ValueError(
                    "Production requires APP_RATE_LIMIT_BACKEND=redis and APP_RATE_LIMIT_REDIS_URL"
                )
            if self.email_provider != "smtp":
                raise ValueError("Production requires a configured transactional email provider")
            if not all(
                [
                    self.email_from,
                    self.email_smtp_host,
                    self.email_smtp_username,
                    self.email_smtp_password,
                ]
            ):
                raise ValueError("Production SMTP settings are incomplete")
            if self.beta_enabled:
                if not all(
                    [
                        self.beta_product_owner_contact,
                        self.beta_support_contact,
                        self.beta_moderation_contact,
                        self.beta_data_quality_contact,
                        self.beta_incident_contact,
                    ]
                ):
                    raise ValueError(
                        "Production beta requires named product, support, moderation, "
                        "data-quality, and incident contacts"
                    )
                if not self.webauthn_rp_id or not self.webauthn_origin_list:
                    raise ValueError(
                        "Production beta requires APP_WEBAUTHN_RP_ID and APP_WEBAUTHN_ORIGINS"
                    )
                for origin in self.webauthn_origin_list:
                    parsed = urlparse(origin)
                    hostname = parsed.hostname
                    valid_host = hostname and (
                        hostname == self.webauthn_rp_id
                        or hostname.endswith(f".{self.webauthn_rp_id}")
                    )
                    if (
                        parsed.scheme != "https"
                        or not valid_host
                        or parsed.path not in {"", "/"}
                        or parsed.params
                        or parsed.query
                        or parsed.fragment
                        or parsed.username
                        or parsed.password
                    ):
                        raise ValueError(
                            "Production WebAuthn origins must be HTTPS origins for "
                            "APP_WEBAUTHN_RP_ID"
                        )
            if self.assistant_enabled and self.assistant_provider != "evidence-template":
                raise ValueError(
                    "Production assistant requires the reviewed evidence-template provider"
                )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def webauthn_origin_list(self) -> list[str]:
        return [
            item.strip().rstrip("/") for item in self.webauthn_origins.split(",") if item.strip()
        ]

    @property
    def trusted_proxy_ip_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxy_ips.split(",") if item.strip()]

    @property
    def database_url_for_migrations(self) -> str:
        """Return the migration-only credential without exposing it to API workers."""
        if self.env == "production" and self.migration_database_url is None:
            raise ValueError("Production migrations require APP_MIGRATION_DATABASE_URL")
        return (
            self.migration_database_url.get_secret_value()
            if self.migration_database_url is not None
            else self.database_url
        )

    @property
    def refresh_cookie_secure(self) -> bool:
        return self.env == "production" if self.cookie_secure is None else self.cookie_secure


@lru_cache
def get_settings() -> Settings:
    return Settings()
