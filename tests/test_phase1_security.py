import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.auth.dependencies import require_verified_student
from app.modules.auth.models import User, UserRole


def test_production_rejects_development_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="APP_JWT_SECRET"):
        Settings(env="production", jwt_secret="local-development-secret-change-me-now")


def test_production_requires_separate_migration_credential() -> None:
    with pytest.raises(ValueError, match="MIGRATION_DATABASE_URL"):
        _ = Settings(
            **_production_settings(migration_database_url=None)
        ).database_url_for_migrations


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"debug": True}, "APP_DEBUG"),
        ({"cookie_secure": False}, "APP_COOKIE_SECURE"),
        ({"cors_origins": "http://beta.example.test"}, "CORS origins must use HTTPS"),
        ({"cors_origins": ""}, "explicit APP_CORS_ORIGINS"),
        ({"trusted_proxy_ips": ""}, "explicit APP_TRUSTED_PROXY_IPS"),
        ({"trusted_proxy_ips": "*"}, "only explicit IP addresses or CIDR ranges"),
        ({"trusted_proxy_ips": "proxy.internal"}, "only explicit IP addresses or CIDR ranges"),
        (
            {"trusted_proxy_mode": "azure-container-apps", "trusted_proxy_ips": "10.0.0.10"},
            "Azure Container Apps proxy mode",
        ),
    ],
)
def test_production_rejects_insecure_http_controls(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(
            **_production_settings(
                **changes,
            )
        )


def test_production_requires_phase_nine_shared_limiter_and_transactional_email() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT"):
        Settings(
            env="production",
            jwt_secret="production-secret-that-is-at-least-32-characters-long",
            migration_database_url="postgresql+psycopg://migrator:secret@example.test/scholarship",
            cors_origins="https://beta.example.test",
            trusted_proxy_ips="10.0.0.10",
        )


def test_production_migration_mode_needs_only_the_migration_secret() -> None:
    settings = Settings(
        env="production",
        migration_only=True,
        migration_database_url="postgresql+psycopg://migrator:secret@example.test/scholarship",
    )

    assert settings.migration_only is True

    with pytest.raises(ValidationError, match="MIGRATION_DATABASE_URL"):
        Settings(env="production", migration_only=True)


def test_production_beta_requires_named_owners_and_passkey_relying_party() -> None:
    with pytest.raises(ValidationError, match="Production beta requires named"):
        Settings(
            env="production",
            jwt_secret="production-secret-that-is-at-least-32-characters-long",
            migration_database_url="postgresql+psycopg://migrator:secret@example.test/scholarship",
            rate_limit_backend="redis",
            rate_limit_redis_url="redis://example.test:6379/0",
            email_provider="smtp",
            email_from="Scholarship AI <support@example.test>",
            email_smtp_host="smtp.example.test",
            email_smtp_username="mailer",
            email_smtp_password="not-a-real-secret",
            beta_enabled=True,
            cors_origins="https://beta.example.test",
            trusted_proxy_ips="10.0.0.10",
        )


@pytest.mark.parametrize(
    "webauthn_origins",
    [
        "http://beta.example.test",
        "https://attacker.example.test",
        "https://beta.example.test/path",
        "https://user@beta.example.test",
    ],
)
def test_production_beta_rejects_webauthn_origins_outside_the_relying_party(
    webauthn_origins: str,
) -> None:
    with pytest.raises(ValidationError, match="Production WebAuthn origins"):
        Settings(
            **_production_settings(
                beta_enabled=True,
                beta_product_owner_contact="product@example.test",
                beta_support_contact="support@example.test",
                beta_moderation_contact="moderation@example.test",
                beta_data_quality_contact="data@example.test",
                beta_incident_contact="incident@example.test",
                webauthn_rp_id="beta.example.test",
                webauthn_origins=webauthn_origins,
            )
        )


def test_production_rejects_unreviewed_enabled_assistant_provider() -> None:
    with pytest.raises(ValidationError, match="reviewed evidence-template provider"):
        Settings(
            **_production_settings(
                assistant_enabled=True,
                assistant_provider="unreviewed-remote-provider",
            )
        )


def _production_settings(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "env": "production",
        "jwt_secret": "production-secret-that-is-at-least-32-characters-long",
        "migration_database_url": "postgresql+psycopg://migrator:secret@example.test/scholarship",
        "rate_limit_backend": "redis",
        "rate_limit_redis_url": "redis://example.test:6379/0",
        "email_provider": "smtp",
        "email_from": "Scholarship AI <support@example.test>",
        "email_smtp_host": "smtp.example.test",
        "email_smtp_username": "mailer",
        "email_smtp_password": "not-a-real-secret",
        "cors_origins": "https://beta.example.test",
        "trusted_proxy_ips": "10.0.0.10",
    }
    values.update(changes)
    return values


def test_production_document_lab_requires_scanner_and_isolated_parser() -> None:
    with pytest.raises(ValidationError, match="ClamAV"):
        Settings(
            **_production_settings(
                document_lab_enabled=True,
                document_lab_encryption_key="uDMSMy2eqtBsVCjUMgSWG2WD4Zlbn_EsF4T14j8A4Yw=",
                document_lab_storage_provider="s3-compatible",
                document_lab_s3_bucket="private-documents",
                document_lab_s3_region="ap-southeast-1",
                document_lab_s3_kms_key_id="alias/documents",
            )
        )

    with pytest.raises(ValidationError, match="no-network"):
        Settings(
            **_production_settings(
                document_lab_enabled=True,
                document_lab_encryption_key="uDMSMy2eqtBsVCjUMgSWG2WD4Zlbn_EsF4T14j8A4Yw=",
                document_lab_storage_provider="s3-compatible",
                document_lab_s3_bucket="private-documents",
                document_lab_s3_region="ap-southeast-1",
                document_lab_s3_kms_key_id="alias/documents",
                document_lab_scanner_provider="clamav",
            )
        )


def test_production_document_lab_remote_analysis_requires_explicit_approval() -> None:
    with pytest.raises(ValidationError, match="privacy and vendor approval"):
        Settings(
            **_production_settings(
                document_lab_enabled=True,
                document_lab_encryption_key="uDMSMy2eqtBsVCjUMgSWG2WD4Zlbn_EsF4T14j8A4Yw=",
                document_lab_storage_provider="s3-compatible",
                document_lab_s3_bucket="private-documents",
                document_lab_s3_region="ap-southeast-1",
                document_lab_s3_kms_key_id="alias/documents",
                document_lab_scanner_provider="clamav",
                document_lab_parser_isolation_enabled=True,
                document_lab_provider="reviewed-remote-provider",
            )
        )


def test_unverified_student_is_blocked_from_production_personal_content_writes() -> None:
    student = User(
        id=uuid.uuid4(),
        email="unverified@example.test",
        password_hash="not-used",
        role=UserRole.STUDENT,
    )
    with pytest.raises(AppError, match="Verify your email"):
        require_verified_student(student, Settings(**_production_settings()))

    student.email_verified_at = datetime.now(UTC)
    assert require_verified_student(student, Settings(**_production_settings())) is student


def test_primary_response_has_browser_security_headers(client) -> None:
    response = client.get("/")

    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]


def test_operational_health_exposes_only_safe_aggregate_data(client) -> None:
    response = client.get("/health/operations")

    assert response.status_code == 200
    assert response.json()["rate_limit_store_healthy"] is True
    assert response.json()["account_email_healthy"] is False
    assert "student@example.com" not in response.text


def test_phase_three_client_keeps_access_tokens_in_memory_and_uses_csrf_protection() -> None:
    javascript = (Path("frontend/src/api/client.ts")).read_text(encoding="utf-8")

    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert 'credentials: "same-origin"' in javascript
    assert '"X-CSRF-Token"' in javascript
