"""Browser journeys that run only when a live app URL is supplied."""

import os
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


@pytest.fixture
def live_base_url() -> str:
    base_url = os.getenv("E2E_BASE_URL")
    if not base_url:
        pytest.skip("Set E2E_BASE_URL to run browser end-to-end tests.")
    return base_url.rstrip("/")


def test_student_can_register_use_catalogue_and_log_out(page: Page, live_base_url: str) -> None:
    email = f"e2e-{uuid4().hex}@example.com"

    page.goto(live_base_url, wait_until="networkidle")
    expect(page).to_have_title("Scholarship AI Assistant")
    expect(page.locator("main")).to_be_visible()

    page.locator("#register-tab").click()
    page.locator("#auth-email").fill(email)
    page.locator("#auth-password").fill("BrowserTest!2026")
    page.locator("#auth-submit").click()

    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#user-email")).to_have_text(email)
    expect(page.locator("#opportunity-status")).to_contain_text("verified opportunities found")

    page.get_by_role("button", name="Logout").click()
    expect(page.locator("#auth-panel")).to_be_visible()
    expect(page.locator("#auth-status")).to_have_text("Logged out.")


def test_auth_form_is_keyboard_reachable(page: Page, live_base_url: str) -> None:
    page.goto(live_base_url, wait_until="networkidle")

    page.locator("#auth-email").focus()
    expect(page.locator("#auth-email")).to_be_focused()
    page.keyboard.press("Tab")
    expect(page.locator("#auth-password")).to_be_focused()


def test_phase_three_foundation_can_register_and_sign_out(page: Page, live_base_url: str) -> None:
    email = f"phase3-{uuid4().hex}@example.com"

    page.goto(f"{live_base_url}/app", wait_until="networkidle")
    expect(
        page.get_by_role("heading", name="Make your next scholarship decision with confidence.")
    ).to_be_visible()

    page.get_by_role("link", name="Get started").click()
    page.get_by_role("tab", name="Create account").click()
    page.get_by_label("Email address").fill(email)
    page.get_by_label("Password").fill("PhaseThree!2026")
    page.get_by_role("button", name="Create account").click()

    expect(page).to_have_url(f"{live_base_url}/app/dashboard")
    expect(
        page.get_by_role("heading", name=f"Good to see you, {email.split('@')[0]}.")
    ).to_be_visible()
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("link", name="Sign in")).to_be_visible()


def test_phase_three_catalogue_and_source_detail_are_browsable(
    page: Page, live_base_url: str
) -> None:
    opportunity_id = "0ad4842b-0c76-47d3-8dc1-2489ef3cf744"
    summary = {
        "id": opportunity_id,
        "name": "Phase Three Test Scholarship",
        "provider_name": "Verified Test Provider",
        "university_name": "Test University",
        "country": "Malaysia",
        "degree_level": "masters",
        "application_deadline": "2099-12-31T23:59:59Z",
        "funding_type": "full",
        "funding_summary": "Tuition and monthly living support are covered.",
        "verification_status": "officially_verified",
        "last_verified_at": "2099-01-01T00:00:00Z",
        "official_source_url": "https://example.com/official-scholarship",
        "application_window_state": "open",
        "source_is_fresh": True,
    }
    detail = {
        **summary,
        "field_eligibility": "Computer Science",
        "nationality_eligibility": "International applicants",
        "intake_year": 2100,
        "tuition_coverage": "Full tuition",
        "monthly_stipend_amount": 1500,
        "monthly_stipend_currency": "MYR",
        "accommodation_coverage": None,
        "travel_allowance": None,
        "health_insurance": "Included",
        "application_fee_info": "No fee",
        "english_language_requirement": "IELTS may be required",
        "standardized_test_requirement": None,
        "minimum_academic_requirement": "Strong academic record",
        "required_documents": ["Transcript", "Passport"],
        "application_method": "Official online portal",
        "application_url": "https://example.com/apply",
        "data_confidence": "high",
        "notes": "Check the official call before applying.",
        "eligibility_warnings": ["Confirm English language requirements."],
        "source": {
            "id": "24add9f5-f680-4653-8f6b-ec10a81f0017",
            "url": "https://example.com/official-scholarship",
            "source_type": "official",
            "title": "Official scholarship call",
            "relevant_excerpt": (
                "The official call confirms funding, requirements, and the application route."
            ),
            "verification_status": "officially_verified",
            "last_verified_at": "2099-01-01T00:00:00Z",
        },
    }

    def fulfil_opportunity_request(route) -> None:
        if route.request.url.endswith(opportunity_id):
            route.fulfill(status=200, content_type="application/json", json=detail)
        else:
            route.fulfill(
                status=200,
                content_type="application/json",
                json={
                    "items": [summary],
                    "pagination": {
                        "total": 1,
                        "limit": 10,
                        "offset": 0,
                        "count": 1,
                        "has_next": False,
                        "has_previous": False,
                    },
                },
            )

    page.route("**/api/v1/opportunities**", fulfil_opportunity_request)
    page.goto(f"{live_base_url}/app/catalogue", wait_until="networkidle")

    expect(
        page.get_by_role("heading", name="Find the opportunities worth your attention.")
    ).to_be_visible()
    expect(page.get_by_role("heading", name="Phase Three Test Scholarship")).to_be_visible()
    expect(page.get_by_text("Verified official source")).to_be_visible()
    page.get_by_role("link", name="View opportunity").click()

    expect(page).to_have_url(f"{live_base_url}/app/catalogue/{opportunity_id}")
    expect(page.get_by_role("heading", name="Official scholarship call")).to_be_visible()
    expect(page.get_by_role("link", name="Open official source")).to_have_attribute(
        "href", "https://example.com/official-scholarship"
    )


