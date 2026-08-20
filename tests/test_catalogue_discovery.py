import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, select

from app.modules.catalogue_ingestion.discovery import (
    DiscoveryObjective,
    DiscoveryObjectiveKind,
    DiscoveryPrioritySnapshot,
    DiscoveryQueryPlan,
    DiscoveryQueryPlanner,
)
from app.modules.catalogue_ingestion.discovery_models import (
    CatalogueDiscoveryAttempt,
    CatalogueDiscoveryLead,
    CatalogueDiscoveryObservation,
    CatalogueDiscoveryQuery,
    CatalogueDiscoveryRun,
    DiscoveryAttemptStatus,
    DiscoveryOfficialityStatus,
    DiscoveryQueryStatus,
    DiscoveryRunStatus,
)
from app.modules.catalogue_ingestion.discovery_provider import (
    DiscoveryProviderError,
    DiscoveryProviderRequest,
    DiscoveryProviderResult,
    FakeDiscoveryProvider,
)
from app.modules.catalogue_ingestion.discovery_repository import (
    CatalogueDiscoveryRepository,
    DiscoveryAssessmentInput,
    DiscoveryAttemptOutcome,
    DiscoveryBudgetExhausted,
    DiscoveryRunLimits,
    DiscoveryStateError,
    DiscoveryURLRejected,
)
from app.modules.catalogue_ingestion.discovery_service import (
    CatalogueDiscoveryExecutionService,
    CatalogueDiscoveryLeadIngestionService,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueIngestionRun,
    IngestionMode,
)
from app.modules.catalogue_ingestion.url_policy import URLRejectionCode


def _candidate(db_session) -> CatalogueCandidate:
    ingestion_run = CatalogueIngestionRun(
        source_label="discovery-test.json",
        source_fingerprint=uuid.uuid4().hex.ljust(64, "0"),
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
        max_candidates=1,
        max_pages_per_candidate=1,
        max_model_calls=0,
        max_input_characters=1_000,
        max_output_tokens=256,
        max_estimated_cost=Decimal("0"),
    )
    db_session.add(ingestion_run)
    db_session.flush()
    candidate = CatalogueCandidate(
        run_id=ingestion_run.id,
        seed_index=0,
        idempotency_key=uuid.uuid4().hex.ljust(64, "0"),
        seed_name="Example Scholarship",
        seed_provider="Example Ministry",
        seed_country="United Kingdom",
    )
    db_session.add(candidate)
    db_session.commit()
    return candidate


def _objective(candidate_id: uuid.UUID | None = None, **overrides) -> DiscoveryObjective:
    values = {
        "objective_kind": DiscoveryObjectiveKind.RESOLVE_CANONICAL_SOURCE,
        "candidate_id": candidate_id,
        "field_paths": ("identity.official_source", "identity.provider"),
        "reason_codes": ("OFFICIAL_SOURCE_MISSING",),
        "criticality_tier": 0,
        "scholarship_name": "Example Scholarship",
        "provider_name": "Example Ministry",
        "country": "United Kingdom",
        "reviewed_domains": ("scholarships.gov.uk",),
    }
    values.update(overrides)
    return DiscoveryObjective(**values)


def _priority() -> DiscoveryPrioritySnapshot:
    return DiscoveryPrioritySnapshot(
        blocking_class=0,
        criticality_tier=0,
        conflict_or_stale_rank=1,
        current_cycle_rank=2,
        deterministic_tiebreak="example-scholarship",
        reason_codes=("OFFICIAL_SOURCE_MISSING",),
    )


def _limits(**overrides) -> DiscoveryRunLimits:
    values = {
        "max_queries": 2,
        "max_provider_calls": 2,
        "max_tool_calls": 2,
        "max_leads": 5,
        "max_response_bytes": 50_000,
        "max_estimated_cost": Decimal("1.00"),
    }
    values.update(overrides)
    return DiscoveryRunLimits(**values)


