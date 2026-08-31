"""Comprehensive unit test suite for the 6 Launch MVP Modules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.applications.watchdog import (
    AlertUrgency,
    evaluate_deadline_alert,
    generate_watchdog_digest,
)
from app.modules.matching.exporter import build_match_strategy_report
from app.modules.opportunities.calendar import (
    generate_google_calendar_url,
    generate_opportunity_ics,
)
from app.modules.opportunities.checklist import build_opportunity_checklist
from app.modules.opportunities.comparator import build_funding_comparison
from app.modules.opportunities.directory import (
    build_directory_card,
    generate_schema_org_json_ld,
)
from app.modules.opportunities.evidence_models import (
    FundingComponent,
    RequiredDocument,
)
from app.modules.opportunities.materialization_models import OpportunityEvent
from app.modules.opportunities.models import (
    ApplicationFeeStatus,
    DegreeLevel,
    FundingType,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    Provider,
)
from app.modules.profiles.models import StudentProfile, TargetDegreeLevel


def _sample_opportunity(
    *,
    name: str = "Chevening Scholarship",
    country: str = "United Kingdom",
    funding_type: FundingType = FundingType.FULL,
    degree_level: DegreeLevel = DegreeLevel.MASTERS,
) -> Opportunity:
    opp_id = uuid.uuid4()
    prov_id = uuid.uuid4()
    opp = Opportunity(
        id=opp_id,
        provider_id=prov_id,
        name=name,
        programme_family_id="chevening",
        cycle_id="2027",
        country=country,
        degree_level=degree_level,
        intake_year=2027,
        funding_type=funding_type,
        status=OpportunityStatus.ACTIVE,
        application_fee_status=ApplicationFeeStatus.NOT_REQUIRED,
    )
    provider = Provider(
        id=prov_id,
        name="UK Foreign, Commonwealth & Development Office",
        canonical_id="fcdo",
    )
    opp.provider = provider
    return opp


# ==============================================================================
# TEST 1: RFC 5545 .ICS CALENDAR & GOOGLE URL GENERATOR
# ==============================================================================


def test_calendar_ics_and_google_links() -> None:
    opp = _sample_opportunity()
    deadline_dt = datetime(2027, 11, 5, 12, 0, tzinfo=UTC)
    cycle = OpportunityCycle(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        label="2027",
        intake_year=2027,
        is_current=True,
        application_deadline=deadline_dt,
    )
    event = OpportunityEvent(
        id=uuid.uuid4(),
        scholarship_id=opp.id,
        cycle_id=cycle.id,
        identity_key=f"event-{opp.id}",
        event_key="interview_stage",
        event_type="interview",
        starts_at=datetime(2028, 2, 1, 9, 0, tzinfo=UTC),
        ends_at=datetime(2028, 2, 1, 10, 0, tzinfo=UTC),
        label="Embassy Interview",
    )

    ics_content = generate_opportunity_ics(opp, cycle=cycle, events=[event])

    assert "BEGIN:VCALENDAR" in ics_content
    assert "END:VCALENDAR" in ics_content
    assert "DEADLINE: Chevening Scholarship (2027)" in ics_content
    assert "20271105T120000Z" in ics_content
    assert "Embassy Interview" in ics_content
    assert "BEGIN:VALARM" in ics_content

    google_url = generate_google_calendar_url(
        title=f"DEADLINE: {opp.name}",
        start_dt=deadline_dt,
        end_dt=deadline_dt,
        details="Chevening Application Deadline",
        location=opp.country,
    )
    assert "calendar.google.com/calendar/render" in google_url
    assert "action=TEMPLATE" in google_url
    assert "Chevening" in google_url


# ==============================================================================
# TEST 2: INTERACTIVE DOCUMENT CHECKLIST & READINESS SCORE
# ==============================================================================


def test_document_checklist_and_readiness_scoring() -> None:
    opp = _sample_opportunity()
    docs = [
        RequiredDocument(
            id=uuid.uuid4(),
            scholarship_id=opp.id,
            document_key="transcripts",
            name="Official Academic Transcript",
            required=True,
            original_count=1,
            copy_count=2,
            translation_requirement="Certified English translation required",
        ),
        RequiredDocument(
            id=uuid.uuid4(),
            scholarship_id=opp.id,
            document_key="recommendation_letters",
            name="Letters of Recommendation",
            required=True,
            original_count=2,
        ),
        RequiredDocument(
            id=uuid.uuid4(),
            scholarship_id=opp.id,
            document_key="portfolio",
            name="Creative Portfolio",
            required=False,
        ),
    ]

    # Case A: 0 items completed (0%)
    res_0 = build_opportunity_checklist(opp, docs, completed_keys=set())
    assert res_0.total_documents == 3
    assert res_0.required_count == 2
    assert res_0.completed_count == 0
    assert res_0.readiness_percentage == 0
    assert res_0.is_ready_for_submission is False
    assert len(res_0.critical_missing) == 2

    # Case B: 1 of 2 required items completed (50%)
    res_50 = build_opportunity_checklist(opp, docs, completed_keys={"transcripts"})
    assert res_50.completed_count == 1
    assert res_50.readiness_percentage == 50
    assert res_50.is_ready_for_submission is False
    assert res_50.critical_missing == ["Letters of Recommendation"]

    # Case C: All required items completed (100%)
    res_100 = build_opportunity_checklist(
        opp, docs, completed_keys={"transcripts", "recommendation_letters"}
    )
    assert res_100.completed_count == 2
    assert res_100.readiness_percentage == 100
    assert res_100.is_ready_for_submission is True
    assert len(res_100.critical_missing) == 0


# ==============================================================================
# TEST 3: SCHOLARSHIP BENEFITS & FUNDING COMPARATOR
# ==============================================================================


def test_scholarship_funding_comparator() -> None:
    opp1 = _sample_opportunity(name="Chevening UK", country="United Kingdom")
    comp1 = [
        FundingComponent(
            id=uuid.uuid4(),
            scholarship_id=opp1.id,
            component_type="tuition",
            coverage_status="full",
            amount=None,
            description="100% Full University Tuition Fees",
        ),
        FundingComponent(
            id=uuid.uuid4(),
            scholarship_id=opp1.id,
            component_type="stipend",
            coverage_status="full",
            amount=Decimal("1400"),
            currency="GBP",
            frequency="month",
        ),
        FundingComponent(
            id=uuid.uuid4(),
            scholarship_id=opp1.id,
            component_type="travel",
            coverage_status="full",
            description="Return flights",
        ),
    ]

    opp2 = _sample_opportunity(name="MEXT Japan", country="Japan")
    comp2 = [
        FundingComponent(
            id=uuid.uuid4(),
            scholarship_id=opp2.id,
            component_type="stipend",
            coverage_status="full",
            amount=Decimal("144000"),
            currency="JPY",
            frequency="month",
        ),
    ]

    res = build_funding_comparison([(opp1, comp1), (opp2, comp2)])

    assert res.total_compared == 2
    assert len(res.scholarships) == 2
    # Check currency conversion and monthly stipend display
    chev_card = next(c for c in res.scholarships if c.opportunity_id == str(opp1.id))
    assert "GBP 1,400 / month" in chev_card.monthly_stipend_text
    assert chev_card.monthly_stipend_usd > 1500  # 1400 * 1.28 ~ 1792 USD
    assert chev_card.travel_airfare_covered is True
    assert chev_card.total_estimated_annual_value_usd > 35_000


# ==============================================================================
# TEST 4: PERSONALIZED MATCH STRATEGY REPORT EXPORTER
# ==============================================================================


def test_match_strategy_report_exporter() -> None:
    profile = StudentProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        nationality="PK",
        target_degree_level=TargetDegreeLevel.MASTERS,
        intended_field="Computer Science",
        cgpa=Decimal("3.8"),
        grading_scale=Decimal("4.0"),
    )

    from app.modules.matching.schemas import MatchExplanation, OpportunityMatchResponse
    from app.modules.opportunities.models import (
        ApplicationWindowState,
        FundingClassification,
        VerificationStatus,
    )
    from app.modules.opportunities.schemas import OpportunitySummaryResponse

    opp = _sample_opportunity()
    from app.modules.opportunities.schemas import (
        CatalogueDecisionTier,
        VerificationFreshness,
    )

    summary = OpportunitySummaryResponse(
        id=opp.id,
        name=opp.name,
        provider_name=opp.provider.name,
        university_name=None,
        country=opp.country or "United Kingdom",
        degree_level=opp.degree_level,
        degree_levels=[opp.degree_level],
        application_deadline=datetime(2027, 11, 5, tzinfo=UTC),
        funding_type=opp.funding_type,
        funding_classification=FundingClassification.FULLY_FUNDED,
        funding_summary="Fully funded scholarship",
        verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        last_verified_at=datetime.now(UTC),
        official_source_url="https://chevening.org",
        application_window_state=ApplicationWindowState.OPEN,
        source_is_fresh=True,
        verification_freshness=VerificationFreshness.RECENT,
        funding_display_label="Fully Funded",
        catalogue_decision_tier=CatalogueDecisionTier.DECISION_READY,
        structured_eligibility_complete=True,
    )

    match_item = OpportunityMatchResponse(
        opportunity=summary,
        match_score=95,
        score_label="Excellent Match",
        fit_band="Tier 1",
        display_label="95% Match",
        eligibility_status="eligible",
        fit_score=95,
        evidence_completeness=100,
        profile_completeness=100,
        confidence="high",
        failed_criteria=[],
        unknown_criteria=[],
        warnings=[],
        matcher_version="v2",
        evaluated_at=datetime.now(UTC),
        explanation=MatchExplanation(
            satisfied=["Direct match on field: 'computer science'"],
            missing=[],
            uncertain=[],
            next_steps=["Submit transcript", "Apply online"],
        ),
    )

    report = build_match_strategy_report(profile, [match_item])

    assert report.total_matches_found == 1
    assert report.top_tier_matches_count == 1
    assert report.student_profile["cgpa"] == "3.80"
    assert report.student_profile["target_degree"] == "MASTERS"
    assert len(report.top_matches) == 1
    assert report.top_matches[0].fit_score_percentage == 95
    assert len(report.immediate_action_items) >= 3


# ==============================================================================
# TEST 5: DEADLINE WATCHDOG ALERT ENGINE
# ==============================================================================


def test_deadline_watchdog_triggers() -> None:
    ref_time = datetime(2027, 10, 1, 12, 0, tzinfo=UTC)

    # 1. 2 days away -> CRITICAL
    alert_2d = evaluate_deadline_alert(
        user_id="user-1",
        user_email="student@example.com",
        opportunity_id="opp-1",
        opportunity_name="Fulbright USA",
        country="United States",
        deadline_at=ref_time + timedelta(days=2),
        reference_dt=ref_time,
    )
    assert alert_2d is not None
    assert alert_2d.urgency == AlertUrgency.CRITICAL
    assert alert_2d.days_remaining == 2
    assert "2 days left" in alert_2d.subject_line

    # 2. 7 days away -> HIGH
    alert_7d = evaluate_deadline_alert(
        user_id="user-2",
        user_email="student2@example.com",
        opportunity_id="opp-2",
        opportunity_name="DAAD Germany",
        country="Germany",
        deadline_at=ref_time + timedelta(days=7),
        reference_dt=ref_time,
    )
    assert alert_7d is not None
    assert alert_7d.urgency == AlertUrgency.HIGH
    assert alert_7d.days_remaining == 7

    # 3. 45 days away -> None (too early)
    alert_45d = evaluate_deadline_alert(
        user_id="user-3",
        user_email="student3@example.com",
        opportunity_id="opp-3",
        opportunity_name="Turkiye Burslari",
        country="Turkey",
        deadline_at=ref_time + timedelta(days=45),
        reference_dt=ref_time,
    )
    assert alert_45d is None

    # 4. Digest aggregation
    digest = generate_watchdog_digest(
        [
            {
                "user_id": "u1",
                "user_email": "a@test.com",
                "opportunity_id": "o1",
                "opportunity_name": "Fulbright",
                "country": "US",
                "deadline_at": ref_time + timedelta(days=2),
            },
            {
                "user_id": "u2",
                "user_email": "b@test.com",
                "opportunity_id": "o2",
                "opportunity_name": "DAAD",
                "country": "DE",
                "deadline_at": ref_time + timedelta(days=7),
            },
        ],
        reference_dt=ref_time,
    )
    assert digest.total_alerts_generated == 2
    assert digest.critical_alerts_count == 1
    assert digest.high_alerts_count == 1


# ==============================================================================
# TEST 6: PUBLIC DIRECTORY & SCHEMA.ORG JSON-LD SEO GENERATOR
# ==============================================================================


def test_directory_and_schema_org_json_ld() -> None:
    opp = _sample_opportunity(name="Eiffel Excellence Scholarship", country="France")
    schema_ld = generate_schema_org_json_ld(opp, base_url="https://scholarshipai.app")

    assert schema_ld["@context"] == "https://schema.org"
    assert schema_ld["@type"] == "FinancialAid"
    assert schema_ld["name"] == "Eiffel Excellence Scholarship"
    assert schema_ld["areaServed"] == "France"
    assert "scholarshipai.app/scholarships/france/eiffel-excellence-scholarship" in schema_ld["url"]

    card = build_directory_card(opp, base_url="https://scholarshipai.app")
    assert card.slug == "eiffel-excellence-scholarship"
    assert card.country == "France"
    assert card.is_open is True
    assert card.schema_org_json_ld["@type"] == "FinancialAid"
