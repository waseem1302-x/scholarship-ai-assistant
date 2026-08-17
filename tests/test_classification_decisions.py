import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.classification import (
    ClassificationDecisionRecorder,
    ClassificationIntegrityError,
    ConfidenceBand,
    RelationshipDecision,
)
from app.modules.catalogue_ingestion.models import (
    ClassificationDecision,
    ClassificationDecisionStatus,
    CatalogueCandidate,
    CatalogueIngestionRun,
    IngestionMode,
    IngestionRunStatus,
)
from app.modules.opportunities.evidence_models import OfficialityStatus, SourceSnapshot
from app.modules.opportunities.graph_models import RelationshipKind
from app.modules.opportunities.models import (
    DataConfidence,
    DegreeLevel,
    FundingType,
    IndependenceStatus,
    Opportunity,
    OpportunityStatus,
    Provider,
    Source,
    SourceType,
    VerificationStatus,
)


def create_candidate(db_session: Session) -> CatalogueCandidate:
    run = CatalogueIngestionRun(
        source_label="PR3 classification fixture",
        source_fingerprint=uuid.uuid4().hex,
        mode=IngestionMode.CANDIDATE_ONLY,
        status=IngestionRunStatus.PENDING,
        dry_run=True,
        max_candidates=10,
        max_pages_per_candidate=3,
        max_model_calls=0,
        max_input_characters=80_000,
        max_output_tokens=4_000,
        max_estimated_cost=Decimal("0"),
    )
    db_session.add(run)
    db_session.flush()
    candidate = CatalogueCandidate(
        run_id=run.id,
        seed_index=0,
        idempotency_key=uuid.uuid4().hex,
        seed_name="Candidate scholarship page",
        seed_keywords=[],
    )
    db_session.add(candidate)
    db_session.flush()
    return candidate


def create_scholarship(db_session: Session, name: str = "Canonical Scholarship") -> Opportunity:
    provider = Provider(name=f"PR3 provider {uuid.uuid4()}")
    db_session.add(provider)
    db_session.flush()
    scholarship = Opportunity(
        provider_id=provider.id,
        name=name,
        canonical_slug=f"pr3-{uuid.uuid4().hex}",
        country="China",
        degree_level=DegreeLevel.MASTERS,
        funding_type=FundingType.UNKNOWN,
        status=OpportunityStatus.DRAFT,
        data_confidence=DataConfidence.LOW,
        required_documents=[],
        eligibility_warnings=[],
    )
    db_session.add(scholarship)
    db_session.flush()
    return scholarship


def create_snapshot(db_session: Session, scholarship: Opportunity) -> SourceSnapshot:
    path = uuid.uuid4().hex
    evidence_text = "Official relationship evidence."
    source = Source(
        opportunity_id=scholarship.id,
        url=f"https://example.edu/{path}",
        canonical_url=f"https://example.edu/{path}",
        normalized_url=f"https://example.edu/{path}",
        domain="example.edu",
        source_type=SourceType.OFFICIAL,
        officiality_status=OfficialityStatus.OFFICIAL,
        officiality_reason="PR3 fixture official source",
        verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        title="PR3 classification evidence",
        relevant_excerpt=evidence_text,
        is_active=True,
    )
    db_session.add(source)
    db_session.flush()
    snapshot = SourceSnapshot(
        source_id=source.id,
        http_status=200,
        content_hash=uuid.uuid4().hex,
        normalized_text=evidence_text,
        extraction_method="http_text",
        language_code="en",
        byte_count=len(evidence_text.encode()),
        character_count=len(evidence_text),
        fetch_metadata={},
    )
    db_session.add(snapshot)
    db_session.flush()
    return snapshot


def child_decision() -> RelationshipDecision:
    return RelationshipDecision(
        relationship=RelationshipKind.PARTICIPATING_INSTITUTION,
        confidence_band=ConfidenceBand.HIGH,
        reason_code="explicit_official_relationship",
        deterministic_signals=("official_source", "parent_scheme_explicit"),
    )


def independent_decision() -> RelationshipDecision:
    return RelationshipDecision(
        relationship=RelationshipKind.INDEPENDENT_UNIVERSITY_SCHOLARSHIP,
        confidence_band=ConfidenceBand.HIGH,
        reason_code="independence_proven_pending_human_review",
        deterministic_signals=(
            "official_name_explicit",
            "awarding_authority_explicit",
            "separate_application",
            "independent_award_decision",
            "current_official_source",
        ),
        proposes_independent_scholarship=True,
    )


def test_recorded_child_decision_is_review_only_and_links_parent(db_session: Session) -> None:
    candidate = create_candidate(db_session)
    scholarship = create_scholarship(db_session)
    snapshot = create_snapshot(db_session, scholarship)

    recorded = ClassificationDecisionRecorder(db_session).record(
        candidate_id=candidate.id,
        decision=child_decision(),
        parent_scholarship_id=scholarship.id,
        evidence_snapshot_ids=(snapshot.id,),
    )
    db_session.flush()

    assert recorded.proposed_relationship == RelationshipKind.PARTICIPATING_INSTITUTION
    assert recorded.parent_scholarship_id == scholarship.id
    assert recorded.decision_status == ClassificationDecisionStatus.NEEDS_REVIEW
    assert recorded.reviewer_id is None
    assert recorded.reviewed_at is None
    assert recorded.proposed_new_scholarship_id is None