def _run(db_session, candidate_id: uuid.UUID | None = None, **limit_overrides):
    objective = _objective(candidate_id)
    plans = DiscoveryQueryPlanner(max_queries=2).plan(objective)
    repository = CatalogueDiscoveryRepository(db_session)
    run = repository.create_run(
        objective=objective,
        priority=_priority(),
        plans=plans,
        provider="fake",
        model="fake-web-search-v1",
        limits=_limits(**limit_overrides),
    )
    queries = list(
        db_session.scalars(
            select(CatalogueDiscoveryQuery)
            .where(CatalogueDiscoveryQuery.run_id == run.id)
            .order_by(CatalogueDiscoveryQuery.ordinal)
        )
    )
    return repository, run, queries


def _claim(repository, run_id, *, worker="worker-1", now=None):
    return repository.claim_queries(
        run_id=run_id,
        worker_id=worker,
        limit=1,
        lease_seconds=60,
        max_attempts=3,
        now=now,
    )[0]


def _settle_success(repository, query, *, worker="worker-1"):
    attempt = repository.reserve_attempt(
        query_id=query.id,
        worker_id=worker,
        request_fingerprint="a" * 64,
        reserved_tool_calls=1,
        reserved_estimated_cost=Decimal("0.10"),
    )
    repository.settle_attempt(
        attempt.id,
        DiscoveryAttemptOutcome(
            status=DiscoveryAttemptStatus.SUCCEEDED,
            provider_response_id=f"response-{attempt.attempt_number}",
            web_search_executed=True,
            tool_call_count=1,
            result_url_count=1,
            response_bytes=500,
            estimated_model_cost=Decimal("0.01"),
            estimated_tool_cost=Decimal("0.02"),
            latency_ms=25,
        ),
    )
    return attempt


def test_objective_is_public_only_normalized_and_deterministic() -> None:
    first = _objective(
        field_paths=("identity.provider", "identity.official_source"),
        reason_codes=("OFFICIAL_SOURCE_MISSING", "PROVIDER_UNRESOLVED"),
        scholarship_aliases=(" Example Award ", "Example Award"),
        reviewed_domains=("SCHOLARSHIPS.GOV.UK.", "scholarships.gov.uk"),
    )
    second = _objective(
        field_paths=("identity.official_source", "identity.provider"),
        reason_codes=("PROVIDER_UNRESOLVED", "OFFICIAL_SOURCE_MISSING"),
        scholarship_aliases=("Example Award",),
        reviewed_domains=("scholarships.gov.uk",),
    )
    first_plan = DiscoveryQueryPlanner(max_queries=2).plan(first)
    second_plan = DiscoveryQueryPlanner(max_queries=2).plan(second)
    assert [item.query_hash for item in first_plan] == [item.query_hash for item in second_plan]
    assert first.reviewed_domains == ("scholarships.gov.uk",)
    assert first.scholarship_aliases == ("Example Award",)
    assert first_plan[0].query_text == '"Example Scholarship" official scholarship'
    assert "student" not in str(first_plan[0].public_context).casefold()

    with pytest.raises(ValidationError, match="extra_forbidden"):
        DiscoveryQueryPlan(
            ordinal=0,
            query_text="safe public query",
            query_hash="a" * 64,
            query_kind="test",
            public_context={
                **first_plan[0].public_context.model_dump(mode="json"),
                "applicant_profile": {"email": "private@example.test"},
            },
        )

    with pytest.raises(ValidationError, match="extra_forbidden"):
        DiscoveryObjective(
            **_objective().model_dump(),
            student_email="private@example.com",
        )
    with pytest.raises(ValidationError, match="bare public DNS names"):
        _objective(reviewed_domains=("https://example.edu/private",))
    with pytest.raises(ValidationError, match="unsupported discovery field paths"):
        _objective(field_paths=("applicant.gpa",))


