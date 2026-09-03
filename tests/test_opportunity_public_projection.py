import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.evidence import EvidenceStore
from app.modules.opportunities.evidence_models import (
    ApplicationStep,
    EvidenceSupportType,
    EvidenceValidatorStatus,
    FundingComponent,
    RequiredDocument,
    ScopedDeadline,
    SourceSnapshot,
)
from app.modules.opportunities.graph_models import ApplicationTrack
from app.modules.opportunities.materialization_models import (
    OpportunityEvent,
    OpportunityResource,
    ScholarshipEligibilityRule,
    ScholarshipProgramme,
)
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
from app.modules.opportunities.public_projection import (
    build_decision_summary,
    build_public_projection,
)


def _source_snapshot(
    db_session: Session,
    opportunity: Opportunity,
    *,
    status: VerificationStatus,
    text: str,
) -> SourceSnapshot:
    suffix = uuid.uuid4().hex
    source = Source(
        opportunity_id=opportunity.id,
        url=f"https://official.example/{suffix}",
        canonical_url=f"https://official.example/{suffix}",
        normalized_url=f"https://official.example/{suffix}",
        domain="official.example",
        source_type=SourceType.OFFICIAL,
        title=f"Official source {suffix[:8]}",
        relevant_excerpt=text,
        verification_status=status,
        last_verified_at=datetime(2026, 9, 1, tzinfo=UTC),
        is_active=True,
    )
    db_session.add(source)
    db_session.flush()
    snapshot = SourceSnapshot(
        source_id=source.id,
        http_status=200,
        content_hash=(suffix * 2)[:64],
        normalized_text=text,
        extraction_method="http_text",
        language_code="en",
        byte_count=len(text.encode()),
        character_count=len(text),
        fetch_metadata={},
    )
    db_session.add(snapshot)
    db_session.flush()
    return snapshot


def _add_evidence(
    db_session: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    field_path: str,
    snapshot: SourceSnapshot,
    excerpt: str,
) -> None:
    start = snapshot.normalized_text.index(excerpt)
    EvidenceStore(db_session).add_field_evidence(
        entity_type=entity_type,
        entity_id=entity_id,
        field_path=field_path,
        source_snapshot_id=snapshot.id,
        excerpt=excerpt,
        excerpt_start=start,
        excerpt_end=start + len(excerpt),
        support_type=EvidenceSupportType.EXPLICIT,
        validator_status=EvidenceValidatorStatus.PASSED,
    )


