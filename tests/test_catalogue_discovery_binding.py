import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.modules.catalogue_ingestion.discovery import (
    DiscoveryObjective,
    DiscoveryObjectiveKind,
    DiscoveryPrioritySnapshot,
    DiscoveryQueryPlanner,
)
from app.modules.catalogue_ingestion.discovery_binding import (
    CatalogueDiscoveryBindingService,
)
from app.modules.catalogue_ingestion.discovery_models import (
    CatalogueDiscoveryAssessment,
    CatalogueDiscoveryQuery,
    DiscoveryAttemptStatus,
    DiscoveryOfficialityStatus,
)
from app.modules.catalogue_ingestion.discovery_officiality import (
    CONTEXTUAL_OFFICIALITY_CLASSIFIER_VERSION,
    CatalogueDiscoveryOfficialityService,
    ReviewedOwnerDomain,
    SourceAuthorityClass,
)
from app.modules.catalogue_ingestion.discovery_repository import (
    CatalogueDiscoveryRepository,
    DiscoveryAssessmentInput,
    DiscoveryAttemptOutcome,
    DiscoveryRunLimits,
    DiscoveryStateError,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueIngestionRun,
    IngestionMode,
)
from app.modules.opportunities.evidence_models import SourceOwnerType
from app.modules.opportunities.graph_models import Institution
from app.modules.opportunities.models import DegreeLevel, Opportunity, Provider


def _candidate(
    db_session,
    *,
    provider_name: str | None,
    university_name: str | None = None,
    status: CandidateStatus = CandidateStatus.DISCOVERED,
    failure_code: str | None = None,
) -> CatalogueCandidate:
    ingestion_run = CatalogueIngestionRun(
        source_label=f"binding-{uuid.uuid4().hex}.json",
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
        seed_name="Chinese Government Scholarship",
        seed_provider=provider_name,
        seed_university=university_name,
        seed_country="China",
        status=status,
        failure_code=failure_code,
    )
    db_session.add(candidate)
    db_session.commit()
    return candidate


def _provider(db_session) -> Provider:
    provider = Provider(
        name=f"China Scholarship Council {uuid.uuid4().hex}",
        website_url="https://csc.edu.cn",
    )
    db_session.add(provider)
    db_session.commit()
    return provider


def _institution(db_session) -> Institution:
    institution = Institution(
        canonical_name=f"Tsinghua University {uuid.uuid4().hex}",
        slug=f"tsinghua-{uuid.uuid4().hex}",
        institution_type="university",
        country_code="CN",
        official_domain="tsinghua.edu.cn",
        official_website="https://tsinghua.edu.cn",
        identity_status="verified",
    )
    db_session.add(institution)
    db_session.commit()
    return institution


def _objective(
    *,
    candidate_id: uuid.UUID | None,
    provider_name: str | None,
    domains: tuple[str, ...],
    objective_kind: DiscoveryObjectiveKind = DiscoveryObjectiveKind.RESOLVE_CANONICAL_SOURCE,
    institution: Institution | None = None,
) -> DiscoveryObjective:
    return DiscoveryObjective(
        objective_kind=objective_kind,
        candidate_id=candidate_id,
        institution_id=institution.id if institution else None,
        field_paths=("identity.official_source",),
        reason_codes=("OFFICIAL_SOURCE_MISSING",),
        criticality_tier=0,
        scholarship_name="Chinese Government Scholarship",
        provider_name=provider_name,
        institution_name=institution.canonical_name if institution else None,
        country="China",
        reviewed_domains=domains,
    )


def _discovery_run(db_session, objective: DiscoveryObjective, *, dry_run: bool = False):
    repository = CatalogueDiscoveryRepository(db_session)
    run = repository.create_run(
        objective=objective,
        priority=DiscoveryPrioritySnapshot(
            blocking_class=0,
            criticality_tier=0,
            conflict_or_stale_rank=1,
            current_cycle_rank=1,
            deterministic_tiebreak=uuid.uuid4().hex,
            reason_codes=objective.reason_codes,
        ),
        plans=DiscoveryQueryPlanner(max_queries=2).plan(objective),
        provider="fake",
        model="fake-web-search-v1",
        limits=DiscoveryRunLimits(
            max_queries=2,
            max_provider_calls=2,
            max_tool_calls=2,
            max_leads=10,
            max_response_bytes=50_000,
            max_estimated_cost=Decimal("1.00"),
        ),
        dry_run=dry_run,
    )
    queries = list(
        db_session.scalars(
            select(CatalogueDiscoveryQuery)
            .where(CatalogueDiscoveryQuery.run_id == run.id)
            .order_by(CatalogueDiscoveryQuery.ordinal)
        )
    )
    return repository, run, queries