def test_local_objectives_require_explicit_local_scope() -> None:
    with pytest.raises(ValidationError, match="resolved institution context"):
        _objective(
            objective_kind=DiscoveryObjectiveKind.INSTITUTION_LOCAL_DEADLINE,
            field_paths=("institution.local_deadline",),
            institution_name="Example University",
        )
    objective = _objective(
        objective_kind=DiscoveryObjectiveKind.INSTITUTION_LOCAL_DEADLINE,
        field_paths=("institution.local_deadline",),
        institution_id=uuid.uuid4(),
        institution_name="Example University",
        cycle_hint="2027",
    )
    plan = DiscoveryQueryPlanner(max_queries=1).plan(objective)
    assert plan[0].query_text == '"Example Scholarship" "Example University" deadline 2027'


def test_repository_rejects_tampered_plan_without_partial_run(db_session) -> None:
    objective = _objective()
    plans = DiscoveryQueryPlanner(max_queries=2).plan(objective)
    tampered = plans[0].model_copy(update={"query_hash": "f" * 64})
    repository = CatalogueDiscoveryRepository(db_session)
    before = list(db_session.scalars(select(CatalogueDiscoveryRun.id)))

    with pytest.raises(ValueError, match="hash does not match"):
        repository.create_run(
            objective=objective,
            priority=_priority(),
            plans=(tampered, *plans[1:]),
            provider="fake",
            model="fake-web-search-v1",
            limits=_limits(),
        )

    assert list(db_session.scalars(select(CatalogueDiscoveryRun.id))) == before


def test_priority_is_lexicographic_and_explainable() -> None:
    blocker = _priority()
    breadth = DiscoveryPrioritySnapshot(
        blocking_class=3,
        criticality_tier=2,
        conflict_or_stale_rank=3,
        current_cycle_rank=2,
        deterministic_tiebreak="institution-expansion",
    )
    assert blocker.sort_key < breadth.sort_key


def test_run_persists_bounded_typed_snapshots_without_private_columns(db_session) -> None:
    candidate = _candidate(db_session)
    _, run, queries = _run(db_session, candidate.id)
    assert run.target_candidate_id == candidate.id
    assert run.target_identity_snapshot["scholarship_name"] == "Example Scholarship"
    assert run.objective_scope["candidate_id"] == str(candidate.id)
    assert run.objective_priority_snapshot["blocking_class"] == 0
    assert len(queries) == 2

    column_names = {
        column["name"] for column in inspect(db_session.bind).get_columns(run.__tablename__)
    }
    assert not {
        "user_id",
        "student_id",
        "email",
        "profile",
        "application_id",
        "document_id",
    }.intersection(column_names)


def test_execution_reserves_before_provider_and_reconciles_attempt(db_session) -> None:
    repository, run, queries = _run(db_session)
    query = _claim(repository, run.id)
    result = DiscoveryProviderResult(
        provider_response_id="fake-response-1",
        web_search_executed=True,
        urls=("https://scholarships.gov.uk/example",),
        tool_call_count=1,
        response_bytes=800,
        latency_ms=40,
        input_tokens=20,
        output_tokens=5,
        estimated_model_cost=Decimal("0.01"),
        estimated_tool_cost=Decimal("0.02"),
    )
    provider = FakeDiscoveryProvider({queries[0].query_hash: result})
    returned = CatalogueDiscoveryExecutionService(db_session, provider).execute_claimed_query(
        query_id=query.id,
        worker_id="worker-1",
        max_urls=5,
        max_tool_calls=1,
        max_estimated_cost=Decimal("0.10"),
    )
    assert returned == result
    assert len(provider.requests) == 1
    db_session.refresh(run)
    db_session.refresh(query)
    assert run.provider_calls_reserved == 0
    assert run.provider_calls_completed == 1
    assert run.tool_calls_reserved == 0
    assert run.tool_calls_completed == 1
    assert run.estimated_cost_reserved == Decimal("0")
    assert run.estimated_cost_settled == Decimal("0.03")
    assert query.status is DiscoveryQueryStatus.RESPONSE_RECEIVED
    attempt = db_session.scalar(
        select(CatalogueDiscoveryAttempt).where(CatalogueDiscoveryAttempt.query_id == query.id)
    )
    assert attempt is not None
    assert attempt.status is DiscoveryAttemptStatus.SUCCEEDED
    assert attempt.estimated_total_cost == Decimal("0.03")


