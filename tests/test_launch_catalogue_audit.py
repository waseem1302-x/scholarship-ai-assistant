import json
import uuid
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.modules.auth.models import User, UserRole
from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ScopedCoverageState
from app.modules.catalogue_ingestion.models import (
    CandidateStatus,
    CatalogueCandidate,
    CatalogueIngestionRun,
    IngestionMode,
    IngestionRunStatus,
)
from app.modules.catalogue_ingestion.review_models import (
    CatalogueCandidateReview,
    CatalogueProposalState,
)
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueCoverageCell,
    CatalogueScopeNode,
    ScopeNodeType,
)
from app.modules.opportunities.evidence_models import OfficialityStatus, SourceOwnerType
from app.modules.opportunities.models import (
    DegreeLevel,
    IndependenceStatus,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    Provider,
    Source,
    SourceType,
    VerificationStatus,
)
from app.modules.opportunities.schemas import (
    DecisionSummaryBlockResponse,
    DecisionSummaryState,
    PublicScholarshipProjectionResponse,
    ScholarshipDecisionSummaryResponse,
)

CRITICAL_OBJECTIVES = (
    ClaimObjective.IDENTITY,
    ClaimObjective.ROUTES,
    ClaimObjective.ELIGIBILITY,
    ClaimObjective.FUNDING,
    ClaimObjective.APPLICATION_TIMELINE,
)


def create_launch_fixture(
    db_session: Session,
    *,
    stale: bool = False,
    coverage_state: ScopedCoverageState = ScopedCoverageState.COMPLETE,
    open_objective: ClaimObjective | None = None,
) -> tuple[Opportunity, CatalogueCandidate]:
    suffix = uuid.uuid4().hex
    now = datetime.now(UTC)
    reviewer = User(
        id=uuid.uuid4(),
        email=f"reviewer-{suffix}@example.com",
        role=UserRole.ADMIN,
        is_active=True,
    )
    provider = Provider(
        id=uuid.uuid4(),
        name=f"Official Provider {suffix}",
        canonical_id=f"provider-{suffix}",
    )
    opportunity = Opportunity(
        id=uuid.uuid4(),
        provider_id=provider.id,
        name=f"Flagship Scholarship {suffix}",
        country="Singapore",
        degree_level=DegreeLevel.MASTERS,
        status=OpportunityStatus.ACTIVE,
        independence_status=IndependenceStatus.CONFIRMED_INDEPENDENT,
        publication_completeness="incomplete",
    )
    source = Source(
        id=uuid.uuid4(),
        opportunity_id=opportunity.id,
        url=f"https://official.example/{suffix}",
        normalized_url=f"https://official.example/{suffix}",
        source_type=SourceType.OFFICIAL,
        title="Official scholarship call",
        relevant_excerpt="Official scholarship facts.",
        verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        last_verified_at=now - timedelta(days=91 if stale else 1),
        verified_by_user_id=reviewer.id,
        officiality_status=OfficialityStatus.OFFICIAL,
        source_owner_type=SourceOwnerType.PROVIDER,
        source_owner_id=provider.id,
    )
    cycle = OpportunityCycle(
        id=uuid.uuid4(),
        opportunity_id=opportunity.id,
        label="2027",
        intake_year=2027,
        application_deadline=now + timedelta(days=180),
        is_current=True,
        source_id=source.id,
    )
    opportunity.current_cycle_id = cycle.id
    run = CatalogueIngestionRun(
        id=uuid.uuid4(),
        source_label=f"launch-{suffix}",
        source_fingerprint=suffix.ljust(64, "0")[:64],
        mode=IngestionMode.REVIEW_QUEUE,
        status=IngestionRunStatus.COMPLETED,
        dry_run=False,
        max_candidates=1,
        max_pages_per_candidate=1,
        max_model_calls=1,
        max_input_characters=1_000,
        max_output_tokens=1_000,
        max_estimated_cost=Decimal("1"),
    )
    candidate = CatalogueCandidate(
        id=uuid.uuid4(),
        run_id=run.id,
        seed_index=0,
        idempotency_key=suffix.ljust(64, "0")[:64],
        seed_name=opportunity.name,
        seed_provider=provider.name,
        seed_official_url=source.url,
        status=CandidateStatus.PUBLISHED,
        opportunity_id=opportunity.id,
    )
    review = CatalogueCandidateReview(
        candidate_id=candidate.id,
        state=CatalogueProposalState.PUBLISHED,
        reviewed_by_user_id=reviewer.id,
        reviewed_at=now,
        materialized_at=now,
        published_at=now,
        materialization_revision="catalogue-graph.v1",
    )
    root = CatalogueScopeNode(
        id=uuid.uuid4(),
        candidate_id=candidate.id,
        node_type=ScopeNodeType.SCHOLARSHIP_FAMILY,
        canonical_key=f"scholarship-{suffix}",
        display_label=opportunity.name,
        provenance_json={"reviewed": True},
    )
    cells = [
        CatalogueCoverageCell(
            candidate_id=candidate.id,
            objective=objective,
            scope_node_id=root.id,
            state=(
                coverage_state
                if objective is ClaimObjective.FUNDING
                else ScopedCoverageState.COMPLETE
            ),
            required=True,
            supporting_evidence_ids=[f"evidence-{objective.value}"],
            reason="Persisted deterministic coverage result.",
            evaluator_version="test.v1",
            input_fingerprint=suffix.ljust(64, "0")[:64],
        )
        for objective in CRITICAL_OBJECTIVES
    ]
    if open_objective is not None:
        cells.append(
            CatalogueCoverageCell(
                candidate_id=candidate.id,
                objective=open_objective,
                scope_node_id=root.id,
                state=ScopedCoverageState.UNKNOWN,
                required=True,
                reason="Coverage remains open.",
                missing_frontier_reasons=["resolve_scoped_evidence"],
                evaluator_version="test.v1",
                input_fingerprint=suffix.ljust(64, "0")[:64],
            )
        )
    db_session.add_all([reviewer, provider, run])
    db_session.flush()
    db_session.add(opportunity)
    db_session.flush()
    db_session.add_all([source, cycle])
    db_session.flush()
    db_session.add(candidate)
    db_session.flush()
    db_session.add_all([review, root])
    db_session.flush()
    db_session.add_all(cells)
    db_session.commit()
    return opportunity, candidate


