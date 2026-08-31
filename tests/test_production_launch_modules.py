"""Comprehensive unit test suite for the 6 Production Launch Enhancement Modules."""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.applications.models import (
    Application,
    ApplicationLifecycle,
)
from app.modules.applications.pipeline import (
    KanbanLaneName,
    build_pipeline_summary,
)
from app.modules.matching.guest_matcher import (
    GuestMatchRequest,
    evaluate_guest_matches,
)
from app.modules.opportunities.cycle_rollover import (
    determine_cycle_state,
)
from app.modules.opportunities.models import (
    ApplicationFeeStatus,
    ApplicationWindowState,
    DegreeLevel,
    FundingType,
    Opportunity,
    OpportunityStatus,
    Provider,
)
from app.modules.opportunities.sitemap import (
    generate_robots_txt,
    generate_sitemap_xml,
)
from app.modules.opportunities.telemetry import (
    get_trending_scholarships,
    track_outbound_apply_click,
)
from app.modules.profiles.models import (
    StudentProfile,
    TargetDegreeLevel,
    TestStatus,
)
from app.modules.profiles.strength import (
    evaluate_profile_strength,
)


def _sample_opportunity(
    *,
    name: str = "DAAD Scholarship",
    country: str = "Germany",
    funding_type: FundingType = FundingType.FULL,
    degree_level: DegreeLevel = DegreeLevel.MASTERS,
    deadline_dt: datetime | None = None,
) -> Opportunity:
    opp_id = uuid.uuid4()
    prov_id = uuid.uuid4()
    opp = Opportunity(
        id=opp_id,
        provider_id=prov_id,
        name=name,
        programme_family_id="daad",
        cycle_id="2027",
        country=country,
        degree_level=degree_level,
        intake_year=2027,
        funding_type=funding_type,
        status=OpportunityStatus.ACTIVE,
        application_fee_status=ApplicationFeeStatus.NOT_REQUIRED,
        application_deadline=deadline_dt,
    )
    provider = Provider(
        id=prov_id,
        name=f"Provider {opp_id}",
        canonical_id=f"provider-{opp_id}",
    )
    opp.provider = provider
    return opp


# ==============================================================================
# TEST 1: DYNAMIC XML SITEMAP & ROBOTS.TXT (SEO ENGINE)
# ==============================================================================


def test_dynamic_sitemap_and_robots_txt(db_session) -> None:
    opp = _sample_opportunity(name="DAAD Master Study", country="Germany")
    db_session.add(opp.provider)
    db_session.add(opp)
    db_session.flush()

    # 1. Test Sitemap XML
    sitemap_xml = generate_sitemap_xml(db_session, base_url="https://scholarshipai.app")

    assert "<?xml version=" in sitemap_xml
    assert "<urlset" in sitemap_xml
    assert "https://scholarshipai.app/scholarships" in sitemap_xml
    assert "https://scholarshipai.app/scholarships/country/germany" in sitemap_xml
    assert "daad-master-study" in sitemap_xml

    # Verify XML parses without error
    root = ET.fromstring(sitemap_xml.split("?>", 1)[-1].strip())
    assert root.tag.endswith("urlset")
    urls = list(root)
    assert len(urls) >= 4  # Statics + country + opportunity

    # 2. Test Robots.txt
    robots_txt = generate_robots_txt(base_url="https://scholarshipai.app")
    assert "User-agent: *" in robots_txt
    assert "Allow: /scholarships" in robots_txt
    assert "Disallow: /admin" in robots_txt
    assert "Sitemap: https://scholarshipai.app/sitemap.xml" in robots_txt


# ==============================================================================
# TEST 2: GUEST / ANONYMOUS QUICK-MATCH ENGINE
# ==============================================================================


def test_guest_quick_match_engine(db_session) -> None:
    opp = _sample_opportunity(
        name="Turkiye Burslari", country="Turkey", degree_level=DegreeLevel.MASTERS
    )
    opp.field_eligibility = "engineering, computer science, medicine"
    db_session.add(opp.provider)
    db_session.add(opp)
    db_session.flush()

    req = GuestMatchRequest(
        nationality="Pakistan",
        target_degree_level=DegreeLevel.MASTERS,
        intended_field="Computer Science",
        cgpa=3.8,
        grading_scale=4.0,
    )

    res = evaluate_guest_matches(db_session, req)

    assert res.total_eligible_count >= 1
    assert res.estimated_total_funding_usd >= 30_000.0
    assert "Turkey" in res.unlocked_countries
    assert len(res.top_teaser_matches) >= 1
    assert res.top_teaser_matches[0].name == "Turkiye Burslari"
    assert res.top_teaser_matches[0].fit_percentage >= 80
    assert "10 seconds" in res.registration_cta_subheading


# ==============================================================================
# TEST 3: ANNUAL CYCLE AUTO-ROLLOVER & NEXT INTAKE ESTIMATIONS
# ==============================================================================


