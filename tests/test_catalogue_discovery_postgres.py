import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.modules.catalogue_ingestion.discovery import (
    DiscoveryObjective,
    DiscoveryObjectiveKind,
    DiscoveryPrioritySnapshot,
    DiscoveryQueryPlanner,
)
from app.modules.catalogue_ingestion.discovery_models import (
    CatalogueDiscoveryAssessment,
    CatalogueDiscoveryAttempt,
    CatalogueDiscoveryLead,
    CatalogueDiscoveryObservation,
    CatalogueDiscoveryQuery,
    CatalogueDiscoveryRun,
    DiscoveryAttemptStatus,
    DiscoveryOfficialityStatus,
)
from app.modules.catalogue_ingestion.discovery_repository import (
    CatalogueDiscoveryRepository,
    DiscoveryAssessmentInput,
    DiscoveryAttemptOutcome,
    DiscoveryBudgetExhausted,
    DiscoveryRunLimits,
)

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for discovery concurrency tests")
    engine = create_engine(database_url, pool_size=4, max_overflow=0, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    yield engine
    engine.dispose()


def _create_run(
    session,
    *,
    max_provider_calls: int = 2,
    max_tool_calls: int | None = None,
    max_estimated_cost: Decimal | None = None,
) -> CatalogueDiscoveryRun:
    objective = DiscoveryObjective(
        objective_kind=DiscoveryObjectiveKind.RESOLVE_CANONICAL_SOURCE,
        field_paths=("identity.official_source",),
        reason_codes=("OFFICIAL_SOURCE_MISSING",),
        criticality_tier=0,
        scholarship_name=f"Concurrency Scholarship {uuid.uuid4().hex}",
        provider_name="Concurrency Provider",
    )
    plans = DiscoveryQueryPlanner(max_queries=2).plan(objective)
    return CatalogueDiscoveryRepository(session).create_run(
        objective=objective,
        priority=DiscoveryPrioritySnapshot(
            blocking_class=0,
            criticality_tier=0,
            conflict_or_stale_rank=1,
            current_cycle_rank=2,
            deterministic_tiebreak=uuid.uuid4().hex,
        ),
        plans=plans,
        provider="fake",
        model="fake-web-search-v1",
        limits=DiscoveryRunLimits(
            max_queries=2,
            max_provider_calls=max_provider_calls,
            max_tool_calls=max_tool_calls or max_provider_calls,
            max_leads=5,
            max_response_bytes=10_000,
            max_estimated_cost=(
                max_estimated_cost
                if max_estimated_cost is not None
                else Decimal("0.10") * max_provider_calls
            ),
        ),
    )


def _cleanup(sessions, *run_ids: uuid.UUID) -> None:
    with sessions() as cleanup:
        query_ids = select(CatalogueDiscoveryQuery.id).where(
            CatalogueDiscoveryQuery.run_id.in_(run_ids)
        )
        lead_ids = list(
            cleanup.scalars(
                select(CatalogueDiscoveryObservation.lead_id).where(
                    CatalogueDiscoveryObservation.query_id.in_(query_ids)
                )
            )
        )
        cleanup.execute(
            delete(CatalogueDiscoveryAssessment).where(
                CatalogueDiscoveryAssessment.run_id.in_(run_ids)
            )
        )
        cleanup.execute(
            delete(CatalogueDiscoveryObservation).where(
                CatalogueDiscoveryObservation.query_id.in_(query_ids)
            )
        )
        cleanup.execute(
            delete(CatalogueDiscoveryAttempt).where(
                CatalogueDiscoveryAttempt.query_id.in_(query_ids)
            )
        )
        cleanup.execute(
            delete(CatalogueDiscoveryQuery).where(CatalogueDiscoveryQuery.run_id.in_(run_ids))
        )
        cleanup.execute(delete(CatalogueDiscoveryRun).where(CatalogueDiscoveryRun.id.in_(run_ids)))
        if lead_ids:
            cleanup.execute(
                delete(CatalogueDiscoveryLead).where(CatalogueDiscoveryLead.id.in_(lead_ids))
            )
        cleanup.commit()


def test_discovery_query_claim_skips_a_row_locked_by_another_worker(postgres_engine) -> None:
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with sessions() as setup:
        run = _create_run(setup)
        run_id = run.id

    locker = sessions()
    worker = sessions()
    try:
        locked = locker.scalar(
            select(CatalogueDiscoveryQuery)
            .where(CatalogueDiscoveryQuery.run_id == run_id)
            .order_by(CatalogueDiscoveryQuery.ordinal)
            .limit(1)
            .with_for_update()
        )
        assert locked is not None
        claimed = CatalogueDiscoveryRepository(worker).claim_queries(
            run_id=run_id,
            worker_id="discovery-worker-two",
            limit=1,
            lease_seconds=60,
            max_attempts=3,
        )
        assert len(claimed) == 1
        assert claimed[0].id != locked.id
    finally:
        locker.rollback()
        worker.close()
        locker.close()
        _cleanup(sessions, run_id)


@pytest.mark.parametrize(
    ("max_provider_calls", "max_tool_calls", "max_estimated_cost"),
    (
        (1, 2, Decimal("0.20")),
        (2, 1, Decimal("0.20")),
        (2, 2, Decimal("0.10")),
    ),
    ids=("provider-call-ceiling", "tool-call-ceiling", "cost-ceiling"),
)
def test_atomic_reservation_allows_only_one_competing_provider_call(
    postgres_engine,
    max_provider_calls: int,
    max_tool_calls: int,
    max_estimated_cost: Decimal,
) -> None:
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with sessions() as setup:
        run = _create_run(
            setup,
            max_provider_calls=max_provider_calls,
            max_tool_calls=max_tool_calls,
            max_estimated_cost=max_estimated_cost,
        )
        run_id = run.id
    with sessions() as first_claim_session:
        first = CatalogueDiscoveryRepository(first_claim_session).claim_queries(
            run_id=run_id,
            worker_id="budget-worker-one",
            limit=1,
            lease_seconds=60,
            max_attempts=3,
        )[0]
        first_id = first.id
    with sessions() as second_claim_session:
        second = CatalogueDiscoveryRepository(second_claim_session).claim_queries(
            run_id=run_id,
            worker_id="budget-worker-two",
            limit=1,
            lease_seconds=60,
            max_attempts=3,
        )[0]
        second_id = second.id

    barrier = threading.Barrier(2)

    def reserve(query_id: uuid.UUID, worker_id: str, fingerprint: str) -> str:
        with sessions() as session:
            repository = CatalogueDiscoveryRepository(session)
            barrier.wait(timeout=10)
            try:
                repository.reserve_attempt(
                    query_id=query_id,
                    worker_id=worker_id,
                    request_fingerprint=fingerprint,
                    reserved_tool_calls=1,
                    reserved_estimated_cost=Decimal("0.10"),
                )
            except DiscoveryBudgetExhausted:
                return "rejected"
            return "reserved"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda arguments: reserve(*arguments),
                    (
                        (first_id, "budget-worker-one", "a" * 64),
                        (second_id, "budget-worker-two", "b" * 64),
                    ),
                )
            )
        assert sorted(results) == ["rejected", "reserved"]
        with sessions() as verify:
            persisted = verify.get(CatalogueDiscoveryRun, run_id)
            assert persisted is not None
            assert persisted.provider_calls_reserved == 1
            assert persisted.tool_calls_reserved == 1
            assert persisted.estimated_cost_reserved == Decimal("0.10")
            attempts = list(
                verify.scalars(
                    select(CatalogueDiscoveryAttempt)
                    .join(CatalogueDiscoveryQuery)
                    .where(CatalogueDiscoveryQuery.run_id == run_id)
                )
            )
            assert len(attempts) == 2
            assert {attempt.status.value for attempt in attempts} == {
                "in_progress",
                "budget_rejected",
            }
    finally:
        _cleanup(sessions, run_id)


