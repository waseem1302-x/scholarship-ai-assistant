import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.modules.catalogue_ingestion.models import (
    CatalogueCandidate,
    CatalogueIngestionRun,
    IngestionMode,
    IngestionRunRetryClass,
    IngestionRunStatus,
)
from app.modules.catalogue_ingestion.repository import CatalogueIngestionRepository
from app.modules.catalogue_ingestion.schemas import SeedCandidate
from app.modules.opportunities.models import (
    DegreeLevel,
    Opportunity,
    OpportunityStatus,
    Provider,
    Source,
    SourceType,
    VerificationStatus,
)
from app.modules.opportunities.repository import OpportunityRepository

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for catalogue worker claim tests")
    engine = create_engine(database_url, pool_size=4, max_overflow=0, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    yield engine
    engine.dispose()


def _run() -> CatalogueIngestionRun:
    return CatalogueIngestionRun(
        source_label="postgres-concurrency-test.json",
        source_fingerprint=uuid.uuid4().hex.ljust(64, "0"),
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
        max_candidates=2,
        max_pages_per_candidate=1,
        max_model_calls=0,
        max_input_characters=1_000,
        max_output_tokens=256,
        max_estimated_cost=Decimal("0"),
    )


def test_candidate_worker_claim_skips_a_row_locked_by_another_worker(postgres_engine) -> None:
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with sessions() as setup:
        repository = CatalogueIngestionRepository(setup)
        run = _run()
        repository.add_run(run)
        repository.add_seed_candidates(
            run,
            [
                SeedCandidate(name=f"Locked Scholarship {uuid.uuid4().hex}"),
                SeedCandidate(name=f"Available Scholarship {uuid.uuid4().hex}"),
            ],
        )
        run_id = run.id

    locker = sessions()
    worker = sessions()
    try:
        locked = locker.scalar(
            select(CatalogueCandidate)
            .where(CatalogueCandidate.run_id == run_id)
            .order_by(CatalogueCandidate.seed_index)
            .limit(1)
            .with_for_update()
        )
        assert locked is not None
        claimed = CatalogueIngestionRepository(worker).claim_candidates(
            run_id=run_id,
            worker_id="postgres-worker-two",
            limit=1,
            lease_seconds=60,
        )
        assert len(claimed) == 1
        assert claimed[0].id != locked.id
    finally:
        locker.rollback()
        worker.close()
        locker.close()
        with sessions() as cleanup:
            persisted = cleanup.get(CatalogueIngestionRun, run_id)
            if persisted is not None:
                cleanup.delete(persisted)
                cleanup.commit()


def test_run_lease_reclaim_and_fencing_are_enforced_by_postgres(postgres_engine) -> None:
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with sessions() as setup:
        repository = CatalogueIngestionRepository(setup)
        run = _run()
        run.idempotency_key = f"postgres-fence-{uuid.uuid4().hex}"
        run.max_attempts = 2
        repository.add_run(run)
        setup.commit()
        run_id = run.id

    now = datetime.now(UTC)
    worker_one = sessions()
    worker_two = sessions()
    try:
        first = CatalogueIngestionRepository(worker_one).claim_runs(
            worker_id="postgres-worker-one", limit=1, lease_seconds=60, now=now
        )[0]
        first_token = first.lease_token
        second = CatalogueIngestionRepository(worker_two).claim_runs(
            worker_id="postgres-worker-two",
            limit=1,
            lease_seconds=60,
            now=now + timedelta(seconds=61),
        )[0]
        assert second.lease_token != first_token
        assert second.attempt_count == 1
        assert (
            CatalogueIngestionRepository(worker_one).complete_run_claim(
                run_id, lease_token=first_token or ""
            )
            is False
        )
        assert (
            CatalogueIngestionRepository(worker_two).fail_run_claim(
                run_id,
                lease_token=second.lease_token or "",
                error_code="postgres_transient_failure",
                error_reason="transient source boundary failure",
                retry_class=IngestionRunRetryClass.TRANSIENT,
                retry_delay_seconds=30,
                now=now + timedelta(seconds=61),
            )
            is True
        )
        worker_two.expire_all()
        persisted = worker_two.get(CatalogueIngestionRun, run_id)
        assert persisted is not None
        assert persisted.status is IngestionRunStatus.PENDING
    finally:
        worker_one.close()
        worker_two.close()
        with sessions() as cleanup:
            persisted = cleanup.get(CatalogueIngestionRun, run_id)
            if persisted is not None:
                cleanup.delete(persisted)
                cleanup.commit()


def test_model_budget_reservation_is_atomic_under_postgres_concurrency(postgres_engine) -> None:
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with sessions() as setup:
        repository = CatalogueIngestionRepository(setup)
        run = _run()
        run.idempotency_key = f"postgres-budget-{uuid.uuid4().hex}"
        run.mode = IngestionMode.EXTRACTION
        run.max_model_calls = 1
        run.max_estimated_cost = Decimal("0.010")
        repository.add_run(run)
        setup.commit()
        claimed = repository.claim_run(
            run.id,
            worker_id="postgres-budget-worker",
            lease_seconds=60,
        )
        assert claimed is not None
        run_id = run.id
        lease_token = claimed.lease_token
        assert lease_token is not None

    def reserve() -> bool:
        with sessions() as worker:
            return CatalogueIngestionRepository(worker).reserve_model_budget(
                run_id,
                lease_token=lease_token,
                projected_cost=Decimal("0.005"),
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: reserve(), range(2)))

        assert sorted(outcomes) == [False, True]
        with sessions() as check:
            persisted = check.get(CatalogueIngestionRun, run_id)
            assert persisted is not None
            assert persisted.model_calls == 1
            assert persisted.estimated_cost == Decimal("0.005000")
    finally:
        with sessions() as cleanup:
            persisted = cleanup.get(CatalogueIngestionRun, run_id)
            if persisted is not None:
                cleanup.delete(persisted)
                cleanup.commit()