def _claim_and_settle(repository: CatalogueDiscoveryRepository, run_id: uuid.UUID):
    query = repository.claim_queries(
        run_id=run_id,
        worker_id="binding-worker",
        limit=1,
        lease_seconds=60,
        max_attempts=2,
    )[0]
    attempt = repository.reserve_attempt(
        query_id=query.id,
        worker_id="binding-worker",
        request_fingerprint=f"{query.ordinal + 1:x}" * 64,
        reserved_tool_calls=1,
        reserved_estimated_cost=Decimal("0.10"),
    )
    repository.settle_attempt(
        attempt.id,
        DiscoveryAttemptOutcome(
            status=DiscoveryAttemptStatus.SUCCEEDED,
            provider_response_id=f"binding-response-{query.ordinal}",
            web_search_executed=True,
            tool_call_count=1,
            result_url_count=1,
            response_bytes=200,
            estimated_tool_cost=Decimal("0.01"),
        ),
    )
    return query


def _observe(
    repository: CatalogueDiscoveryRepository,
    query: CatalogueDiscoveryQuery,
    url: str,
    *,
    provider_rank: int | None = None,
):
    return repository.record_lead_observation(
        query_id=query.id,
        url=url,
        discovery_reason="binding proof lead",
        provider_rank=provider_rank,
        minimal_title="Untrusted search title",
    )[0]


def _provider_registration(provider: Provider, domain: str) -> ReviewedOwnerDomain:
    return ReviewedOwnerDomain(
        domain=domain,
        owner_type=SourceOwnerType.PROVIDER,
        owner_name_snapshot=provider.name,
        authority_class=SourceAuthorityClass.CANONICAL_OWNER,
        review_reason="Verified provider domain for binding tests.",
        provider_id=provider.id,
    )


def _assess(db_session, run_id, lead_id, registrations):
    return CatalogueDiscoveryOfficialityService(db_session).assess_lead(
        run_id=run_id,
        lead_id=lead_id,
        reviewed_owner_domains=registrations,
    )


def _provider_binding_context(db_session, *, status=CandidateStatus.DISCOVERED, failure_code=None):
    provider = _provider(db_session)
    candidate = _candidate(
        db_session,
        provider_name=provider.name,
        status=status,
        failure_code=failure_code,
    )
    objective = _objective(
        candidate_id=candidate.id,
        provider_name=provider.name,
        domains=("csc.edu.cn",),
    )
    repository, run, _ = _discovery_run(db_session, objective)
    query = _claim_and_settle(repository, run.id)
    lead = _observe(repository, query, "https://csc.edu.cn/scholarships")
    assessment = _assess(
        db_session,
        run.id,
        lead.id,
        (_provider_registration(provider, "csc.edu.cn"),),
    )
    assert assessment.officiality_status is DiscoveryOfficialityStatus.OFFICIAL
    return candidate, run, lead, assessment


def test_binding_creates_one_discovered_source_without_fetch_or_candidate_creation(
    db_session,
) -> None:
    candidate, run, lead, assessment = _provider_binding_context(db_session)
    candidate_count = db_session.scalar(select(func.count()).select_from(CatalogueCandidate))

    first = CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)
    repeated = CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert first.source.id == repeated.source.id
    assert first.lead_id == lead.id
    assert first.assessment_id == assessment.id
    assert first.created
    assert not repeated.created
    assert first.source.candidate_id == candidate.id
    assert first.source.discovery_lead_id == lead.id
    assert first.source.status is CandidateSourceStatus.DISCOVERED
    assert first.source.is_official
    assert first.source.final_url is None
    assert first.source.content_hash is None
    assert candidate.status is CandidateStatus.DISCOVERED
    persisted_candidate_count = db_session.scalar(
        select(func.count()).select_from(CatalogueCandidate)
    )
    assert persisted_candidate_count == candidate_count
    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 1