def test_annual_cycle_state_machine_and_rollover() -> None:
    ref_now = datetime(2027, 9, 1, 12, 0, tzinfo=UTC)

    # 1. Active open window (> 14 days)
    opp_open = _sample_opportunity(deadline_dt=ref_now + timedelta(days=45))
    state_open = determine_cycle_state(opp_open, reference_dt=ref_now)
    assert state_open.state == ApplicationWindowState.OPEN
    assert state_open.is_open is True
    assert state_open.days_remaining == 45
    assert "Open Now" in state_open.badge_label

    # 2. Closing soon (<= 14 days)
    opp_soon = _sample_opportunity(deadline_dt=ref_now + timedelta(days=5))
    state_soon = determine_cycle_state(opp_soon, reference_dt=ref_now)
    assert state_soon.state == ApplicationWindowState.OPEN
    assert state_soon.is_open is True
    assert state_soon.days_remaining == 5
    assert "Closing in 5d" in state_soon.badge_label

    # 3. Passed deadline -> Closed with Next Cycle Estimation
    opp_closed = _sample_opportunity(deadline_dt=ref_now - timedelta(days=10))
    state_closed = determine_cycle_state(opp_closed, reference_dt=ref_now)
    assert state_closed.state == ApplicationWindowState.CLOSED
    assert state_closed.is_open is False
    assert state_closed.days_remaining is None
    assert "Closed for 2027" in state_closed.badge_label
    assert state_closed.next_cycle_estimated_open is not None
    assert "2028 intake" in state_closed.next_cycle_estimated_open
    assert "Set a deadline alert" in state_closed.public_status_message


# ==============================================================================
# TEST 4: OUTBOUND APPLY CLICK TELEMETRY & POPULARITY RANKING
# ==============================================================================


def test_outbound_click_telemetry_and_trending(db_session) -> None:
    opp1 = _sample_opportunity(name="Chevening 1")
    opp2 = _sample_opportunity(name="DAAD 2")
    db_session.add(opp1.provider)
    db_session.add(opp1)
    db_session.add(opp2.provider)
    db_session.add(opp2)
    db_session.flush()

    # Track 3 clicks on Chevening and 1 on DAAD
    track_outbound_apply_click(opp1, user_agent="Mozilla/5.0")
    track_outbound_apply_click(opp1, user_agent="Mozilla/5.0")
    track_outbound_apply_click(opp1, user_agent="iPhone")
    track_outbound_apply_click(opp2, user_agent="Mozilla/5.0")

    trending = get_trending_scholarships(db_session, limit=5)
    assert len(trending) >= 2
    # Chevening should be #1
    top_item = next(t for t in trending if t.opportunity_id == str(opp1.id))
    assert top_item.total_apply_clicks >= 3
    assert top_item.trending_badge == "Most Popular"


# ==============================================================================
# TEST 5: PROFILE STRENGTH & SCHOLARSHIP UNLOCK METER
# ==============================================================================


def test_profile_strength_and_unlock_meter() -> None:
    # 1. Incomplete Profile (Only Nationality and Target Degree)
    prof_incomplete = StudentProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        nationality="PK",
        target_degree_level=TargetDegreeLevel.MASTERS,
    )
    res_incomplete = evaluate_profile_strength(prof_incomplete)
    assert res_incomplete.overall_score < 50
    assert len(res_incomplete.missing_fields) >= 3
    assert len(res_incomplete.unlock_suggestions) >= 3

    # 2. Complete Profile
    prof_complete = StudentProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        nationality="PK",
        target_degree_level=TargetDegreeLevel.MASTERS,
        intended_field="Computer Science",
        cgpa=Decimal("3.8"),
        grading_scale=Decimal("4.0"),
        ielts_score=Decimal("7.5"),
        english_test_status=TestStatus.TAKEN,
        work_experience_months=24,
    )
    res_complete = evaluate_profile_strength(prof_complete)
    assert res_complete.overall_score == 100
    assert res_complete.strength_tier.startswith("Elite")
    assert len(res_complete.missing_fields) == 0


# ==============================================================================
# TEST 6: APPLICATION KANBAN PIPELINE SUMMARY
# ==============================================================================


def test_application_kanban_pipeline_summary() -> None:
    ref_now = datetime(2027, 10, 1, 12, 0, tzinfo=UTC)
    opp = _sample_opportunity(deadline_dt=ref_now + timedelta(days=5))

    app1 = Application(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        opportunity_id=opp.id,
        lifecycle=ApplicationLifecycle.PREPARING,
    )
    app2 = Application(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        opportunity_id=opp.id,
        lifecycle=ApplicationLifecycle.SUBMITTED,
    )

    apps_data = [
        (app1, opp, 2, 5),  # 2 of 5 tasks done
        (app2, opp, 5, 5),  # 5 of 5 tasks done
    ]

    pipeline = build_pipeline_summary(apps_data, reference_dt=ref_now)

    assert pipeline.total_active_applications == 2
    assert pipeline.urgent_deadlines_count == 2  # 5 days left -> urgent

    preparing_lane = next(lane for lane in pipeline.lanes if lane.lane == KanbanLaneName.PREPARING)
    assert preparing_lane.count == 1
    assert preparing_lane.cards[0].tasks_completed == 2
    assert preparing_lane.cards[0].urgency_color == "rose"

    submitted_lane = next(lane for lane in pipeline.lanes if lane.lane == KanbanLaneName.SUBMITTED)
    assert submitted_lane.count == 1
