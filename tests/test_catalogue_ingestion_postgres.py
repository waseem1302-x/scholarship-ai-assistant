import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.modules.catalogue_ingestion.models import (
    CatalogueCandidate,
    CatalogueIngestionRun,
    IngestionMode,
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