def test_source_monitor_queue_skips_a_locked_due_source(postgres_engine) -> None:
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    marker = uuid.uuid4().hex
    with sessions() as setup:
        provider = Provider(name=f"Claim Provider {marker}")
        opportunities = []
        for index in range(2):
            opportunity = Opportunity(
                provider=provider,
                name=f"Claim Opportunity {marker} {index}",
                country="Canada",
                degree_level=DegreeLevel.MASTERS,
                status=OpportunityStatus.ACTIVE,
            )
            opportunity.sources.append(
                Source(
                    url=f"https://example.edu/{marker}/{index}",
                    source_type=SourceType.OFFICIAL,
                    title="Official source",
                    relevant_excerpt="Official source evidence for queue concurrency testing.",
                    verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
                    last_verified_at=now,
                    last_updated_at=now - timedelta(days=8),
                )
            )
            opportunities.append(opportunity)
        setup.add_all(opportunities)
        setup.commit()
        opportunity_ids = [item.id for item in opportunities]

    locker = sessions()
    worker = sessions()
    try:
        locked = locker.scalar(
            select(Source)
            .join(Opportunity)
            .where(Opportunity.id.in_(opportunity_ids))
            .order_by(Source.url)
            .limit(1)
            .with_for_update()
        )
        assert locked is not None
        claimed = OpportunityRepository(worker).claim_sources_due_for_monitoring(
            now=now,
            check_interval_days=7,
            freshness_days=14,
            limit=1,
            lease_seconds=60,
        )
        assert len(claimed) == 1
        assert claimed[0].id != locked.id
    finally:
        locker.rollback()
        worker.close()
        locker.close()
        with sessions() as cleanup:
            for opportunity_id in opportunity_ids:
                opportunity = cleanup.get(Opportunity, opportunity_id)
                if opportunity is not None:
                    cleanup.delete(opportunity)
            provider = cleanup.scalar(
                select(Provider).where(Provider.name == f"Claim Provider {marker}")
            )
            if provider is not None:
                cleanup.delete(provider)
            cleanup.commit()