def _reviewed_graph_fixture(db_session: Session) -> tuple[Opportunity, Source]:
    provider = Provider(name=f"Projection provider {uuid.uuid4()}")
    db_session.add(provider)
    db_session.flush()
    opportunity = Opportunity(
        provider_id=provider.id,
        name="Evidence Scholarship",
        canonical_slug=f"evidence-scholarship-{uuid.uuid4().hex}",
        country="Malaysia",
        degree_level=DegreeLevel.MASTERS,
        degree_levels=[DegreeLevel.MASTERS.value],
        funding_type=FundingType.FULL,
        status=OpportunityStatus.ACTIVE,
        data_confidence=DataConfidence.HIGH,
        required_documents=[],
        eligibility_warnings=[],
    )
    db_session.add(opportunity)
    db_session.flush()

    old_cycle = OpportunityCycle(
        opportunity_id=opportunity.id,
        label="2026",
        intake_year=2026,
        is_current=False,
        is_archived=True,
        timezone="UTC",
    )
    current_cycle = OpportunityCycle(
        opportunity_id=opportunity.id,
        label="2027",
        intake_year=2027,
        application_deadline=datetime(2027, 6, 1, tzinfo=UTC),
        is_current=True,
        is_archived=False,
        timezone="UTC",
    )
    later_non_current_cycle = OpportunityCycle(
        opportunity_id=opportunity.id,
        label="2028",
        intake_year=2028,
        application_deadline=datetime(2028, 6, 1, tzinfo=UTC),
        is_current=False,
        is_archived=False,
        timezone="UTC",
    )
    db_session.add_all([old_cycle, current_cycle, later_non_current_cycle])
    db_session.flush()
    opportunity.current_cycle_id = current_cycle.id

    track = ApplicationTrack(
        scholarship_id=opportunity.id,
        cycle_id=current_cycle.id,
        code="embassy",
        name="Embassy route",
        track_type="embassy",
        application_url="https://unsupported.example/apply",
        display_order=1,
    )
    unverified_track = ApplicationTrack(
        scholarship_id=opportunity.id,
        cycle_id=current_cycle.id,
        code="unverified",
        name="Unverified route",
        track_type="direct",
        display_order=2,
    )
    old_track = ApplicationTrack(
        scholarship_id=opportunity.id,
        cycle_id=old_cycle.id,
        code="old",
        name="Old route",
        track_type="direct",
        display_order=0,
    )
    db_session.add_all([track, unverified_track, old_track])
    db_session.flush()

    programme = ScholarshipProgramme(
        scholarship_id=opportunity.id,
        cycle_id=current_cycle.id,
        track_id=track.id,
        identity_key=uuid.uuid4().hex,
        programme_key="data-science",
        name="Data Science",
        degree_levels=[DegreeLevel.MASTERS.value],
        fields_of_study=["data-science"],
    )
    db_session.add(programme)
    db_session.flush()

    eligibility = ScholarshipEligibilityRule(
        scholarship_id=opportunity.id,
        cycle_id=current_cycle.id,
        track_id=track.id,
        programme_id=programme.id,
        identity_key=uuid.uuid4().hex,
        rule_key="pakistan-citizens",
        rule_type="nationality",
        operator="in",
        value_json={"value": ["PK"]},
        original_text="Citizens of Pakistan may apply",
    )
    deadline = ScopedDeadline(
        scholarship_id=opportunity.id,
        cycle_id=current_cycle.id,
        track_id=track.id,
        scholarship_programme_id=programme.id,
        deadline_type="application",
        deadline_at=datetime(2027, 6, 1, tzinfo=UTC),
        timezone="UTC",
        label="Application deadline",
    )
    funding = FundingComponent(
        scholarship_id=opportunity.id,
        component_type="tuition",
        coverage_status="full",
        description="Full tuition coverage",
    )
    unsupported_document = RequiredDocument(
        scholarship_id=opportunity.id,
        cycle_id=current_cycle.id,
        document_key="passport",
        name="Passport",
        required=True,
    )
    step = ApplicationStep(
        scholarship_id=opportunity.id,
        cycle_id=current_cycle.id,
        track_id=track.id,
        step_code="submit",
        title="Submit online",
    )
    event = OpportunityEvent(
        scholarship_id=opportunity.id,
        cycle_id=current_cycle.id,
        identity_key=uuid.uuid4().hex,
        event_key="interview",
        event_type="interview",
        label="Interview window",
    )
    resource = OpportunityResource(
        scholarship_id=opportunity.id,
        cycle_id=current_cycle.id,
        identity_key=uuid.uuid4().hex,
        resource_key="portal",
        title="Official portal",
        resource_type="application_portal",
        url="https://official.example/apply",
    )
    db_session.add_all(
        [eligibility, deadline, funding, unsupported_document, step, event, resource]
    )
    db_session.flush()

    reviewed_text = (
        "2027 intake. Embassy route. Data Science. Citizens of Pakistan may apply. "
        "Applications close 1 June 2027. Full tuition coverage. Submit online. "
        "Interview window. Official portal."
    )
    reviewed_snapshot = _source_snapshot(
        db_session,
        opportunity,
        status=VerificationStatus.OFFICIALLY_VERIFIED,
        text=reviewed_text,
    )
    unverified_snapshot = _source_snapshot(
        db_session,
        opportunity,
        status=VerificationStatus.NEEDS_REVIEW,
        text="Unverified route. Old route.",
    )
    reviewed_source = db_session.get(Source, reviewed_snapshot.source_id)
    assert reviewed_source is not None

    for entity_type, entity, field_path, excerpt in [
        ("cycle", current_cycle, "intake_year", "2027 intake"),
        ("track", track, "name", "Embassy route"),
        ("programme", programme, "name", "Data Science"),
        ("eligibility", eligibility, "original_text", "Citizens of Pakistan may apply"),
        ("deadline", deadline, "deadline_at", "Applications close 1 June 2027"),
        ("funding", funding, "component_type", "Full tuition coverage"),
        ("funding", funding, "coverage_status", "Full tuition coverage"),
        ("step", step, "title", "Submit online"),
        ("event", event, "label", "Interview window"),
        ("resource", resource, "title", "Official portal"),
    ]:
        _add_evidence(
            db_session,
            entity_type=entity_type,
            entity_id=entity.id,
            field_path=field_path,
            snapshot=reviewed_snapshot,
            excerpt=excerpt,
        )
    _add_evidence(
        db_session,
        entity_type="track",
        entity_id=unverified_track.id,
        field_path="name",
        snapshot=unverified_snapshot,
        excerpt="Unverified route",
    )
    _add_evidence(
        db_session,
        entity_type="track",
        entity_id=old_track.id,
        field_path="name",
        snapshot=unverified_snapshot,
        excerpt="Old route",
    )
    db_session.commit()
    return opportunity, reviewed_source


