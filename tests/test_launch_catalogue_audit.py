import hashlib
import json
import uuid
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, select
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
from app.modules.catalogue_ingestion.trust_domains import EvidenceTrustDomain
from app.modules.opportunities.evidence_models import (
    EvidenceSupportType,
    EvidenceValidatorStatus,
    FieldEvidence,
    FundingComponent,
    OfficialityStatus,
    ScopedDeadline,
    SourceOwnerType,
    SourceSnapshot,
)
from app.modules.opportunities.graph_models import ApplicationTrack
from app.modules.opportunities.materialization_models import (
    CatalogueMaterializedClaimLink,
    ScholarshipEligibilityRule,
)
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
from app.modules.opportunities.public_projection import build_public_projection
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
    open_state: ScopedCoverageState = ScopedCoverageState.UNKNOWN,
    link_coverage_evidence: bool = True,
    mismatch_coverage_link: bool = False,
    mismatch_evidence_source: bool = False,
    add_unlinked_public_funding: bool = False,
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
    track = ApplicationTrack(
        id=uuid.uuid4(),
        scholarship_id=opportunity.id,
        cycle_id=cycle.id,
        code="direct",
        name="Direct application route",
        track_type="direct",
    )
    eligibility = ScholarshipEligibilityRule(
        id=uuid.uuid4(),
        scholarship_id=opportunity.id,
        cycle_id=cycle.id,
        track_id=track.id,
        identity_key=uuid.uuid4().hex,
        rule_key="eligible-applicants",
        rule_type="nationality",
        operator="in",
        value_json={"value": ["SG"]},
        original_text="Eligible applicants may apply",
    )
    funding = FundingComponent(
        id=uuid.uuid4(),
        scholarship_id=opportunity.id,
        cycle_id=cycle.id,
        component_type="tuition",
        coverage_status="full",
    )
    unlinked_funding = (
        FundingComponent(
            id=uuid.uuid4(),
            scholarship_id=opportunity.id,
            cycle_id=cycle.id,
            component_type="stipend",
            coverage_status="full",
        )
        if add_unlinked_public_funding
        else None
    )
    deadline = ScopedDeadline(
        id=uuid.uuid4(),
        scholarship_id=opportunity.id,
        cycle_id=cycle.id,
        deadline_type="application",
        deadline_at=cycle.application_deadline,
        timezone="UTC",
    )
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
    proposal_hash = (suffix * 2)[:64]
    review = CatalogueCandidateReview(
        id=uuid.uuid4(),
        candidate_id=candidate.id,
        state=CatalogueProposalState.PUBLISHED,
        proposal_hash=proposal_hash,
        approved_proposal_hash=proposal_hash,
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
    db_session.add_all([reviewer, provider, run])
    db_session.flush()
    db_session.add(opportunity)
    db_session.flush()
    db_session.add_all([source, cycle])
    db_session.flush()
    evidence_source = source
    if mismatch_evidence_source:
        unrelated_opportunity = Opportunity(
            id=uuid.uuid4(),
            provider_id=provider.id,
            name=f"Unrelated Scholarship {suffix}",
            country="Singapore",
            degree_level=DegreeLevel.MASTERS,
            status=OpportunityStatus.DRAFT,
        )
        db_session.add(unrelated_opportunity)
        db_session.flush()
        evidence_source = Source(
            id=uuid.uuid4(),
            opportunity_id=unrelated_opportunity.id,
            url=f"https://other-official.example/{suffix}",
            normalized_url=f"https://other-official.example/{suffix}",
            source_type=SourceType.OFFICIAL,
            title="Unrelated official scholarship call",
            relevant_excerpt="Unrelated official scholarship facts.",
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            last_verified_at=now,
            verified_by_user_id=reviewer.id,
            officiality_status=OfficialityStatus.OFFICIAL,
            source_owner_type=SourceOwnerType.PROVIDER,
            source_owner_id=provider.id,
        )
        db_session.add(evidence_source)
        db_session.flush()
    db_session.add_all(
        [track, eligibility, funding, deadline]
        + ([unlinked_funding] if unlinked_funding is not None else [])
    )
    db_session.flush()
    evidence_text = (
        f"{opportunity.name}. {provider.name}. 2027 intake. Direct application route. "
        "Eligible applicants may apply. Full tuition. Applications close in 2027."
    )
    snapshot = SourceSnapshot(
        id=uuid.uuid4(),
        source_id=evidence_source.id,
        http_status=200,
        content_hash=(uuid.uuid4().hex * 2)[:64],
        normalized_text=evidence_text,
        extraction_method="http_text",
        language_code="en",
        byte_count=len(evidence_text.encode()),
        character_count=len(evidence_text),
        fetch_metadata={},
    )
    db_session.add(snapshot)
    db_session.flush()
    db_session.add(candidate)
    db_session.flush()
    db_session.add_all([review, root])
    db_session.flush()

    artifact_id = uuid.uuid4()
    claim_specs = {
        ClaimObjective.IDENTITY: [
            ("identity-name", "scholarship", opportunity.id, "name", opportunity.name),
            (
                "identity-provider",
                "scholarship",
                opportunity.id,
                "provider_name",
                provider.name,
            ),
            ("identity-cycle", "cycle", cycle.id, "intake_year", "2027 intake"),
        ],
        ClaimObjective.ROUTES: [
            ("route-name", "track", track.id, "name", "Direct application route")
        ],
        ClaimObjective.ELIGIBILITY: [
            (
                "eligibility-rule",
                "eligibility",
                eligibility.id,
                "original_text",
                "Eligible applicants may apply",
            )
        ],
        ClaimObjective.FUNDING: [
            (
                "funding-component",
                "funding",
                funding.id,
                "component_type",
                "Full tuition",
            )
        ],
        ClaimObjective.APPLICATION_TIMELINE: [
            (
                "application-deadline",
                "deadline",
                deadline.id,
                "deadline_at",
                "Applications close in 2027",
            )
        ],
    }
    claim_ids_by_objective: dict[ClaimObjective, list[str]] = {}
    evidence_ids_by_objective: dict[ClaimObjective, list[str]] = {}
    links: list[CatalogueMaterializedClaimLink] = []
    for objective, specs in claim_specs.items():
        claim_ids_by_objective[objective] = []
        evidence_ids_by_objective[objective] = []
        for claim_id, entity_type, entity_id, field_path, excerpt in specs:
            start = evidence_text.index(excerpt)
            end = start + len(excerpt)
            evidence = FieldEvidence(
                id=uuid.uuid4(),
                entity_type=entity_type,
                entity_id=entity_id,
                field_path=field_path,
                source_snapshot_id=snapshot.id,
                excerpt=excerpt,
                excerpt_start=start,
                excerpt_end=end,
                support_type=EvidenceSupportType.EXPLICIT,
                validator_status=EvidenceValidatorStatus.PASSED,
                trust_domain=EvidenceTrustDomain.OFFICIAL_FACTUAL.value,
            )
            db_session.add(evidence)
            db_session.flush()
            evidence_id = hashlib.sha256(
                f"{artifact_id}:{snapshot.content_hash}:{start}:{end}".encode()
            ).hexdigest()
            claim_ids_by_objective[objective].append(claim_id)
            evidence_ids_by_objective[objective].append(evidence_id)
            if link_coverage_evidence:
                links.append(
                    CatalogueMaterializedClaimLink(
                        candidate_id=candidate.id,
                        review_id=review.id,
                        proposal_hash=proposal_hash,
                        claim_id=claim_id,
                        entity_type=entity_type,
                        entity_id=(
                            uuid.uuid4()
                            if mismatch_coverage_link and objective is ClaimObjective.FUNDING
                            else entity_id
                        ),
                        field_path=field_path,
                        field_evidence_id=evidence.id,
                        trust_domain=EvidenceTrustDomain.OFFICIAL_FACTUAL.value,
                        provenance_json={
                            "artifact_id": str(artifact_id),
                            "source_url": evidence_source.url,
                            "content_hash": snapshot.content_hash,
                            "trust_tier": 1,
                            "objectives": [objective.value],
                            "scope": {},
                            "source_snapshot_id": str(snapshot.id),
                        },
                    )
                )

    if unlinked_funding is not None:
        excerpt = "Full tuition"
        start = evidence_text.index(excerpt)
        db_session.add(
            FieldEvidence(
                id=uuid.uuid4(),
                entity_type="funding",
                entity_id=unlinked_funding.id,
                field_path="component_type",
                source_snapshot_id=snapshot.id,
                excerpt=excerpt,
                excerpt_start=start,
                excerpt_end=start + len(excerpt),
                support_type=EvidenceSupportType.EXPLICIT,
                validator_status=EvidenceValidatorStatus.PASSED,
                trust_domain=EvidenceTrustDomain.OFFICIAL_FACTUAL.value,
            )
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
            supporting_claim_ids=claim_ids_by_objective[objective],
            supporting_evidence_ids=evidence_ids_by_objective[objective],
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
                state=open_state,
                required=True,
                reason="Coverage remains open.",
                missing_frontier_reasons=["resolve_scoped_evidence"],
                evaluator_version="test.v1",
                input_fingerprint=suffix.ljust(64, "0")[:64],
            )
        )
    db_session.add_all(links)
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


