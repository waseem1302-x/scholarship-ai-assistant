from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.modules.catalogue_ingestion.provider_attempts import ProviderFailureClass
from app.modules.catalogue_ingestion.provider_config import catalogue_configuration_fingerprint


def test_authentication_failure_opens_scoped_provider_circuit_immediately(db_session) -> None:
    from app.modules.catalogue_ingestion.scheduling import CatalogueProviderScheduler

    scheduler = CatalogueProviderScheduler(
        db_session,
        Settings(
            env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret="test-secret-that-is-at-least-32-characters-long",
        ),
    )
    observed_at = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    scheduler.record_failure(
        provider="azure_openai",
        deployment="extract-v1",
        failure_class=ProviderFailureClass.AUTHENTICATION_CONFIGURATION_ERROR,
        observed_at=observed_at,
    )

    admission = scheduler.admit(
        provider="azure_openai",
        deployment="extract-v1",
        logical_job_key="job-1",
        observed_at=observed_at,
    )

    assert admission.allowed is False
    assert admission.reason == "provider_circuit_open"
    assert admission.decision_id is not None


def test_scheduler_limits_participate_in_run_configuration_receipt() -> None:
    base = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
    )
    changed = base.model_copy(update={"catalogue_provider_max_concurrency_per_deployment": 5})

    assert catalogue_configuration_fingerprint(base) != catalogue_configuration_fingerprint(changed)


def test_half_open_circuit_allows_only_one_probe(db_session) -> None:
    from app.modules.catalogue_ingestion.scheduling import CatalogueProviderScheduler

    settings = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
        catalogue_provider_circuit_open_seconds=60,
    )
    scheduler = CatalogueProviderScheduler(db_session, settings)
    opened_at = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    scheduler.record_failure(
        provider="fake_provider",
        deployment="extract-v1",
        failure_class=ProviderFailureClass.AUTHENTICATION_CONFIGURATION_ERROR,
        observed_at=opened_at,
    )
    probe_at = opened_at + timedelta(seconds=61)

    first = scheduler.admit(
        provider="fake_provider",
        deployment="extract-v1",
        logical_job_key="probe-1",
        observed_at=probe_at,
    )
    second = scheduler.admit(
        provider="fake_provider",
        deployment="extract-v1",
        logical_job_key="probe-2",
        observed_at=probe_at,
    )

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "provider_circuit_open"