def test_budget_rejection_is_durable_and_prevents_provider_call(db_session) -> None:
    repository, run, queries = _run(db_session, max_provider_calls=0, max_tool_calls=0)
    query = _claim(repository, run.id)
    provider = FakeDiscoveryProvider(
        {
            queries[0].query_hash: DiscoveryProviderResult(
                web_search_executed=True,
                urls=("https://example.edu",),
                tool_call_count=1,
                response_bytes=100,
                latency_ms=1,
            )
        }
    )
    with pytest.raises(DiscoveryBudgetExhausted) as exc_info:
        CatalogueDiscoveryExecutionService(db_session, provider).execute_claimed_query(
            query_id=query.id,
            worker_id="worker-1",
            max_urls=5,
            max_tool_calls=1,
            max_estimated_cost=Decimal("0.10"),
        )
    assert provider.requests == []
    attempt = repository.get_attempt(exc_info.value.attempt_id)
    assert attempt is not None
    assert attempt.status is DiscoveryAttemptStatus.BUDGET_REJECTED
    assert run.status is DiscoveryRunStatus.BUDGET_EXHAUSTED
    assert query.status is DiscoveryQueryStatus.BUDGET_EXHAUSTED


def test_provider_contract_rejects_unbounded_or_unexecuted_results() -> None:
    request = DiscoveryProviderRequest(
        query_hash="b" * 64,
        query_text="Example Scholarship official",
        max_urls=1,
        max_response_bytes=100,
        max_tool_calls=1,
    )
    with pytest.raises(ValidationError, match="URLs require"):
        DiscoveryProviderResult(
            web_search_executed=False,
            urls=("https://example.edu",),
            tool_call_count=0,
            response_bytes=10,
            latency_ms=1,
        )
    provider = FakeDiscoveryProvider(
        {
            request.query_hash: DiscoveryProviderResult(
                web_search_executed=True,
                urls=("https://one.example", "https://two.example"),
                tool_call_count=1,
                response_bytes=50,
                latency_ms=1,
            )
        }
    )
    with pytest.raises(DiscoveryProviderError, match="provider_url_limit_exceeded"):
        provider.search(request)


def test_terminal_attempt_cannot_be_rewritten(db_session) -> None:
    repository, run, _ = _run(db_session)
    query = _claim(repository, run.id)
    attempt = _settle_success(repository, query)
    with pytest.raises(DiscoveryStateError, match="already_terminal"):
        repository.settle_attempt(
            attempt.id,
            DiscoveryAttemptOutcome(status=DiscoveryAttemptStatus.PROVIDER_FAILED),
        )


def test_retry_and_completion_transitions_are_allowlisted(db_session) -> None:
    repository, run, _ = _run(
        db_session,
        max_provider_calls=3,
        max_tool_calls=3,
    )
    first = _claim(repository, run.id)
    attempt = repository.reserve_attempt(
        query_id=first.id,
        worker_id="worker-1",
        request_fingerprint="f" * 64,
        reserved_tool_calls=1,
        reserved_estimated_cost=Decimal("0.10"),
    )
    repository.settle_attempt(
        attempt.id,
        DiscoveryAttemptOutcome(
            status=DiscoveryAttemptStatus.RATE_LIMITED,
            http_status=429,
            error_code="provider_rate_limited",
        ),
    )
    retry_at = datetime.now(UTC) + timedelta(seconds=30)
    repository.schedule_retry(first.id, next_attempt_at=retry_at, max_attempts=3)
    reclaimed = _claim(repository, run.id, now=retry_at)
    assert reclaimed.id == first.id
    _settle_success(repository, reclaimed)
    repository.complete_query(reclaimed.id)
    assert run.status is DiscoveryRunStatus.RUNNING

    second = _claim(repository, run.id)
    _settle_success(repository, second)
    repository.complete_query(second.id)
    assert run.status is DiscoveryRunStatus.COMPLETED
    assert run.completed_at is not None
    with pytest.raises(DiscoveryStateError, match="cannot_complete"):
        repository.complete_query(second.id)


