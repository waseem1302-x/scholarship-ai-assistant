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