def test_binding_reuses_identical_assessment_created_by_an_earlier_run(db_session) -> None:
    provider = _provider(db_session)
    candidate = _candidate(db_session, provider_name=provider.name)
    objective = _objective(
        candidate_id=candidate.id,
        provider_name=provider.name,
        domains=("csc.edu.cn",),
    )
    registrations = (_provider_registration(provider, "csc.edu.cn"),)

    first_repository, first_run, _ = _discovery_run(db_session, objective)
    first_query = _claim_and_settle(first_repository, first_run.id)
    first_lead = _observe(first_repository, first_query, "https://csc.edu.cn/reusable")
    first_assessment = _assess(db_session, first_run.id, first_lead.id, registrations)

    second_repository, second_run, _ = _discovery_run(db_session, objective)
    second_query = _claim_and_settle(second_repository, second_run.id)
    second_lead = _observe(second_repository, second_query, "https://csc.edu.cn/reusable")
    reused_assessment = _assess(db_session, second_run.id, second_lead.id, registrations)

    assert reused_assessment.id == first_assessment.id
    assert reused_assessment.run_id == first_run.id

    result = CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=second_run.id)

    assert result.assessment_id == first_assessment.id
    assert result.source.candidate_id == candidate.id
    assert result.source.discovery_lead_id == first_lead.id


def test_repeated_binding_after_terminal_transition_does_not_reset_candidate(db_session) -> None:
    candidate, run, _, _ = _provider_binding_context(db_session)
    first = CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)
    candidate.status = CandidateStatus.PUBLISHED
    db_session.commit()

    repeated = CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert repeated.source.id == first.source.id
    assert not repeated.created
    assert not repeated.candidate_resumed
    assert candidate.status is CandidateStatus.PUBLISHED


def test_label_only_objective_cannot_create_or_bind_candidate(db_session) -> None:
    provider = _provider(db_session)
    objective = _objective(
        candidate_id=None,
        provider_name=provider.name,
        domains=("csc.edu.cn",),
    )
    repository, run, _ = _discovery_run(db_session, objective)
    query = _claim_and_settle(repository, run.id)
    lead = _observe(repository, query, "https://csc.edu.cn/scholarships")
    _assess(
        db_session,
        run.id,
        lead.id,
        (_provider_registration(provider, "csc.edu.cn"),),
    )

    with pytest.raises(DiscoveryStateError, match="explicit_target_candidate"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidate)) == 0
    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 0


def test_dry_run_can_select_but_cannot_mutate_candidate_source(db_session) -> None:
    provider = _provider(db_session)
    candidate = _candidate(db_session, provider_name=provider.name)
    objective = _objective(
        candidate_id=candidate.id,
        provider_name=provider.name,
        domains=("csc.edu.cn",),
    )
    repository, run, _ = _discovery_run(db_session, objective, dry_run=True)
    query = _claim_and_settle(repository, run.id)
    lead = _observe(repository, query, "https://csc.edu.cn/dry-run")
    _assess(
        db_session,
        run.id,
        lead.id,
        (_provider_registration(provider, "csc.edu.cn"),),
    )
    service = CatalogueDiscoveryBindingService(db_session)

    assert service.select_root(run_id=run.id).lead_id == lead.id
    with pytest.raises(DiscoveryStateError, match="disabled_for_dry_run"):
        service.bind_best_root(run_id=run.id)

    assert candidate.status is CandidateStatus.DISCOVERED
    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 0