def test_launch_audit_accepts_real_evidence_backed_public_summary(
    db_session: Session,
) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, _ = create_launch_fixture(db_session)

    projection = build_public_projection(db_session, opportunity)
    result = audit_launch_catalogue(db_session, minimum_records=1)

    assert projection.summary is not None
    assert {
        projection.summary.overview.state,
        projection.summary.funding.state,
        projection.summary.eligibility.state,
        projection.summary.application_route.state,
    } == {DecisionSummaryState.CONFIRMED}
    assert all(
        block.evidence_ids
        for block in (
            projection.summary.overview,
            projection.summary.funding,
            projection.summary.eligibility,
            projection.summary.application_route,
        )
    )
    assert "unsupported_public_summary_claim" not in result.blockers_by_code
    assert result.ready is True


def test_launch_audit_rejects_real_public_summary_evidence_not_linked_to_review(
    db_session: Session,
) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, candidate = create_launch_fixture(
        db_session,
        add_unlinked_public_funding=True,
    )

    projection = build_public_projection(db_session, opportunity)
    result = audit_launch_catalogue(db_session, minimum_records=1)
    linked_evidence_ids = set(
        db_session.scalars(
            select(CatalogueMaterializedClaimLink.field_evidence_id).where(
                CatalogueMaterializedClaimLink.candidate_id == candidate.id
            )
        )
    )

    assert projection.summary is not None
    assert projection.summary.funding.state is DecisionSummaryState.CONFIRMED
    assert set(projection.summary.funding.evidence_ids) - linked_evidence_ids
    assert result.ready is False
    assert result.opportunity_ids_by_blocker["unsupported_public_summary_claim"] == [
        opportunity.id
    ]


