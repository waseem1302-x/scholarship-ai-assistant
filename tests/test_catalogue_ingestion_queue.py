from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import Settings
from app.modules.catalogue_ingestion.models import (
    CatalogueIngestionRun,
    IngestionMode,
    IngestionRunRetryClass,
    IngestionRunStage,
    IngestionRunStatus,
)
from app.modules.catalogue_ingestion.repository import CatalogueIngestionRepository
from app.modules.catalogue_ingestion.service import CatalogueIngestionService


def _run(*, idempotency_key: str) -> CatalogueIngestionRun:
    return CatalogueIngestionRun(
        source_label="queue-contract",
        source_fingerprint="a" * 64,
        idempotency_key=idempotency_key,
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
        max_candidates=1,
        max_pages_per_candidate=1,
        max_model_calls=0,
        max_input_characters=1_000,
        max_output_tokens=256,
        max_estimated_cost=Decimal("0"),
    )


def test_direct_url_enqueue_is_idempotent_and_performs_no_acquisition(db_session) -> None:
    class UnexpectedFetcher:
        # The assertion is that enqueue never calls this method.
        def fetch(self, _url: str):  # pragma: no cover
            raise AssertionError("enqueue must not acquire a source")

    service = CatalogueIngestionService(db_session, Settings(), fetcher=UnexpectedFetcher())

    first = service.create_run_from_url(
        "https://scholarships.gov.uk/queue-contract",
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
        idempotency_key="admin-request-queue-contract",
    )
    second = service.create_run_from_url(
        "https://scholarships.gov.uk/queue-contract",
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
        idempotency_key="admin-request-queue-contract",
    )

    assert first.id == second.id
    assert first.status is IngestionRunStatus.PENDING
    assert db_session.scalar(select(func.count()).select_from(CatalogueIngestionRun)) == 1


def test_expired_run_lease_is_reclaimed_with_a_new_fencing_token(db_session) -> None:
    repository = CatalogueIngestionRepository(db_session)
    run = _run(idempotency_key="lease-reclaim")
    repository.add_run(run)
    db_session.commit()
    now = datetime.now(UTC)

    first = repository.claim_runs(worker_id="worker-one", limit=1, lease_seconds=60, now=now)
    assert [item.id for item in first] == [run.id]
    first_token = first[0].lease_token
    assert first_token

    second = repository.claim_runs(
        worker_id="worker-two", limit=1, lease_seconds=60, now=now + timedelta(seconds=61)
    )

    assert [item.id for item in second] == [run.id]
    assert second[0].lease_token and second[0].lease_token != first_token
    assert second[0].stage is IngestionRunStage.ACQUIRING
    assert second[0].attempt_count == 1


def test_stale_worker_cannot_complete_a_reclaimed_run(db_session) -> None:
    repository = CatalogueIngestionRepository(db_session)
    run = _run(idempotency_key="stale-fence")
    repository.add_run(run)
    db_session.commit()
    now = datetime.now(UTC)
    first = repository.claim_runs(worker_id="worker-one", limit=1, lease_seconds=60, now=now)[0]
    first_token = first.lease_token
    second = repository.claim_runs(
        worker_id="worker-two", limit=1, lease_seconds=60, now=now + timedelta(seconds=61)
    )[0]

    assert repository.complete_run_claim(run.id, lease_token=first_token or "") is False
    assert repository.complete_run_claim(run.id, lease_token=second.lease_token or "") is True

    persisted = repository.get_run(run.id)
    assert persisted is not None
    assert persisted.status is IngestionRunStatus.COMPLETED
    assert persisted.lease_token is None


def test_transient_failure_retries_then_dead_letters_at_attempt_limit(db_session) -> None:
    repository = CatalogueIngestionRepository(db_session)
    run = _run(idempotency_key="retry-dead-letter")
    run.max_attempts = 2
    repository.add_run(run)
    db_session.commit()
    now = datetime.now(UTC)

    first = repository.claim_runs(worker_id="worker-one", limit=1, lease_seconds=60, now=now)[0]
    assert (
        repository.fail_run_claim(
            run.id,
            lease_token=first.lease_token or "",
            error_code="upstream_timeout",
            error_reason="safe fetch timed out",
            retry_class=IngestionRunRetryClass.TRANSIENT,
            retry_delay_seconds=30,
            now=now,
        )
        is True
    )
    pending = repository.get_run(run.id)
    assert pending is not None
    assert pending.status is IngestionRunStatus.PENDING
    assert pending.next_attempt_at == now + timedelta(seconds=30)

    second = repository.claim_runs(
        worker_id="worker-two", limit=1, lease_seconds=60, now=now + timedelta(seconds=31)
    )[0]
    assert (
        repository.fail_run_claim(
            run.id,
            lease_token=second.lease_token or "",
            error_code="upstream_timeout",
            error_reason="safe fetch timed out again",
            retry_class=IngestionRunRetryClass.TRANSIENT,
            retry_delay_seconds=30,
            now=now + timedelta(seconds=31),
        )
        is True
    )

    dead = repository.get_run(run.id)
    assert dead is not None
    assert dead.status is IngestionRunStatus.DEAD_LETTER
    assert dead.dead_lettered_at == now + timedelta(seconds=31)
    assert dead.failure_code == "upstream_timeout"
