import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.evidence import EvidenceStore
from app.modules.opportunities.evidence_models import (
    EvidenceSupportType,
    EvidenceValidatorStatus,
    OfficialityStatus,
    ScopedDeadline,
    SourceOwnerType,
    SourceSnapshot,
)
from app.modules.opportunities.graph_models import AcademicProgramme, ApplicationTrack, Institution
from app.modules.opportunities.graph_query import FactScope, resolve_scoped_deadline
from app.modules.opportunities.models import (
    DataConfidence,
    DegreeLevel,
    FundingType,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    Provider,
    Source,
    SourceType,
    VerificationStatus,
)


def _scholarship(db_session: Session) -> Opportunity:
    provider = Provider(name=f"Inheritance provider {uuid.uuid4()}")
    db_session.add(provider)
    db_session.flush()
    scholarship = Opportunity(
        provider_id=provider.id,
        name="Inheritance Scholarship",
        canonical_slug=f"inheritance-{uuid.uuid4().hex}",
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


def _scope(db_session: Session, scholarship: Opportunity):
    cycle = OpportunityCycle(
        opportunity_id=scholarship.id,
        label="2027/28",
        timezone="Asia/Shanghai",
        is_current=True,
    )
    institution = Institution(
        canonical_name="Inheritance University",
        slug=f"inheritance-university-{uuid.uuid4().hex}",
        institution_type="university",
        country_code="CN",
        identity_status="fixture_only",
    )
    db_session.add_all([cycle, institution])
    db_session.flush()
    track = ApplicationTrack(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        code=f"route-{uuid.uuid4().hex[:8]}",
        name="University route",
        track_type="university",
    )
    programme = AcademicProgramme(
        institution_id=institution.id,
        canonical_name="Inheritance Programme",
        slug=f"inheritance-programme-{uuid.uuid4().hex}",
        degree_level=DegreeLevel.MASTERS,
        field_codes=["computer-science"],
    )
    db_session.add_all([track, programme])
    db_session.flush()
    return cycle, track, institution, programme


def _explicit_evidence(
    db_session: Session,
    scholarship: Opportunity,
    fact: ScopedDeadline,
    excerpt: str,
) -> None:
    path = uuid.uuid4().hex
    source = Source(
        opportunity_id=scholarship.id,
        url=f"https://example.edu/{path}",
        canonical_url=f"https://example.edu/{path}",
        normalized_url=f"https://example.edu/{path}",
        domain="example.edu",
        source_type=SourceType.OFFICIAL,
        source_owner_type=SourceOwnerType.INSTITUTION,
        officiality_status=OfficialityStatus.OFFICIAL,
        officiality_reason="fixture official source",
        robots_status="allowed",
        content_type="text/html",
        title="Inheritance evidence",
        relevant_excerpt=excerpt,
        verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        is_active=True,
    )
    db_session.add(source)
    db_session.flush()
    snapshot = SourceSnapshot(
        source_id=source.id,
        http_status=200,
        content_hash=uuid.uuid4().hex,
        normalized_text=excerpt,
        extraction_method="http_text",
        language_code="en",
        byte_count=len(excerpt.encode()),
        character_count=len(excerpt),
        fetch_metadata={},
    )
    db_session.add(snapshot)
    db_session.flush()
    EvidenceStore(db_session).add_field_evidence(
        entity_type="scoped_deadline",
        entity_id=fact.id,
        field_path="deadline_at",
        source_snapshot_id=snapshot.id,
        excerpt=excerpt,
        excerpt_start=0,
        excerpt_end=len(excerpt),
        support_type=EvidenceSupportType.EXPLICIT,
        validator_status=EvidenceValidatorStatus.PASSED,
    )
    db_session.commit()


def test_programme_fact_outranks_institution_track_fact(db_session: Session) -> None:
    scholarship = _scholarship(db_session)
    cycle, track, institution, programme = _scope(db_session, scholarship)
    institution_track_deadline = ScopedDeadline(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        track_id=track.id,
        institution_id=institution.id,
        deadline_type="application",
        deadline_at=datetime(2027, 6, 30, tzinfo=UTC),
        timezone="Asia/Shanghai",
        label="Institution and track deadline",
    )
    programme_deadline = ScopedDeadline(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        institution_id=institution.id,
        programme_id=programme.id,
        deadline_type="application",
        deadline_at=datetime(2027, 6, 20, tzinfo=UTC),
        timezone="Asia/Shanghai",
        label="Programme deadline",
    )
    db_session.add_all([institution_track_deadline, programme_deadline])
    db_session.commit()
    _explicit_evidence(
        db_session,
        scholarship,
        institution_track_deadline,
        "Institution route applications close on 30 June 2027.",
    )
    _explicit_evidence(
        db_session,
        scholarship,
        programme_deadline,
        "Programme applications close on 20 June 2027.",
    )

    resolution = resolve_scoped_deadline(
        db_session,
        scholarship_id=scholarship.id,
        deadline_type="application",
        scope=FactScope(
            cycle_id=cycle.id,
            track_id=track.id,
            institution_id=institution.id,
            programme_id=programme.id,
        ),
    )

    assert resolution.conflict is False
    assert resolution.fact_id == programme_deadline.id
    assert resolution.scope_level == "programme"
