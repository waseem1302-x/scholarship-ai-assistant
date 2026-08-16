import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.evidence import EvidenceIntegrityError, EvidenceStore
from app.modules.opportunities.evidence_models import (
    EvidenceSupportType,
    EvidenceValidatorStatus,
    OfficialityStatus,
    RequiredDocument,
    ScopedDeadline,
    SourceOwnerType,
    SourceSnapshot,
)
from app.modules.opportunities.graph_models import (
    AcademicProgramme,
    ApplicationTrack,
    Institution,
)
from app.modules.opportunities.graph_query import FactScope, resolve_scoped_deadline
from app.modules.opportunities.models import (
    DataConfidence,
    DegreeLevel,
    EligibilityOperator,
    EligibilityRule,
    EligibilityRuleType,
    FundingType,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    Provider,
    Source,
    SourceType,
    VerificationStatus,
)


def create_scholarship(db_session: Session) -> Opportunity:
    provider = Provider(name=f"PR2 evidence provider {uuid.uuid4()}")
    db_session.add(provider)
    db_session.flush()
    scholarship = Opportunity(
        provider_id=provider.id,
        name="Chinese Government Scholarship",
        canonical_slug=f"csc-pr2-{uuid.uuid4().hex}",
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


def create_scope(db_session: Session, scholarship: Opportunity):
    cycle = OpportunityCycle(
        opportunity_id=scholarship.id,
        label="2027/28",
        timezone="Asia/Shanghai",
        is_current=True,
    )
    institution = Institution(
        canonical_name="PR2 Evidence University",
        slug=f"pr2-evidence-university-{uuid.uuid4().hex}",
        institution_type="university",
        country_code="CN",
        identity_status="fixture_only",
    )
    db_session.add_all([cycle, institution])
    db_session.flush()
    track = ApplicationTrack(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        code=f"university-route-{uuid.uuid4().hex[:8]}",
        name="University route",
        track_type="university",
    )
    programme = AcademicProgramme(
        institution_id=institution.id,
        canonical_name="PR2 Evidence Programme",
        slug=f"pr2-evidence-programme-{uuid.uuid4().hex}",
        degree_level=DegreeLevel.MASTERS,
        field_codes=["computer-science"],
    )
    db_session.add_all([track, programme])
    db_session.flush()
    return cycle, track, institution, programme


def create_snapshot(
    db_session: Session,
    scholarship: Opportunity,
    text: str,
) -> SourceSnapshot:
    path = uuid.uuid4().hex
    source = Source(
        opportunity_id=scholarship.id,
        url=f"https://example.edu/{path}/scholarship",
        canonical_url=f"https://example.edu/{path}/scholarship",
        normalized_url=f"https://example.edu/{path}/scholarship",
        domain="example.edu",
        source_type=SourceType.OFFICIAL,
        source_owner_type=SourceOwnerType.INSTITUTION,
        officiality_status=OfficialityStatus.OFFICIAL,
        officiality_reason="fixture resolved to the institution identity",
        robots_status="allowed",
        content_type="text/html",
        title="PR2 official source fixture",
        relevant_excerpt=text,
        verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        is_active=True,
    )
    db_session.add(source)
    db_session.flush()
    snapshot = SourceSnapshot(
        source_id=source.id,
        http_status=200,
        content_hash=uuid.uuid4().hex,
        normalized_text=text,
        extraction_method="http_text",
        language_code="en",
        byte_count=len(text.encode()),
        character_count=len(text),
        fetch_metadata={},
    )
    db_session.add(snapshot)
    db_session.commit()
    return snapshot


def add_explicit_evidence(
    db_session: Session,
    *,
    fact: ScopedDeadline,
    snapshot: SourceSnapshot,
    excerpt: str,
) -> None:
    start = snapshot.normalized_text.index(excerpt)
    EvidenceStore(db_session).add_field_evidence(
        entity_type="scoped_deadline",
        entity_id=fact.id,
        field_path="deadline_at",
        source_snapshot_id=snapshot.id,
        excerpt=excerpt,
        excerpt_start=start,
        excerpt_end=start + len(excerpt),
        support_type=EvidenceSupportType.EXPLICIT,
        validator_status=EvidenceValidatorStatus.PASSED,
    )
    db_session.commit()


def test_graph_evidence_reuses_legacy_source_identity(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    snapshot = create_snapshot(
        db_session,
        scholarship,
        "Applications close on 30 June 2027.",
    )

    source = db_session.get(Source, snapshot.source_id)
    assert source is not None
    assert source.opportunity_id == scholarship.id
    assert source.normalized_url == source.canonical_url
    assert source.officiality_status == OfficialityStatus.OFFICIAL


def test_normalized_source_url_is_unique_within_scholarship(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    normalized_url = "https://example.edu/scholarships/csc"
    db_session.add_all(
        [
            Source(
                opportunity_id=scholarship.id,
                url=normalized_url,
                canonical_url=normalized_url,
                normalized_url=normalized_url,
                domain="example.edu",
                source_type=SourceType.OFFICIAL,
                source_owner_type=SourceOwnerType.INSTITUTION,
                officiality_status=OfficialityStatus.OFFICIAL,
                officiality_reason="resolved institution source",
                robots_status="allowed",
                title="Primary official source",
                relevant_excerpt="Official scholarship information.",
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
                is_active=True,
            ),
            Source(
                opportunity_id=scholarship.id,
                url=f"{normalized_url}?duplicate=1",
                canonical_url=f"{normalized_url}?duplicate=1",
                normalized_url=normalized_url,
                domain="example.edu",
                source_type=SourceType.OFFICIAL,
                source_owner_type=SourceOwnerType.INSTITUTION,
                officiality_status=OfficialityStatus.OFFICIAL,
                officiality_reason="same normalized source",
                robots_status="allowed",
                title="Duplicate normalized source",
                relevant_excerpt="Duplicate normalized source fixture.",
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
                is_active=True,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_source_snapshots_are_immutable_and_not_deletable(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    snapshot = create_snapshot(
        db_session,
        scholarship,
        "Applications close on 30 June 2027.",
    )

    snapshot.normalized_text = "tampered evidence"
    with pytest.raises(EvidenceIntegrityError):
        db_session.commit()
    db_session.rollback()

    snapshot = db_session.get(SourceSnapshot, snapshot.id)
    assert snapshot is not None
    db_session.delete(snapshot)
    with pytest.raises(EvidenceIntegrityError):
        db_session.commit()


def test_field_evidence_excerpt_must_match_snapshot_offsets(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    text = "Applications close on 30 June 2027. Submit through the university portal."
    snapshot = create_snapshot(db_session, scholarship, text)
    excerpt = "30 June 2027"
    start = text.index(excerpt)
    store = EvidenceStore(db_session)

    evidence = store.add_field_evidence(
        entity_type="scoped_deadline",
        entity_id=uuid.uuid4(),
        field_path="deadline_at",
        source_snapshot_id=snapshot.id,
        excerpt=excerpt,
        excerpt_start=start,
        excerpt_end=start + len(excerpt),
        support_type=EvidenceSupportType.EXPLICIT,
        validator_status=EvidenceValidatorStatus.PASSED,
    )
    db_session.flush()
    assert evidence.excerpt == excerpt

    with pytest.raises(EvidenceIntegrityError):
        store.add_field_evidence(
            entity_type="scoped_deadline",
            entity_id=uuid.uuid4(),
            field_path="deadline_at",
            source_snapshot_id=snapshot.id,
            excerpt="31 July 2027",
            excerpt_start=start,
            excerpt_end=start + len("31 July 2027"),
            support_type=EvidenceSupportType.EXPLICIT,
            validator_status=EvidenceValidatorStatus.PASSED,
        )


def test_local_deadline_does_not_override_without_explicit_passed_evidence(
    db_session: Session,
) -> None:
    scholarship = create_scholarship(db_session)
    cycle, track, institution, _ = create_scope(db_session, scholarship)
    global_deadline = ScopedDeadline(
        scholarship_id=scholarship.id,
        deadline_type="application",
        deadline_at=datetime(2027, 7, 15, tzinfo=UTC),
        timezone="UTC",
        label="Global application deadline",
    )
    local_deadline = ScopedDeadline(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        track_id=track.id,
        institution_id=institution.id,
        deadline_type="application",
        deadline_at=datetime(2027, 6, 30, tzinfo=UTC),
        timezone="Asia/Shanghai",
        label="University route deadline",
    )
    db_session.add_all([global_deadline, local_deadline])
    db_session.commit()

    resolution = resolve_scoped_deadline(
        db_session,
        scholarship_id=scholarship.id,
        deadline_type="application",
        scope=FactScope(
            cycle_id=cycle.id,
            track_id=track.id,
            institution_id=institution.id,
        ),
    )

    assert resolution.conflict is False
    assert resolution.fact_id == global_deadline.id
    assert resolution.scope_level == "scholarship"


def test_explicit_passed_local_deadline_overrides_inherited_deadline(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    cycle, track, institution, _ = create_scope(db_session, scholarship)
    global_deadline = ScopedDeadline(
        scholarship_id=scholarship.id,
        deadline_type="application",
        deadline_at=datetime(2027, 7, 15, tzinfo=UTC),
        timezone="UTC",
        label="Global application deadline",
    )
    local_deadline = ScopedDeadline(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        track_id=track.id,
        institution_id=institution.id,
        deadline_type="application",
        deadline_at=datetime(2027, 6, 30, tzinfo=UTC),
        timezone="Asia/Shanghai",
        label="University route deadline",
    )
    db_session.add_all([global_deadline, local_deadline])
    db_session.commit()
    snapshot = create_snapshot(
        db_session,
        scholarship,
        "For the university route, applications close on 30 June 2027.",
    )
    add_explicit_evidence(
        db_session,
        fact=local_deadline,
        snapshot=snapshot,
        excerpt="30 June 2027",
    )

    resolution = resolve_scoped_deadline(
        db_session,
        scholarship_id=scholarship.id,
        deadline_type="application",
        scope=FactScope(
            cycle_id=cycle.id,
            track_id=track.id,
            institution_id=institution.id,
        ),
    )

    assert resolution.conflict is False
    assert resolution.fact_id == local_deadline.id
    assert resolution.scope_level == "institution_track"
    assert resolution.deadline_at == local_deadline.deadline_at


def test_contradictory_child_fact_returns_review_conflict(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    cycle, track, institution, _ = create_scope(db_session, scholarship)
    global_deadline = ScopedDeadline(
        scholarship_id=scholarship.id,
        deadline_type="application",
        deadline_at=datetime(2027, 7, 15, tzinfo=UTC),
        timezone="UTC",
        label="Global application deadline",
    )
    local_deadline = ScopedDeadline(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        track_id=track.id,
        institution_id=institution.id,
        deadline_type="application",
        deadline_at=datetime(2027, 6, 30, tzinfo=UTC),
        timezone="Asia/Shanghai",
        label="Conflicting university route deadline",
    )
    db_session.add_all([global_deadline, local_deadline])
    db_session.commit()
    snapshot = create_snapshot(
        db_session,
        scholarship,
        "The local page contradicts the umbrella deadline and lists 30 June 2027.",
    )
    excerpt = "30 June 2027"
    start = snapshot.normalized_text.index(excerpt)
    EvidenceStore(db_session).add_field_evidence(
        entity_type="scoped_deadline",
        entity_id=local_deadline.id,
        field_path="deadline_at",
        source_snapshot_id=snapshot.id,
        excerpt=excerpt,
        excerpt_start=start,
        excerpt_end=start + len(excerpt),
        support_type=EvidenceSupportType.CONTRADICTS,
        validator_status=EvidenceValidatorStatus.PASSED,
    )
    db_session.commit()

    resolution = resolve_scoped_deadline(
        db_session,
        scholarship_id=scholarship.id,
        deadline_type="application",
        scope=FactScope(
            cycle_id=cycle.id,
            track_id=track.id,
            institution_id=institution.id,
        ),
    )

    assert resolution.conflict is True
    assert resolution.fact_id is None
    assert local_deadline.id in resolution.conflicting_fact_ids


def test_programme_scoped_fact_requires_institution_scope(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    _, _, _, programme = create_scope(db_session, scholarship)
    db_session.add(
        RequiredDocument(
            scholarship_id=scholarship.id,
            programme_id=programme.id,
            document_key="transcript",
            name="Academic transcript",
            required=True,
            display_order=0,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_eligibility_rule_uses_graph_scope_without_parallel_rule_table(
    db_session: Session,
) -> None:
    scholarship = create_scholarship(db_session)
    _, _, _, programme = create_scope(db_session, scholarship)
    db_session.add(
        EligibilityRule(
            opportunity_id=scholarship.id,
            programme_id=programme.id,
            rule_type=EligibilityRuleType.NATIONALITY,
            operator=EligibilityOperator.IN,
            value_json=["PK"],
            required=True,
            confidence=DataConfidence.HIGH,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