@pytest.mark.parametrize(
    ("link_coverage_evidence", "mismatch_coverage_link", "missing_tier_zero"),
    [(False, False, True), (True, True, False)],
)
def test_launch_audit_rejects_missing_or_mismatched_materialized_coverage_evidence(
    db_session: Session,
    link_coverage_evidence: bool,
    mismatch_coverage_link: bool,
    missing_tier_zero: bool,
) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, _ = create_launch_fixture(
        db_session,
        link_coverage_evidence=link_coverage_evidence,
        mismatch_coverage_link=mismatch_coverage_link,
    )

    result = audit_launch_catalogue(db_session, minimum_records=1)

    assert result.ready is False
    assert result.opportunity_ids_by_blocker["missing_evidence"] == [opportunity.id]
    assert ("missing_tier0_evidence" in result.opportunity_ids_by_blocker) is missing_tier_zero


def test_launch_audit_rejects_coverage_evidence_from_another_opportunity(
    db_session: Session,
) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, _ = create_launch_fixture(db_session, mismatch_evidence_source=True)

    result = audit_launch_catalogue(db_session, minimum_records=1)

    assert result.ready is False
    assert result.opportunity_ids_by_blocker["missing_evidence"] == [opportunity.id]
    assert result.opportunity_ids_by_blocker["missing_tier0_evidence"] == [opportunity.id]


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


@pytest.mark.parametrize(
    "open_state",
    [
        ScopedCoverageState.NOT_YET_ACQUIRED,
        ScopedCoverageState.BLOCKED,
        ScopedCoverageState.NOT_STATED,
        ScopedCoverageState.PARTIAL,
        ScopedCoverageState.CONFLICTING,
        ScopedCoverageState.QUARANTINED,
        ScopedCoverageState.FAILED,
    ],
)
def test_launch_audit_rejects_noncritical_states_other_than_unknown(
    db_session: Session,
    open_state: ScopedCoverageState,
) -> None:
    from app.modules.opportunities.launch_audit import audit_launch_catalogue

    opportunity, _ = create_launch_fixture(
        db_session,
        open_objective=ClaimObjective.DOCUMENTS_CORE,
        open_state=open_state,
    )

    result = audit_launch_catalogue(db_session, minimum_records=1)

    assert result.publishable_count == 0
    assert result.publishable_with_gaps_count == 0
    assert result.opportunity_ids_by_blocker["incomplete_record"] == [opportunity.id]


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