def test_concurrent_identical_assessments_reuse_one_row(postgres_engine) -> None:
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with sessions() as setup:
        run = _create_run(setup)
        repository = CatalogueDiscoveryRepository(setup)
        query = repository.claim_queries(
            run_id=run.id,
            worker_id="assessment-setup",
            limit=1,
            lease_seconds=60,
            max_attempts=3,
        )[0]
        attempt = repository.reserve_attempt(
            query_id=query.id,
            worker_id="assessment-setup",
            request_fingerprint="c" * 64,
            reserved_tool_calls=1,
            reserved_estimated_cost=Decimal("0.10"),
        )
        repository.settle_attempt(
            attempt.id,
            DiscoveryAttemptOutcome(
                status=DiscoveryAttemptStatus.SUCCEEDED,
                web_search_executed=True,
                tool_call_count=1,
                result_url_count=1,
                response_bytes=100,
                estimated_tool_cost=Decimal("0.10"),
            ),
        )
        lead, _ = repository.record_lead_observation(
            query_id=query.id,
            url=f"https://example.test/{uuid.uuid4().hex}",
            discovery_reason="concurrency proof",
        )
        run_id = run.id
        lead_id = lead.id

    barrier = threading.Barrier(2)
    assessment_input = DiscoveryAssessmentInput(
        assessment_context_hash="d" * 64,
        context_type="candidate_root",
        officiality_status=DiscoveryOfficialityStatus.UNRESOLVED,
        owner_type="unknown",
        reason_code="CONCURRENCY_PROOF",
        reason_detail="Identical concurrent assessment.",
        classifier_version="official-source.concurrent-test",
    )

    def append() -> uuid.UUID:
        with sessions() as session:
            barrier.wait(timeout=10)
            return (
                CatalogueDiscoveryRepository(session)
                .append_assessment(
                    run_id=run_id,
                    lead_id=lead_id,
                    assessment=assessment_input,
                )
                .id
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            assessment_ids = list(executor.map(lambda _: append(), range(2)))
        assert len(set(assessment_ids)) == 1
        with sessions() as verify:
            persisted = list(
                verify.scalars(
                    select(CatalogueDiscoveryAssessment).where(
                        CatalogueDiscoveryAssessment.run_id == run_id
                    )
                )
            )
            assert len(persisted) == 1
    finally:
        _cleanup(sessions, run_id)


def test_concurrent_equivalent_urls_reuse_one_global_lead(postgres_engine) -> None:
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    run_ids: list[uuid.UUID] = []
    query_ids: list[uuid.UUID] = []
    with sessions() as setup:
        for worker_number in range(2):
            run = _create_run(setup)
            repository = CatalogueDiscoveryRepository(setup)
            query = repository.claim_queries(
                run_id=run.id,
                worker_id=f"url-setup-{worker_number}",
                limit=1,
                lease_seconds=60,
                max_attempts=3,
            )[0]
            attempt = repository.reserve_attempt(
                query_id=query.id,
                worker_id=f"url-setup-{worker_number}",
                request_fingerprint=str(worker_number + 1) * 64,
                reserved_tool_calls=1,
                reserved_estimated_cost=Decimal("0.10"),
            )
            repository.settle_attempt(
                attempt.id,
                DiscoveryAttemptOutcome(
                    status=DiscoveryAttemptStatus.SUCCEEDED,
                    web_search_executed=True,
                    tool_call_count=1,
                    result_url_count=1,
                    response_bytes=100,
                    estimated_tool_cost=Decimal("0.10"),
                ),
            )
            run_ids.append(run.id)
            query_ids.append(query.id)

    barrier = threading.Barrier(2)
    raw_urls = (
        "HTTPS://EXAMPLE.TEST:443/scholarship/?utm_source=one&b=2&a=1#fragment",
        "https://example.test/scholarship?a=1&b=2&utm_campaign=two",
    )

    def record(arguments: tuple[uuid.UUID, str]) -> uuid.UUID:
        query_id, raw_url = arguments
        with sessions() as session:
            barrier.wait(timeout=10)
            lead, _ = CatalogueDiscoveryRepository(session).record_lead_observation(
                query_id=query_id,
                url=raw_url,
                discovery_reason="concurrent normalization proof",
            )
            return lead.id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            lead_ids = list(executor.map(record, zip(query_ids, raw_urls, strict=True)))
        assert len(set(lead_ids)) == 1
        with sessions() as verify:
            leads = list(
                verify.scalars(
                    select(CatalogueDiscoveryLead).where(CatalogueDiscoveryLead.id == lead_ids[0])
                )
            )
            assert len(leads) == 1
            assert leads[0].normalized_url == "https://example.test/scholarship?a=1&b=2"
            observations = list(
                verify.scalars(
                    select(CatalogueDiscoveryObservation).where(
                        CatalogueDiscoveryObservation.lead_id == lead_ids[0]
                    )
                )
            )
            assert len(observations) == 2
            runs = list(
                verify.scalars(
                    select(CatalogueDiscoveryRun).where(CatalogueDiscoveryRun.id.in_(run_ids))
                )
            )
            assert len(runs) == 2
            assert all(run.unique_leads == 1 for run in runs)
    finally:
        _cleanup(sessions, *run_ids)