def test_phase_three_student_workspace_is_browsable(page: Page, live_base_url: str) -> None:
    user = {
        "id": "1aaf4e62-2d60-46cf-ae2d-3c295751ea66",
        "email": "workspace@example.com",
        "role": "student",
        "is_active": True,
        "email_verified_at": None,
        "created_at": "2099-01-01T00:00:00Z",
    }
    opportunity = {
        "id": "1f3a0d2e-93a8-4533-98e7-224d54de3c29",
        "name": "Student Workspace Test Scholarship",
        "provider_name": "Verified Test Provider",
        "university_name": None,
        "country": "Malaysia",
        "degree_level": "masters",
        "application_deadline": "2099-12-31T23:59:59Z",
        "funding_type": "full",
        "funding_summary": "Tuition is covered.",
        "verification_status": "officially_verified",
        "last_verified_at": "2099-01-01T00:00:00Z",
        "official_source_url": "https://example.com/official",
        "application_window_state": "open",
        "source_is_fresh": True,
    }
    profile = {
        "id": "e7fa6b7e-d454-4383-a104-d5240b0a4dde",
        "user_id": user["id"],
        "nationality": "Pakistani",
        "country_of_residence": None,
        "current_education_level": None,
        "target_degree_level": "masters",
        "intended_field": "Computer Science",
        "academic_discipline": None,
        "cgpa": None,
        "percentage": None,
        "grading_scale": None,
        "english_test_status": "unknown",
        "ielts_score": None,
        "toefl_score": None,
        "duolingo_score": None,
        "gre_status": "unknown",
        "gre_score": None,
        "work_experience_months": None,
        "research_experience": None,
        "publications": [],
        "leadership_experience": None,
        "financial_need": None,
        "preferred_destination_countries": ["Malaysia"],
        "preferred_study_mode": None,
        "target_intake": None,
        "application_constraints": None,
        "additional_eligibility_information": None,
        "profile_completeness": 55,
        "missing_recommended_fields": ["academic_discipline"],
    }
    tracker_item = {
        "id": "3119a647-b4fd-4f1e-a8cd-8b1a0a84e1f1",
        "status": "researching",
        "personal_notes": "Confirm the English requirement.",
        "personal_deadline": "2099-10-01T00:00:00Z",
        "document_checklist": [],
        "recommendation_letters": [],
        "test_requirements": [],
        "submitted_at": None,
        "outcome_notes": None,
        "opportunity": opportunity,
    }

    page.route(
        "**/api/v1/auth/refresh",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={"access_token": "test-access-token", "expires_in": 900, "user": user},
        ),
    )

    def profile_route(route) -> None:
        if route.request.method == "PUT":
            route.fulfill(status=200, content_type="application/json", json=profile)
        else:
            route.fulfill(status=204)

    page.route("**/api/v1/profiles/me", profile_route)
    page.route(
        "**/api/v1/matches/me",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={
                "profile_id": profile["id"],
                "results": [
                    {
                        "opportunity": opportunity,
                        "match_score": 82,
                        "score_label": "strong_fit",
                        "eligibility_status": "eligible",
                        "fit_score": 82,
                        "evidence_completeness": 80,
                        "confidence": "medium",
                        "failed_criteria": [],
                        "unknown_criteria": [],
                        "warnings": [],
                        "matcher_version": "v1",
                        "evaluated_at": "2099-01-01T00:00:00Z",
                        "explanation": {
                            "satisfied": ["Target degree aligns."],
                            "missing": ["Add academic discipline."],
                            "uncertain": [],
                            "next_steps": ["Read the official call."],
                        },
                        "disclaimer": "This is decision support, not an admission prediction.",
                    }
                ],
            },
        ),
    )

    def tracker_route(route) -> None:
        if route.request.method == "PATCH":
            route.fulfill(status=200, content_type="application/json", json=tracker_item)
        else:
            route.fulfill(status=200, content_type="application/json", json=[tracker_item])

    page.route("**/api/v1/saved-opportunities**", tracker_route)
    page.goto(f"{live_base_url}/app/profile", wait_until="networkidle")
    expect(page.get_by_role("heading", name="Build a profile you can trust.")).to_be_visible()
    page.get_by_label("Nationality").fill("Pakistani")
    page.get_by_role("button", name="Save profile").click()
    expect(page.get_by_role("status")).to_contain_text("Profile saved")

    page.goto(f"{live_base_url}/app/matches", wait_until="networkidle")
    expect(page.get_by_role("heading", name="Recommendations you can inspect.")).to_be_visible()
    expect(page.get_by_role("heading", name="Student Workspace Test Scholarship")).to_be_visible()
    expect(page.get_by_text("Information to add")).to_be_visible()

    page.goto(f"{live_base_url}/app/tracker", wait_until="networkidle")
    expect(
        page.get_by_role("heading", name="Turn research into a clear next step.")
    ).to_be_visible()
    page.get_by_role("button", name="Save update").click()
    expect(page.get_by_role("heading", name="Student Workspace Test Scholarship")).to_be_visible()