def test_provider_overrun_is_preserved_and_fails_the_run_closed(db_session) -> None:
    repository, run, _ = _run(db_session)
    query = _claim(repository, run.id)
    attempt = repository.reserve_attempt(
        query_id=query.id,
        worker_id="worker-1",
        request_fingerprint="1" * 64,
        reserved_tool_calls=1,
        reserved_estimated_cost=Decimal("0.10"),
    )
    settled = repository.settle_attempt(
        attempt.id,
        DiscoveryAttemptOutcome(
            status=DiscoveryAttemptStatus.SUCCEEDED,
            web_search_executed=True,
            tool_call_count=2,
            estimated_tool_cost=Decimal("0.20"),
        ),
    )
    assert settled.status is DiscoveryAttemptStatus.RESPONSE_INVALID
    assert settled.error_code == "provider_reservation_exceeded"
    assert run.status is DiscoveryRunStatus.FAILED
    assert run.estimated_cost_settled == Decimal("0.20")


def test_expired_in_progress_attempt_is_abandoned_conservatively(db_session) -> None:
    repository, run, _ = _run(db_session)
    started_at = datetime.now(UTC)
    query = _claim(repository, run.id, now=started_at)
    attempt = repository.reserve_attempt(
        query_id=query.id,
        worker_id="worker-1",
        request_fingerprint="c" * 64,
        reserved_tool_calls=1,
        reserved_estimated_cost=Decimal("0.10"),
        now=started_at,
    )
    abandoned = repository.abandon_expired_attempt(
        query.id,
        now=started_at + timedelta(seconds=61),
    )
    assert abandoned.id == attempt.id
    assert abandoned.status is DiscoveryAttemptStatus.ABANDONED
    assert query.status is DiscoveryQueryStatus.PLANNED
    assert run.provider_calls_completed == 1
    assert run.tool_calls_completed == 1
    assert run.estimated_cost_settled == Decimal("0.10")


def test_leads_observations_and_assessments_are_idempotent_and_immutable(db_session) -> None:
    repository, run, _ = _run(db_session)
    first_query = _claim(repository, run.id)
    _settle_success(repository, first_query)
    lead, observation = repository.record_lead_observation(
        query_id=first_query.id,
        url=("HTTPS://SCHOLARSHIPS.GOV.UK:443/example/?utm_source=provider&b=2&a=1#fragment"),
        discovery_reason="exact identity query",
        provider_rank=1,
    )
    repeated_lead, repeated_observation = repository.record_lead_observation(
        query_id=first_query.id,
        url="https://scholarships.gov.uk/example?a=1&b=2",
        discovery_reason="exact identity query",
        provider_rank=1,
    )
    assert repeated_lead.id == lead.id
    assert repeated_observation.id == observation.id
    assert lead.normalized_url == "https://scholarships.gov.uk/example?a=1&b=2"
    assert lead.host == "scholarships.gov.uk"
    assert run.raw_leads_seen == 1
    assert run.unique_leads == 1

    second_repository, second_run, _ = _run(db_session)
    second_query = _claim(second_repository, second_run.id)
    _settle_success(second_repository, second_query)
    global_lead, _ = second_repository.record_lead_observation(
        query_id=second_query.id,
        url="https://scholarships.gov.uk/example?b=2&a=1&utm_campaign=repeat",
        discovery_reason="provider refinement",
    )
    assert global_lead.id == lead.id
    assert second_run.unique_leads == 1

    assessment_input = DiscoveryAssessmentInput(
        assessment_context_hash="d" * 64,
        context_type="candidate_root",
        officiality_status=DiscoveryOfficialityStatus.OFFICIAL,
        owner_type="government",
        reason_code="REVIEWED_GOVERNMENT_DOMAIN",
        reason_detail="Host matches the reviewed government owner.",
        classifier_version="official-source.v1",
        canonical_domain="scholarships.gov.uk",
        trust_tier=1,
    )
    assessment = repository.append_assessment(
        run_id=run.id,
        lead_id=lead.id,
        assessment=assessment_input,
    )
    assert (
        repository.append_assessment(
            run_id=run.id,
            lead_id=lead.id,
            assessment=assessment_input,
        ).id
        == assessment.id
    )
    assert (
        second_repository.append_assessment(
            run_id=second_run.id,
            lead_id=lead.id,
            assessment=assessment_input,
        ).id
        == assessment.id
    )
    unobserved_repository, unobserved_run, _ = _run(db_session)
    with pytest.raises(DiscoveryStateError, match="not_observed_in_run"):
        unobserved_repository.append_assessment(
            run_id=unobserved_run.id,
            lead_id=lead.id,
            assessment=assessment_input,
        )
    assessment.reason_detail = "rewritten"
    with pytest.raises(ValueError, match="immutable provenance"):
        db_session.commit()
    db_session.rollback()

    persisted_observation = db_session.get(CatalogueDiscoveryObservation, observation.id)
    assert persisted_observation is not None
    db_session.delete(persisted_observation)
    with pytest.raises(ValueError, match="immutable provenance"):
        db_session.commit()
    db_session.rollback()