def test_child_relationship_without_parent_fails_closed(db_session: Session) -> None:
    candidate = create_candidate(db_session)
    scholarship = create_scholarship(db_session)
    snapshot = create_snapshot(db_session, scholarship)

    with pytest.raises(ClassificationIntegrityError, match="parent scholarship"):
        ClassificationDecisionRecorder(db_session).record(
            candidate_id=candidate.id,
            decision=child_decision(),
            evidence_snapshot_ids=(snapshot.id,),
        )


def test_non_unresolved_relationship_requires_persisted_evidence_snapshot(
    db_session: Session,
) -> None:
    candidate = create_candidate(db_session)
    scholarship = create_scholarship(db_session)

    with pytest.raises(ClassificationIntegrityError, match="evidence snapshot"):
        ClassificationDecisionRecorder(db_session).record(
            candidate_id=candidate.id,
            decision=child_decision(),
            parent_scholarship_id=scholarship.id,
            evidence_snapshot_ids=(),
        )


def test_unknown_snapshot_identifier_fails_closed(db_session: Session) -> None:
    candidate = create_candidate(db_session)
    scholarship = create_scholarship(db_session)

    with pytest.raises(ClassificationIntegrityError, match="does not exist"):
        ClassificationDecisionRecorder(db_session).record(
            candidate_id=candidate.id,
            decision=child_decision(),
            parent_scholarship_id=scholarship.id,
            evidence_snapshot_ids=(uuid.uuid4(),),
        )


def test_independent_proposal_does_not_create_or_confirm_scholarship(
    db_session: Session,
) -> None:
    candidate = create_candidate(db_session)
    evidence_owner = create_scholarship(db_session, "Evidence Owner Scholarship")
    snapshot = create_snapshot(db_session, evidence_owner)
    opportunity_ids_before = set(db_session.scalars(select(Opportunity.id)).all())

    recorded = ClassificationDecisionRecorder(db_session).record(
        candidate_id=candidate.id,
        decision=independent_decision(),
        evidence_snapshot_ids=(snapshot.id,),
    )
    db_session.flush()

    opportunity_ids_after = set(db_session.scalars(select(Opportunity.id)).all())
    assert opportunity_ids_after == opportunity_ids_before
    assert recorded.decision_status == ClassificationDecisionStatus.NEEDS_REVIEW
    assert recorded.proposed_new_scholarship_id is None
    assert evidence_owner.independence_status == IndependenceStatus.LEGACY_UNREVIEWED


def test_recorder_rejects_any_auto_publish_decision(db_session: Session) -> None:
    candidate = create_candidate(db_session)
    decision = RelationshipDecision(
        relationship=RelationshipKind.UNRESOLVED,
        confidence_band=ConfidenceBand.UNRESOLVED,
        reason_code="unsafe_fixture",
        auto_publish_allowed=True,
    )

    with pytest.raises(ClassificationIntegrityError, match="auto-publication"):
        ClassificationDecisionRecorder(db_session).record(
            candidate_id=candidate.id,
            decision=decision,
        )


def test_model_output_is_untrusted_audit_metadata_not_approval(db_session: Session) -> None:
    candidate = create_candidate(db_session)

    recorded = ClassificationDecisionRecorder(db_session).record(
        candidate_id=candidate.id,
        decision=RelationshipDecision(
            relationship=RelationshipKind.UNRESOLVED,
            confidence_band=ConfidenceBand.UNRESOLVED,
            reason_code="model_proposal_unverified",
        ),
        model_output={"relationship": "independent_university_scholarship", "confidence": 0.99},
    )
    db_session.flush()

    assert recorded.proposed_relationship == RelationshipKind.UNRESOLVED
    assert recorded.decision_status == ClassificationDecisionStatus.NEEDS_REVIEW
    assert recorded.model_output["confidence"] == 0.99
    assert recorded.proposed_new_scholarship_id is None


def test_repeat_classification_appends_new_decision_instead_of_overwriting_history(
    db_session: Session,
) -> None:
    candidate = create_candidate(db_session)

    recorder = ClassificationDecisionRecorder(db_session)
    first = recorder.record(
        candidate_id=candidate.id,
        decision=RelationshipDecision(
            relationship=RelationshipKind.UNRESOLVED,
            confidence_band=ConfidenceBand.UNRESOLVED,
            reason_code="insufficient_evidence",
        ),
    )
    second = recorder.record(
        candidate_id=candidate.id,
        decision=RelationshipDecision(
            relationship=RelationshipKind.UNRESOLVED,
            confidence_band=ConfidenceBand.UNRESOLVED,
            reason_code="new_evidence_still_ambiguous",
        ),
    )
    db_session.flush()

    rows = list(
        db_session.scalars(
            select(ClassificationDecision).where(ClassificationDecision.candidate_id == candidate.id)
        ).all()
    )
    assert first.id != second.id
    assert len(rows) == 2
    assert {row.reason_code for row in rows} == {
        "insufficient_evidence",
        "new_evidence_still_ambiguous",
    }
