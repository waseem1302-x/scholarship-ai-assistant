import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.opportunities.graph_models import (
    AcademicProgramme,
    ApplicationTrack,
    Institution,
    InstitutionParticipation,
    ScholarshipAlias,
    TrackProgramme,
)
from app.modules.opportunities.models import (
    DataConfidence,
    DegreeLevel,
    FundingType,
    IndependenceStatus,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    Provider,
)


def create_scholarship(
    db_session: Session,
    *,
    name: str = "Chinese Government Scholarship",
    canonical_slug: str = "csc",
) -> Opportunity:
    provider = Provider(name=f"Graph test provider {uuid.uuid4()}")
    db_session.add(provider)
    db_session.flush()
    scholarship = Opportunity(
        provider_id=provider.id,
        name=name,
        canonical_slug=canonical_slug,
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


def test_opportunity_remains_the_canonical_scholarship_identity(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)

    assert scholarship.entity_kind == "scholarship"
    assert scholarship.independence_status is IndependenceStatus.LEGACY_UNREVIEWED
    assert scholarship.publication_completeness == "incomplete"
    assert db_session.scalar(select(func.count()).select_from(Opportunity)) == 1


def test_graph_children_do_not_increase_scholarship_count(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    cycle = OpportunityCycle(
        opportunity_id=scholarship.id,
        label="2027/28",
        timezone="Asia/Shanghai",
        is_current=True,
    )
    institution = Institution(
        canonical_name="Reviewed structural test institution",
        slug="reviewed-structural-test-institution",
        institution_type="university",
        country_code="CN",
        identity_status="fixture_only",
    )
    db_session.add_all([cycle, institution])
    db_session.flush()

    track = ApplicationTrack(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        code="route-a",
        name="Reviewed structural test route",
        track_type="university",
        status="fixture_only",
    )
    programme = AcademicProgramme(
        institution_id=institution.id,
        canonical_name="Reviewed structural test programme",
        slug="reviewed-structural-test-programme",
        degree_level=DegreeLevel.MASTERS,
        field_codes=["computer-science"],
        active_status="fixture_only",
    )
    db_session.add_all([track, programme])
    db_session.flush()

    participation = InstitutionParticipation(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        track_id=track.id,
        institution_id=institution.id,
        role="designated_university",
        participation_status="fixture_only",
    )
    track_programme = TrackProgramme(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        track_id=track.id,
        institution_id=institution.id,
        programme_id=programme.id,
        eligibility_status="fixture_only",
        funding_status="fixture_only",
    )
    db_session.add_all([participation, track_programme])
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Opportunity)) == 1
    assert db_session.scalar(select(func.count()).select_from(ApplicationTrack)) == 1
    assert db_session.scalar(select(func.count()).select_from(InstitutionParticipation)) == 1
    assert db_session.scalar(select(func.count()).select_from(AcademicProgramme)) == 1


def test_canonical_slug_is_unique_when_present(db_session: Session) -> None:
    create_scholarship(db_session, canonical_slug="canonical-csc")

    with pytest.raises(IntegrityError):
        create_scholarship(
            db_session,
            name="Another draft using the same canonical identity",
            canonical_slug="canonical-csc",
        )


def test_only_one_current_cycle_is_allowed_per_scholarship(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    db_session.add_all(
        [
            OpportunityCycle(
                opportunity_id=scholarship.id,
                label="2027/28",
                timezone="UTC",
                is_current=True,
            ),
            OpportunityCycle(
                opportunity_id=scholarship.id,
                label="2028/29",
                timezone="UTC",
                is_current=True,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_track_code_is_unique_within_cycle(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    cycle = OpportunityCycle(
        opportunity_id=scholarship.id,
        label="2027/28",
        timezone="UTC",
    )
    db_session.add(cycle)
    db_session.flush()
    db_session.add_all(
        [
            ApplicationTrack(
                scholarship_id=scholarship.id,
                cycle_id=cycle.id,
                code="type-a",
                name="Type A",
                track_type="government_portal",
            ),
            ApplicationTrack(
                scholarship_id=scholarship.id,
                cycle_id=cycle.id,
                code="type-a",
                name="Duplicate Type A",
                track_type="government_portal",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_participation_and_programme_links_are_unique(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    cycle = OpportunityCycle(opportunity_id=scholarship.id, label="2027/28", timezone="UTC")
    institution = Institution(
        canonical_name="Graph uniqueness institution",
        slug="graph-uniqueness-institution",
        institution_type="university",
        identity_status="fixture_only",
    )
    db_session.add_all([cycle, institution])
    db_session.flush()
    track = ApplicationTrack(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        code="route-a",
        name="Route A",
        track_type="university",
    )
    programme = AcademicProgramme(
        institution_id=institution.id,
        canonical_name="Programme A",
        slug="programme-a",
        field_codes=[],
    )
    db_session.add_all([track, programme])
    db_session.flush()

    first = InstitutionParticipation(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        track_id=track.id,
        institution_id=institution.id,
        role="host",
    )
    duplicate = InstitutionParticipation(
        scholarship_id=scholarship.id,
        cycle_id=cycle.id,
        track_id=track.id,
        institution_id=institution.id,
        role="host",
    )
    db_session.add_all([first, duplicate])
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        TrackProgramme(
            scholarship_id=scholarship.id,
            cycle_id=cycle.id,
            track_id=track.id,
            institution_id=institution.id,
            programme_id=programme.id,
        )
    )
    db_session.commit()
    db_session.add(
        TrackProgramme(
            scholarship_id=scholarship.id,
            cycle_id=cycle.id,
            track_id=track.id,
            institution_id=institution.id,
            programme_id=programme.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_self_parent_and_duplicate_alias_are_rejected(db_session: Session) -> None:
    scholarship = create_scholarship(db_session)
    scholarship.parent_scholarship_id = scholarship.id
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    scholarship = db_session.get(Opportunity, scholarship.id)
    assert scholarship is not None
    scholarship.parent_scholarship_id = None
    db_session.add_all(
        [
            ScholarshipAlias(
                scholarship_id=scholarship.id,
                alias="CSC",
                normalized_alias="csc",
            ),
            ScholarshipAlias(
                scholarship_id=scholarship.id,
                alias="C.S.C.",
                normalized_alias="csc",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