def test_provider_url_ingestion_rejects_unsafe_urls_without_persisting_them(db_session) -> None:
    repository, run, _ = _run(db_session)
    query = _claim(repository, run.id)
    provider_result = DiscoveryProviderResult(
        provider_response_id="response-url-policy",
        web_search_executed=True,
        urls=(
            "https://b\u00fccher.example/Scholarship?b=2&a=1&utm_source=search#overview",
            "https://xn--bcher-kva.example/Scholarship?a=1&b=2",
            "http://example.edu/scholarship",
            "https://example.edu/login",
            "https://127.0.0.1/private",
        ),
        tool_call_count=1,
        response_bytes=800,
        latency_ms=20,
        estimated_tool_cost=Decimal("0.02"),
    )
    provider = FakeDiscoveryProvider({query.query_hash: provider_result})
    returned = CatalogueDiscoveryExecutionService(db_session, provider).execute_claimed_query(
        query_id=query.id,
        worker_id="worker-1",
        max_urls=5,
        max_tool_calls=1,
        max_estimated_cost=Decimal("0.10"),
    )

    ingestion_service = CatalogueDiscoveryLeadIngestionService(db_session)
    with pytest.raises(DiscoveryStateError, match="does_not_match_settled_attempt"):
        ingestion_service.ingest_provider_result(
            query_id=query.id,
            result=returned.model_copy(update={"urls": returned.urls[:1]}),
        )

    summary = ingestion_service.ingest_provider_result(
        query_id=query.id,
        result=returned,
    )

    assert summary.urls_seen == 5
    assert summary.accepted_urls == 2
    assert summary.rejected_urls == 3
    assert len(summary.unique_lead_ids) == 1
    assert dict(summary.rejection_counts) == {
        URLRejectionCode.AUTHENTICATION_TARGET: 1,
        URLRejectionCode.PRIVATE_LITERAL: 1,
        URLRejectionCode.UNSUPPORTED_SCHEME: 1,
    }
    leads = list(db_session.scalars(select(CatalogueDiscoveryLead)))
    assert len(leads) == 1
    assert leads[0].normalized_url == "https://xn--bcher-kva.example/Scholarship?a=1&b=2"
    assert leads[0].host == "xn--bcher-kva.example"
    assert run.raw_leads_seen == 1
    assert run.unique_leads == 1

    with pytest.raises(DiscoveryURLRejected) as rejected:
        repository.record_lead_observation(
            query_id=query.id,
            url="https://[::1]/bypass",
            discovery_reason="direct repository bypass",
        )
    assert rejected.value.code is URLRejectionCode.PRIVATE_LITERAL
    assert len(list(db_session.scalars(select(CatalogueDiscoveryLead)))) == 1

    with pytest.raises(ValueError, match="provider rank must be positive"):
        repository.record_lead_observation(
            query_id=query.id,
            url="https://example.edu/scholarship",
            discovery_reason="invalid provider metadata",
            provider_rank=0,
        )
    with pytest.raises(ValueError, match="provider source type must be non-empty"):
        repository.record_lead_observation(
            query_id=query.id,
            url="https://example.edu/scholarship",
            discovery_reason="invalid provider metadata",
            provider_source_type="",
        )
    assert len(list(db_session.scalars(select(CatalogueDiscoveryLead)))) == 1

    second_query = _claim(repository, run.id)
    _settle_success(repository, second_query)
    repeated_lead, _ = repository.record_lead_observation(
        query_id=second_query.id,
        url="https://xn--bcher-kva.example/Scholarship?b=2&a=1#repeat",
        discovery_reason="second query same run",
    )
    assert repeated_lead.id == leads[0].id
    assert run.raw_leads_seen == 2
    assert run.unique_leads == 1