def test_launch_audit_blocks_stale_or_incomplete_records(db_session: Session) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, _ = create_launch_fixture(
        db_session,
        stale=True,
        coverage_state=ScopedCoverageState.UNKNOWN,
    )

    result = audit_launch_catalogue(db_session, minimum_records=1)

    assert result.ready is False
    assert result.blockers_by_code["stale_official_source"] == 1
    assert result.blockers_by_code["incomplete_record"] == 1
    assert result.opportunity_ids_by_blocker["stale_official_source"] == [opportunity.id]
    assert result.opportunity_ids_by_blocker["incomplete_record"] == [opportunity.id]


def test_launch_audit_uses_persisted_coverage_instead_of_publication_string(
    db_session: Session,
) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, _ = create_launch_fixture(db_session)
    assert opportunity.publication_completeness == "incomplete"

    result = audit_launch_catalogue(db_session, minimum_records=1)

    assert result.ready is True
    assert result.active_reviewed_count == 1
    assert result.complete_core_count == 1
    assert result.publishable_with_gaps_count == 0
    assert result.publishable_count == 1
    assert result.blockers_by_code == {}


def test_launch_audit_keeps_source_blockers_separate_from_coverage_tier(
    db_session: Session,
) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    create_launch_fixture(db_session, stale=True)

    result = audit_launch_catalogue(db_session, minimum_records=1)

    assert result.ready is False
    assert result.complete_core_count == 1
    assert result.publishable_count == 1
    assert "minimum_records" not in result.blockers_by_code
    assert result.blockers_by_code["stale_official_source"] == 1


def test_launch_audit_allows_only_noncritical_open_cells_and_lists_them(
    db_session: Session,
) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, _ = create_launch_fixture(
        db_session,
        open_objective=ClaimObjective.DOCUMENTS_CORE,
    )

    result = audit_launch_catalogue(db_session, minimum_records=1)

    assert result.ready is True
    assert result.complete_core_count == 0
    assert result.publishable_with_gaps_count == 1
    assert result.publishable_count == 1
    assert result.publishable_with_gaps[0].opportunity_id == opportunity.id
    assert [cell.objective for cell in result.publishable_with_gaps[0].open_coverage_cells] == [
        ClaimObjective.DOCUMENTS_CORE
    ]
    assert (
        result.publishable_with_gaps[0].open_coverage_cells[0].state is ScopedCoverageState.UNKNOWN
    )