@pytest.mark.parametrize(
    "status",
    (
        CandidateStatus.OFFICIAL_SOURCE_CANDIDATE,
        CandidateStatus.SOURCE_FETCHED,
        CandidateStatus.EXTRACTED,
        CandidateStatus.VALIDATION_FAILED,
        CandidateStatus.CONFLICT_DETECTED,
        CandidateStatus.DUPLICATE_CANDIDATE,
        CandidateStatus.READY_FOR_REVIEW,
        CandidateStatus.SUBMITTED_FOR_REVIEW,
        CandidateStatus.APPROVED,
        CandidateStatus.REJECTED,
        CandidateStatus.PUBLISHED,
        CandidateStatus.SOURCE_CHANGED,
    ),
)
def test_incompatible_candidate_lifecycle_is_never_reset(db_session, status) -> None:
    candidate, run, _, _ = _provider_binding_context(db_session, status=status)

    with pytest.raises(DiscoveryStateError, match="lifecycle_incompatible"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert candidate.status is status
    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 0


def test_only_source_not_found_needs_review_candidate_is_resumed(db_session) -> None:
    candidate, run, lead, _ = _provider_binding_context(
        db_session,
        status=CandidateStatus.NEEDS_REVIEW,
        failure_code="official_source_not_found",
    )
    candidate.failure_reason = "No reviewed official URL was available."
    db_session.commit()

    result = CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert result.candidate_resumed
    assert result.source.discovery_lead_id == lead.id
    assert candidate.status is CandidateStatus.DISCOVERED
    assert candidate.failure_code is None
    assert candidate.failure_reason is None
    assert candidate.next_attempt_at is not None


def test_needs_review_with_other_failure_or_review_payload_is_not_resumed(db_session) -> None:
    wrong_failure, wrong_run, _, _ = _provider_binding_context(
        db_session,
        status=CandidateStatus.NEEDS_REVIEW,
        failure_code="robots_blocked",
    )
    with pytest.raises(DiscoveryStateError, match="lifecycle_incompatible"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=wrong_run.id)
    assert wrong_failure.status is CandidateStatus.NEEDS_REVIEW

    dirty, dirty_run, _, _ = _provider_binding_context(
        db_session,
        status=CandidateStatus.NEEDS_REVIEW,
        failure_code="official_source_not_found",
    )
    dirty.proposed_payload = {"reviewed": True}
    db_session.commit()
    with pytest.raises(DiscoveryStateError, match="review_or_resolution_state"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=dirty_run.id)
    assert dirty.status is CandidateStatus.NEEDS_REVIEW


def test_rejected_source_conflict_leaves_resumable_candidate_untouched(db_session) -> None:
    candidate, run, lead, _ = _provider_binding_context(
        db_session,
        status=CandidateStatus.NEEDS_REVIEW,
        failure_code="official_source_not_found",
    )
    blocked_source = CatalogueCandidateSource(
        candidate_id=candidate.id,
        url=lead.normalized_url,
        canonical_url=lead.normalized_url,
        status=CandidateSourceStatus.FETCHED,
        is_official=True,
        trust_tier=1,
        classification_reason="Existing fetched source.",
    )
    db_session.add(blocked_source)
    db_session.commit()

    with pytest.raises(DiscoveryStateError, match="canonical_url_already_owned"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)
    db_session.commit()

    assert candidate.status is CandidateStatus.NEEDS_REVIEW
    assert candidate.failure_code == "official_source_not_found"
    assert blocked_source.discovery_lead_id is None


def test_actively_claimed_candidate_cannot_be_bound(db_session) -> None:
    candidate, run, _, _ = _provider_binding_context(db_session)
    candidate.claimed_by = "ingestion-worker"
    candidate.claimed_until = datetime.now(UTC) + timedelta(minutes=5)
    db_session.commit()

    with pytest.raises(DiscoveryStateError, match="actively_claimed"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert candidate.claimed_by == "ingestion-worker"
    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 0


def test_candidate_with_existing_opportunity_cannot_receive_root_binding(db_session) -> None:
    candidate, run, _, _ = _provider_binding_context(db_session)
    provider = db_session.scalar(select(Provider).where(Provider.name == candidate.seed_provider))
    assert provider is not None
    opportunity = Opportunity(
        provider_id=provider.id,
        name="Existing Chinese Government Scholarship",
        country="China",
        degree_level=DegreeLevel.MASTERS,
    )
    db_session.add(opportunity)
    db_session.flush()
    candidate.opportunity_id = opportunity.id
    db_session.commit()

    with pytest.raises(DiscoveryStateError, match="already_has_opportunity"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert candidate.opportunity_id == opportunity.id
    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 0


def test_existing_unbound_discovered_source_is_reused(db_session) -> None:
    candidate, run, lead, _ = _provider_binding_context(db_session)
    existing = CatalogueCandidateSource(
        candidate_id=candidate.id,
        url=lead.normalized_url,
        canonical_url=lead.normalized_url,
        status=CandidateSourceStatus.DISCOVERED,
        is_official=False,
        classification_reason="Seed URL awaiting assessment.",
    )
    db_session.add(existing)
    db_session.commit()

    result = CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert result.source.id == existing.id
    assert not result.created
    assert existing.discovery_lead_id == lead.id
    assert existing.is_official
    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 1


def test_supporting_institution_page_cannot_bind_umbrella_root(db_session) -> None:
    provider = _provider(db_session)
    institution = _institution(db_session)
    candidate = _candidate(db_session, provider_name=provider.name)
    objective = _objective(
        candidate_id=candidate.id,
        provider_name=provider.name,
        domains=("csc.edu.cn", "tsinghua.edu.cn"),
        objective_kind=DiscoveryObjectiveKind.INSTITUTION_LOCAL_REQUIREMENTS,
        institution=institution,
    )
    repository, run, _ = _discovery_run(db_session, objective)
    query = _claim_and_settle(repository, run.id)
    lead = _observe(repository, query, "https://tsinghua.edu.cn/csc/requirements")
    assessment = _assess(
        db_session,
        run.id,
        lead.id,
        (
            _provider_registration(provider, "csc.edu.cn"),
            ReviewedOwnerDomain(
                domain="tsinghua.edu.cn",
                owner_type=SourceOwnerType.INSTITUTION,
                owner_name_snapshot=institution.canonical_name,
                authority_class=SourceAuthorityClass.SUPPORTING_INSTITUTION,
                review_reason="Verified institution support source.",
                institution_id=institution.id,
            ),
        ),
    )
    assert assessment.officiality_status is DiscoveryOfficialityStatus.SUPPORTING_OFFICIAL

    with pytest.raises(DiscoveryStateError, match="no_acceptable_official_root"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 0


def test_institution_owned_award_can_bind_reviewed_canonical_institution(db_session) -> None:
    institution = _institution(db_session)
    candidate = _candidate(
        db_session,
        provider_name=None,
        university_name=institution.canonical_name,
    )
    objective = _objective(
        candidate_id=candidate.id,
        provider_name=None,
        domains=("tsinghua.edu.cn",),
        institution=institution,
    )
    repository, run, _ = _discovery_run(db_session, objective)
    query = _claim_and_settle(repository, run.id)
    lead = _observe(repository, query, "https://tsinghua.edu.cn/independent-award")
    assessment = _assess(
        db_session,
        run.id,
        lead.id,
        (
            ReviewedOwnerDomain(
                domain="tsinghua.edu.cn",
                owner_type=SourceOwnerType.INSTITUTION,
                owner_name_snapshot=institution.canonical_name,
                authority_class=SourceAuthorityClass.CANONICAL_OWNER,
                review_reason="Verified institution-owned award root.",
                institution_id=institution.id,
            ),
        ),
    )
    assert assessment.officiality_status is DiscoveryOfficialityStatus.OFFICIAL

    result = CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert result.source.discovery_lead_id == lead.id
    assert result.source.is_official


def test_current_classifier_row_with_cross_owner_identity_is_not_bindable(db_session) -> None:
    provider = _provider(db_session)
    other_provider = _provider(db_session)
    candidate = _candidate(db_session, provider_name=provider.name)
    objective = _objective(
        candidate_id=candidate.id,
        provider_name=provider.name,
        domains=("csc.edu.cn",),
    )
    repository, run, _ = _discovery_run(db_session, objective)
    query = _claim_and_settle(repository, run.id)
    lead = _observe(repository, query, "https://csc.edu.cn/cross-owner")
    repository.append_assessment(
        run_id=run.id,
        lead_id=lead.id,
        assessment=DiscoveryAssessmentInput(
            assessment_context_hash="a" * 64,
            context_type=f"discovery:{objective.objective_kind.value}",
            context_provider_id=provider.id,
            officiality_status=DiscoveryOfficialityStatus.OFFICIAL,
            owner_type=SourceOwnerType.PROVIDER.value,
            owner_id=other_provider.id,
            canonical_domain="csc.edu.cn",
            trust_tier=1,
            reason_code="REVIEWED_PROVIDER_AUTHORITY",
            reason_detail="Forged cross-owner assertion for a binding regression test.",
            classifier_version=CONTEXTUAL_OFFICIALITY_CLASSIFIER_VERSION,
        ),
    )

    with pytest.raises(DiscoveryStateError, match="no_acceptable_official_root"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 0


def test_unsupported_classifier_official_row_is_not_bindable(db_session) -> None:
    provider = _provider(db_session)
    candidate = _candidate(db_session, provider_name=provider.name)
    objective = _objective(
        candidate_id=candidate.id,
        provider_name=provider.name,
        domains=("csc.edu.cn",),
    )
    repository, run, _ = _discovery_run(db_session, objective)
    query = _claim_and_settle(repository, run.id)
    lead = _observe(repository, query, "https://csc.edu.cn/legacy")
    repository.append_assessment(
        run_id=run.id,
        lead_id=lead.id,
        assessment=DiscoveryAssessmentInput(
            assessment_context_hash="f" * 64,
            context_type=f"discovery:{objective.objective_kind.value}",
            context_provider_id=provider.id,
            officiality_status=DiscoveryOfficialityStatus.OFFICIAL,
            owner_type=SourceOwnerType.PROVIDER.value,
            owner_id=provider.id,
            canonical_domain="csc.edu.cn",
            trust_tier=1,
            reason_code="REVIEWED_PROVIDER_AUTHORITY",
            reason_detail="Legacy classifier assertion.",
            classifier_version="legacy-officiality.v0",
        ),
    )

    with pytest.raises(DiscoveryStateError, match="no_acceptable_official_root"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)

    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 0


def test_superseded_official_assessment_is_not_bindable(db_session) -> None:
    provider = _provider(db_session)
    candidate = _candidate(db_session, provider_name=provider.name)
    objective = _objective(
        candidate_id=candidate.id,
        provider_name=provider.name,
        domains=("csc.edu.cn",),
    )
    repository, run, _ = _discovery_run(db_session, objective)
    query = _claim_and_settle(repository, run.id)
    lead = _observe(repository, query, "https://csc.edu.cn/superseded")
    official = _assess(
        db_session,
        run.id,
        lead.id,
        (_provider_registration(provider, "csc.edu.cn"),),
    )
    superseding = repository.append_assessment(
        run_id=run.id,
        lead_id=lead.id,
        assessment=DiscoveryAssessmentInput(
            assessment_context_hash="e" * 64,
            context_type=f"discovery:{objective.objective_kind.value}",
            context_provider_id=provider.id,
            officiality_status=DiscoveryOfficialityStatus.UNRESOLVED,
            owner_type=SourceOwnerType.PROVIDER.value,
            owner_id=provider.id,
            canonical_domain="csc.edu.cn",
            reason_code="OWNER_REVIEW_REVOKED",
            reason_detail="A later review revoked the prior owner assessment.",
            classifier_version=official.classifier_version,
            supersedes_assessment_id=official.id,
        ),
    )

    with pytest.raises(DiscoveryStateError, match="no_acceptable_official_root"):
        CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)
    with pytest.raises(DiscoveryStateError, match="assessment_was_superseded"):
        repository.bind_candidate_source(
            run_id=run.id,
            lead_id=lead.id,
            assessment_id=official.id,
        )

    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidateSource)) == 0
    db_session.execute(
        delete(CatalogueDiscoveryAssessment).where(
            CatalogueDiscoveryAssessment.id == superseding.id
        )
    )
    db_session.execute(
        delete(CatalogueDiscoveryAssessment).where(CatalogueDiscoveryAssessment.id == official.id)
    )
    db_session.commit()


def test_root_selection_prefers_query_intent_then_provider_rank_then_url(db_session) -> None:
    provider = _provider(db_session)
    candidate = _candidate(db_session, provider_name=provider.name)
    domains = ("alpha.csc.edu.cn", "beta.csc.edu.cn", "zeta.csc.edu.cn")
    objective = _objective(
        candidate_id=candidate.id,
        provider_name=provider.name,
        domains=domains,
    )
    repository, run, _ = _discovery_run(db_session, objective)
    registrations = tuple(_provider_registration(provider, domain) for domain in domains)

    exact_query = _claim_and_settle(repository, run.id)
    zeta = _observe(
        repository,
        exact_query,
        "https://zeta.csc.edu.cn/root",
        provider_rank=2,
    )
    alpha = _observe(
        repository,
        exact_query,
        "https://alpha.csc.edu.cn/root",
        provider_rank=2,
    )
    _assess(db_session, run.id, zeta.id, registrations)
    _assess(db_session, run.id, alpha.id, registrations)

    refinement_query = _claim_and_settle(repository, run.id)
    beta = _observe(
        repository,
        refinement_query,
        "https://beta.csc.edu.cn/root",
        provider_rank=1,
    )
    _assess(db_session, run.id, beta.id, registrations)

    selection = CatalogueDiscoveryBindingService(db_session).select_root(run_id=run.id)

    assert selection.lead_id == alpha.id
    assert selection.normalized_url == "https://alpha.csc.edu.cn/root"