def test_promotion_requires_matching_fetched_source_and_is_idempotent(db_session) -> None:
    candidate = _candidate(db_session)
    repository, run, _ = _run(db_session, candidate.id)
    query = _claim(repository, run.id)
    _settle_success(repository, query)
    lead, _ = repository.record_lead_observation(
        query_id=query.id,
        url="https://scholarships.gov.uk/example",
        discovery_reason="official root",
    )
    assessment = repository.append_assessment(
        run_id=run.id,
        lead_id=lead.id,
        assessment=DiscoveryAssessmentInput(
            assessment_context_hash="e" * 64,
            context_type="candidate_root",
            officiality_status=DiscoveryOfficialityStatus.OFFICIAL,
            owner_type="government",
            reason_code="OFFICIAL_OWNER_MATCH",
            reason_detail="Owner and target context match.",
            classifier_version="official-source.v1",
            trust_tier=1,
        ),
    )
    source = CatalogueCandidateSource(
        candidate_id=candidate.id,
        discovery_lead_id=lead.id,
        url=lead.normalized_url,
        canonical_url=lead.normalized_url,
        status=CandidateSourceStatus.DISCOVERED,
        is_official=True,
        trust_tier=1,
        classification_reason="official owner match",
    )
    db_session.add(source)
    db_session.commit()
    with pytest.raises(DiscoveryStateError, match="requires_fetched"):
        repository.record_promotion(
            run_id=run.id,
            lead_id=lead.id,
            assessment_id=assessment.id,
            candidate_id=candidate.id,
            candidate_source_id=source.id,
        )
    source.status = CandidateSourceStatus.FETCHED
    source.is_official = False
    db_session.commit()
    with pytest.raises(DiscoveryStateError, match="requires_fetched"):
        repository.record_promotion(
            run_id=run.id,
            lead_id=lead.id,
            assessment_id=assessment.id,
            candidate_id=candidate.id,
            candidate_source_id=source.id,
        )
    source.is_official = True
    db_session.commit()
    promotion = repository.record_promotion(
        run_id=run.id,
        lead_id=lead.id,
        assessment_id=assessment.id,
        candidate_id=candidate.id,
        candidate_source_id=source.id,
    )
    repeated = repository.record_promotion(
        run_id=run.id,
        lead_id=lead.id,
        assessment_id=assessment.id,
        candidate_id=candidate.id,
        candidate_source_id=source.id,
    )
    assert repeated.id == promotion.id
    assert run.promotions == 1

    other_candidate = _candidate(db_session)
    other_repository, other_run, _ = _run(db_session, other_candidate.id)
    with pytest.raises(DiscoveryStateError, match="not_run_target"):
        other_repository.record_promotion(
            run_id=other_run.id,
            lead_id=lead.id,
            assessment_id=assessment.id,
            candidate_id=candidate.id,
            candidate_source_id=source.id,
        )