def test_launch_audit_reports_tier_zero_and_dimension_blockers_with_exact_ids(
    db_session: Session,
) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, candidate = create_launch_fixture(
        db_session,
        coverage_state=ScopedCoverageState.UNKNOWN,
    )
    opportunity.independence_status = IndependenceStatus.UNRESOLVED
    opportunity.current_cycle_id = None
    for source in opportunity.sources:
        source.verification_status = VerificationStatus.NEEDS_REVIEW
    identity_cell = next(
        cell
        for cell in db_session.query(CatalogueCoverageCell).filter_by(candidate_id=candidate.id)
        if cell.objective is ClaimObjective.IDENTITY
    )
    identity_cell.state = ScopedCoverageState.UNKNOWN
    identity_cell.supporting_evidence_ids = []
    db_session.commit()

    result = audit_launch_catalogue(db_session, minimum_records=1)

    expected_id = [opportunity.id]
    assert result.opportunity_ids_by_blocker["missing_tier0_evidence"] == expected_id
    assert result.opportunity_ids_by_blocker["missing_identity"] == expected_id
    assert result.opportunity_ids_by_blocker["missing_current_cycle"] == expected_id
    assert result.opportunity_ids_by_blocker["missing_funding"] == expected_id
    assert result.opportunity_ids_by_blocker["missing_evidence"] == expected_id
    assert result.opportunity_ids_by_blocker["incomplete_record"] == expected_id


def test_launch_audit_blocks_unresolved_source_or_coverage_conflicts(
    db_session: Session,
) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, candidate = create_launch_fixture(db_session)
    opportunity.sources[0].verification_status = VerificationStatus.CONFLICTING_INFORMATION
    funding = next(
        cell
        for cell in db_session.query(CatalogueCoverageCell).filter_by(candidate_id=candidate.id)
        if cell.objective is ClaimObjective.FUNDING
    )
    funding.state = ScopedCoverageState.CONFLICTING
    db_session.commit()

    result = audit_launch_catalogue(db_session, minimum_records=1)

    assert result.unresolved_conflict_count == 1
    assert result.opportunity_ids_by_blocker["unresolved_conflict"] == [opportunity.id]


def test_launch_audit_blocks_summary_claims_without_projection_evidence(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.opportunities import launch_audit

    opportunity, _ = create_launch_fixture(db_session)
    unsupported = DecisionSummaryBlockResponse(
        text="A claim without public evidence.",
        evidence_ids=[uuid.uuid4()],
        state=DecisionSummaryState.CONFIRMED,
    )
    unknown = DecisionSummaryBlockResponse(
        text="Unknown.",
        evidence_ids=[],
        state=DecisionSummaryState.UNKNOWN,
    )
    projection = PublicScholarshipProjectionResponse(
        summary=ScholarshipDecisionSummaryResponse(
            overview=unsupported,
            funding=unknown,
            eligibility=unknown,
            application_route=unknown,
        )
    )
    monkeypatch.setattr(launch_audit, "build_public_projection", lambda *_: projection)

    result = launch_audit.audit_launch_catalogue(db_session, minimum_records=1)

    assert result.ready is False
    assert result.opportunity_ids_by_blocker["unsupported_public_summary_claim"] == [opportunity.id]


def test_launch_audit_is_read_only(db_session: Session) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, candidate = create_launch_fixture(db_session)
    writes: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", record_statement)
    try:
        audit_launch_catalogue(db_session, minimum_records=1)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", record_statement)

    assert writes == []
    assert db_session.get(Opportunity, opportunity.id).publication_completeness == "incomplete"
    assert all(
        cell.evaluator_version == "test.v1"
        for cell in db_session.query(CatalogueCoverageCell).filter_by(candidate_id=candidate.id)
    )


def test_launch_catalogue_cli_emits_json_and_exits_nonzero_for_blocker(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.cli import audit_launch_catalogue as cli

    create_launch_fixture(db_session)
    monkeypatch.setattr(cli, "SystemSessionLocal", lambda: nullcontext(db_session))

    with pytest.raises(SystemExit) as raised:
        cli.main(["--minimum-records", "2"])

    assert raised.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["minimum_records"] == 2
    assert payload["blockers_by_code"]["minimum_records"] == 1
    assert cli.parser().parse_args([]).minimum_records == 12