def test_public_projection_preserves_scope_and_excludes_unverified_claims(
    db_session: Session,
) -> None:
    opportunity, reviewed_source = _reviewed_graph_fixture(db_session)

    projection = build_public_projection(db_session, opportunity)

    assert projection.cycle is not None
    assert projection.cycle.intake_year == 2027
    assert [item.name for item in projection.tracks] == ["Embassy route"]
    assert projection.tracks[0].scope.track_id == projection.tracks[0].id
    assert projection.tracks[0].application_url is None
    assert projection.programmes[0].scope.programme_id == projection.programmes[0].id
    assert projection.eligibility[0].scope.programme_id == projection.programmes[0].id
    assert projection.funding[0].scope.cycle_id is None
    assert projection.deadlines[0].scope.track_id == projection.tracks[0].id
    assert projection.steps[0].title == "Submit online"
    assert projection.events[0].label == "Interview window"
    assert projection.resources[0].title == "Official portal"
    assert projection.documents == []
    assert projection.known_unknowns == ["documents"]
    assert projection.evidence
    assert {item.verification_status for item in projection.evidence} == {
        VerificationStatus.OFFICIALLY_VERIFIED
    }
    assert {str(item.source_url) for item in projection.evidence} == {reviewed_source.url}
    assert all(item.field_path for item in projection.evidence)


def test_disqualifying_official_source_suppresses_public_projection(
    db_session: Session,
) -> None:
    opportunity, _ = _reviewed_graph_fixture(db_session)
    db_session.add(
        Source(
            opportunity_id=opportunity.id,
            url="https://official.example/conflict",
            canonical_url="https://official.example/conflict",
            normalized_url="https://official.example/conflict",
            domain="official.example",
            source_type=SourceType.OFFICIAL,
            title="Conflicting official source",
            relevant_excerpt="A conflicting official statement.",
            verification_status=VerificationStatus.CONFLICTING_INFORMATION,
            is_active=True,
        )
    )
    db_session.commit()

    projection = build_public_projection(db_session, opportunity)

    assert projection.cycle is None
    assert projection.tracks == []
    assert projection.evidence == []
    assert "cycle" in projection.known_unknowns


def test_projection_requires_passed_explicit_field_evidence(db_session: Session) -> None:
    opportunity, _ = _reviewed_graph_fixture(db_session)
    cycle_id = opportunity.current_cycle_id
    assert cycle_id is not None
    snapshot = _source_snapshot(
        db_session,
        opportunity,
        status=VerificationStatus.OFFICIALLY_VERIFIED,
        text="Pending route. Partial route.",
    )
    pending_track = ApplicationTrack(
        scholarship_id=opportunity.id,
        cycle_id=cycle_id,
        code="pending",
        name="Pending route",
        track_type="direct",
    )
    partial_track = ApplicationTrack(
        scholarship_id=opportunity.id,
        cycle_id=cycle_id,
        code="partial",
        name="Partial route",
        track_type="direct",
    )
    db_session.add_all([pending_track, partial_track])
    db_session.flush()
    for track, support_type, validator_status in [
        (
            pending_track,
            EvidenceSupportType.EXPLICIT,
            EvidenceValidatorStatus.PENDING,
        ),
        (
            partial_track,
            EvidenceSupportType.PARTIAL,
            EvidenceValidatorStatus.PASSED,
        ),
    ]:
        excerpt = track.name
        start = snapshot.normalized_text.index(excerpt)
        EvidenceStore(db_session).add_field_evidence(
            entity_type="track",
            entity_id=track.id,
            field_path="name",
            source_snapshot_id=snapshot.id,
            excerpt=excerpt,
            excerpt_start=start,
            excerpt_end=start + len(excerpt),
            support_type=support_type,
            validator_status=validator_status,
        )
    db_session.commit()

    projection = build_public_projection(db_session, opportunity)

    assert [item.code for item in projection.tracks] == ["embassy"]


def test_decision_summary_uses_only_confirmed_projection_values(
    db_session: Session,
) -> None:
    opportunity, _ = _reviewed_graph_fixture(db_session)
    projection = build_public_projection(db_session, opportunity)

    summary = build_decision_summary(opportunity, projection)

    assert projection.summary == summary
    assert summary.overview.state == "confirmed"
    assert summary.overview.evidence_ids
    assert "2027" in summary.overview.text
    assert "guaranteed" not in summary.overview.text.casefold()
    assert summary.funding.state == "confirmed"
    assert "tuition" in summary.funding.text.casefold()
    assert summary.eligibility.state == "confirmed"
    assert "pakistan" in summary.eligibility.text.casefold()
    assert "data science programme" in summary.eligibility.text.casefold()
    assert summary.application_route.state == "confirmed"
    assert "embassy route" in summary.application_route.text.casefold()
    projection_evidence_ids = {item.id for item in projection.evidence}
    for block in (
        summary.overview,
        summary.funding,
        summary.eligibility,
        summary.application_route,
    ):
        assert set(block.evidence_ids) <= projection_evidence_ids


def test_decision_summary_marks_missing_funding_as_unknown(db_session: Session) -> None:
    opportunity, _ = _reviewed_graph_fixture(db_session)
    projection = build_public_projection(db_session, opportunity).model_copy(update={"funding": []})

    summary = build_decision_summary(opportunity, projection)

    assert summary.funding.state == "unknown"
    assert summary.funding.evidence_ids == []
    assert summary.funding.text == ("Funding coverage is not confirmed in the reviewed sources.")


def test_decision_summary_preserves_explicit_not_applicable_state(
    db_session: Session,
) -> None:
    opportunity, _ = _reviewed_graph_fixture(db_session)
    projection = build_public_projection(db_session, opportunity)
    not_applicable_funding = projection.funding[0].model_copy(
        update={"coverage_status": "not_applicable"}
    )
    projection = projection.model_copy(update={"funding": [not_applicable_funding]})

    summary = build_decision_summary(opportunity, projection)

    assert summary.funding.state == "not_applicable"
    assert set(summary.funding.evidence_ids) == set(not_applicable_funding.evidence_ids)
    assert "explicitly marked as not applicable" in summary.funding.text


def test_decision_summary_marks_conflicting_sources_without_repeating_claims(
    db_session: Session,
) -> None:
    opportunity, _ = _reviewed_graph_fixture(db_session)
    db_session.add(
        Source(
            opportunity_id=opportunity.id,
            url="https://official.example/summary-conflict",
            canonical_url="https://official.example/summary-conflict",
            normalized_url="https://official.example/summary-conflict",
            domain="official.example",
            source_type=SourceType.OFFICIAL,
            title="Conflicting summary source",
            relevant_excerpt="A conflicting official statement.",
            verification_status=VerificationStatus.CONFLICTING_INFORMATION,
            is_active=True,
        )
    )
    db_session.commit()
    projection = build_public_projection(db_session, opportunity)

    summary = build_decision_summary(opportunity, projection)

    assert {
        block.state
        for block in (
            summary.overview,
            summary.funding,
            summary.eligibility,
            summary.application_route,
        )
    } == {"conflicting"}
    assert all(
        not block.evidence_ids
        for block in (
            summary.overview,
            summary.funding,
            summary.eligibility,
            summary.application_route,
        )
    )


def test_decision_summary_marks_confirmed_but_old_facts_as_stale(
    db_session: Session,
) -> None:
    opportunity, reviewed_source = _reviewed_graph_fixture(db_session)
    reviewed_source.last_verified_at = datetime(2020, 1, 1, tzinfo=UTC)
    db_session.commit()

    projection = build_public_projection(db_session, opportunity)
    summary = build_decision_summary(opportunity, projection)

    assert {
        block.state
        for block in (
            summary.overview,
            summary.funding,
            summary.eligibility,
            summary.application_route,
        )
    } == {"stale"}
    assert all(
        block.evidence_ids
        for block in (
            summary.overview,
            summary.funding,
            summary.eligibility,
            summary.application_route,
        )
    )


def test_decision_summary_marks_expired_projection_as_stale(db_session: Session) -> None:
    opportunity, _ = _reviewed_graph_fixture(db_session)
    db_session.add(
        Source(
            opportunity_id=opportunity.id,
            url="https://official.example/expired-summary",
            canonical_url="https://official.example/expired-summary",
            normalized_url="https://official.example/expired-summary",
            domain="official.example",
            source_type=SourceType.OFFICIAL,
            title="Expired official source",
            relevant_excerpt="This official notice has expired.",
            verification_status=VerificationStatus.EXPIRED,
            is_active=True,
        )
    )
    db_session.commit()

    projection = build_public_projection(db_session, opportunity)

    assert projection.evidence == []
    assert projection.summary is not None
    assert {
        block.state
        for block in (
            projection.summary.overview,
            projection.summary.funding,
            projection.summary.eligibility,
            projection.summary.application_route,
        )
    } == {"stale"}
