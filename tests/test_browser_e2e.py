"""Browser journeys that run only when a live app URL is supplied."""

import inspect
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse
from uuid import uuid4

import pytest
import yaml
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

TRUTH_FIRST_MATCH_EXPECTATION = {
    "canonical_name": "DAAD EPOS",
    "target_degree_level": "bachelors",
    "score_label": "not_eligible",
    "eligibility_status": "ineligible",
    "warning": "Target degree does not match this opportunity.",
}


def _normalized_words(value: str) -> set[str]:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]+", ascii_value.casefold()))


def _manifest_entry_for_name(
    opportunity_name: str, manifest: list[dict[str, str]]
) -> dict[str, str] | None:
    opportunity_words = _normalized_words(opportunity_name)
    matches = [
        entry
        for entry in manifest
        if _normalized_words(entry["canonical_name"]).issubset(opportunity_words)
    ]
    return matches[0] if len(matches) == 1 else None


def _url_matches_official_root(source_url: str, root_url: str) -> bool:
    source = urlparse(source_url)
    root = urlparse(root_url)
    source_host = (source.hostname or "").casefold().removeprefix("www.")
    root_host = (root.hostname or "").casefold().removeprefix("www.")
    source_path = unquote(source.path).rstrip("/") or "/"
    root_path = unquote(root.path).rstrip("/") or "/"
    return (
        source.scheme == root.scheme == "https"
        and source_host == root_host
        and (
            root_path == "/"
            or source_path == root_path
            or source_path.startswith(f"{root_path}/")
        )
        and (not root.query or sorted(parse_qsl(source.query)) == sorted(parse_qsl(root.query)))
    )


@pytest.fixture
def live_base_url() -> str:
    base_url = os.getenv("E2E_BASE_URL")
    if not base_url:
        pytest.skip("Set E2E_BASE_URL to run browser end-to-end tests.")
    return base_url.rstrip("/")


@pytest.fixture
def truth_first_staging_environment() -> dict[str, str]:
    names = (
        "E2E_BASE_URL",
        "E2E_STAGING_EMAIL",
        "E2E_STAGING_PASSWORD",
    )
    values = {name: os.getenv(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.skip(
            "Set the protected staging journey values: " + ", ".join(missing)
        )

    parsed = urlparse(values["E2E_BASE_URL"])
    assert parsed.scheme == "https" and parsed.hostname not in {"localhost", "127.0.0.1"}, (
        "The truth-first launch journey must target a live HTTPS staging revision."
    )
    values["E2E_BASE_URL"] = values["E2E_BASE_URL"].rstrip("/")
    return values


def test_truth_first_launch_manifest_has_only_reviewed_official_roots() -> None:
    expected = [
        (
            "DAAD EPOS",
            "https://www2.daad.de/deutschland/stipendium/datenbank/en/"
            "21148-scholarship-database?detail=50076777",
        ),
        (
            "Fulbright Foreign Student Program",
            "https://foreign.fulbrightonline.org/about/foreign-student-program",
        ),
        ("Chevening", "https://www.chevening.org/scholarships/"),
        ("Vanier", "https://vanier.gc.ca/en/home-accueil.html"),
        ("Australia Awards", "https://www.dfat.gov.au/people-to-people/australia-awards"),
        (
            "Erasmus Mundus Joint Masters",
            "https://erasmus-plus.ec.europa.eu/opportunities/individuals/students/"
            "erasmus-mundus-joint-masters",
        ),
        ("MEXT Research", "https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/"),
        (
            "Commonwealth Master\u2019s",
            "https://cscuk.fcdo.gov.uk/scholarships/commonwealth-masters-scholarships/",
        ),
        ("Gates Cambridge", "https://www.gatescambridge.org/"),
        ("Türkiye Scholarships", "https://www.turkiyeburslari.gov.tr/"),
        ("Stipendium Hungaricum", "https://stipendiumhungaricum.hu/"),
        (
            "Swedish Institute Scholarships for Global Professionals",
            "https://si.se/en/apply/scholarships/swedish-institute-scholarships-for-global-professionals/",
        ),
    ]

    manifest = json.loads(Path("data/launch-scholarships.json").read_text(encoding="utf-8"))

    assert [(item["canonical_name"], item["official_root_url"]) for item in manifest] == expected
    assert all(set(item) == {"canonical_name", "official_root_url"} for item in manifest)


def test_launch_deployment_fails_closed_and_preserves_gate_evidence() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/azure-application-deploy.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["deploy"]["steps"]
    by_name = {step.get("name"): step for step in steps if step.get("name")}
    names = list(by_name)

    migration = names.index("Apply rolling-safe expand migration")
    audit = names.index("Run read-only launch catalogue audit")
    smoke = names.index("Run product and tenant-isolation smoke against candidate")
    journey = names.index("Run truth-first Chromium journey against candidate")
    receipt = names.index("Create immutable staging promotion manifest")
    promotion = names.index("Promote candidate traffic atomically")
    assert migration < audit < smoke < journey < receipt < promotion

    audit_run = by_name["Run read-only launch catalogue audit"]["run"]
    assert "containerapp exec" not in audit_run
    assert "containerapp job start" in audit_run
    assert "containerapp job execution show" in audit_run
    assert "containerapp job logs show" in audit_run
    assert '"--manifest","data/launch-scholarships.json"' in audit_run
    assert 'audit_dir=release-provenance' in audit_run
    assert '"$audit_dir/catalogue-audit.json"' in audit_run
    assert '"$audit_dir/catalogue-audit-execution.json"' in audit_run
    assert "inputs.environment == 'staging'" not in str(
        by_name["Run read-only launch catalogue audit"].get("if", "")
    )

    smoke_run = by_name["Run product and tenant-isolation smoke against candidate"]["run"]
    assert "scripts/staging_smoke.py" in smoke_run
    assert "evidence_dir=release-provenance" in smoke_run
    assert '"$evidence_dir/candidate-smoke.json"' in smoke_run

    journey_step = by_name["Run truth-first Chromium journey against candidate"]
    journey_run = journey_step["run"]
    assert "tests/test_browser_e2e.py::test_truth_first_mvp_launch_journey" in journey_run
    assert journey_run.count("--browser chromium") == 1
    assert "--junitxml=release-provenance/truth-first-chromium.xml" in journey_run
    assert journey_step["env"]["E2E_BASE_URL"] == "${{ steps.candidate.outputs.base_url }}"
    assert journey_step["env"]["E2E_STAGING_EMAIL"] == "${{ vars.E2E_STAGING_EMAIL }}"
    assert journey_step["env"]["E2E_STAGING_PASSWORD"] == "${{ secrets.E2E_STAGING_PASSWORD }}"

    assert "continue-on-error" not in workflow

    upload = by_name["Upload staging promotion manifest"]
    assert upload["with"]["path"] == "release-provenance"
    assert upload["with"]["if-no-files-found"] == "error"
    assert "always()" in upload["if"]

    provenance_run = by_name["Create immutable staging promotion manifest"]["run"]
    assert "scripts/release_provenance.py create" in provenance_run
    assert "--run-attempt" in provenance_run
    assert "--manifest data/launch-scholarships.json" in provenance_run

    beta_validation = by_name["Validate staging provenance"]["run"]
    assert "gh api" in beta_validation
    assert "scripts/release_provenance.py validate" in beta_validation
    assert "--manifest data/launch-scholarships.json" in beta_validation
    assert by_name["Validate staging provenance"]["env"]["EXPECTED_HEAD_SHA"] == "${{ github.sha }}"

    migration_job = Path("infra/azure/migration-job.bicep").read_text(encoding="utf-8")
    assert "name: 'APP_DATABASE_URL'" in migration_job


def test_manifest_name_and_official_root_matching_is_strict() -> None:
    manifest = [
        {
            "canonical_name": "Chevening",
            "official_root_url": "https://www.chevening.org/scholarships/",
        }
    ]

    assert _manifest_entry_for_name("Chevening Scholarships 2027/28", manifest) == manifest[0]
    assert _manifest_entry_for_name("Unrelated Scholarship", manifest) is None
    assert _url_matches_official_root(
        "https://www.chevening.org/scholarships/application-timeline/",
        manifest[0]["official_root_url"],
    )
    assert not _url_matches_official_root(
        "https://www.chevening.org/other-programme/",
        manifest[0]["official_root_url"],
    )


def test_truth_first_journey_uses_a_fixed_flagship_profile_and_match_outcome() -> None:
    assert TRUTH_FIRST_MATCH_EXPECTATION == {
        "canonical_name": "DAAD EPOS",
        "target_degree_level": "bachelors",
        "score_label": "not_eligible",
        "eligibility_status": "ineligible",
        "warning": "Target degree does not match this opportunity.",
    }


def test_truth_first_journey_never_uses_bulk_application_deletion() -> None:
    module_source = Path(__file__).read_text(encoding="utf-8")
    forbidden_endpoint = "/api/v1/applications/" + "data"
    journey_source = inspect.getsource(test_truth_first_mvp_launch_journey)

    assert forbidden_endpoint not in module_source
    assert "_clear_staging_application_state" not in journey_source
    assert "_delete_staging_application(page, application_id)" in journey_source


@pytest.mark.browser_compat
def test_auth_form_is_keyboard_reachable(page: Page, live_base_url: str) -> None:
    page.goto(live_base_url, wait_until="networkidle")

    expect(page.get_by_role("link", name="Scholarships", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Dashboard", exact=True)).to_have_count(0)
    page.get_by_role("link", name="Sign in").click()
    email = page.get_by_label("Email address", exact=True)
    password = page.get_by_label("Password")
    email.focus()
    expect(email).to_be_focused()
    page.keyboard.press("Tab")
    expect(password).to_be_focused()


@pytest.mark.browser_compat
def test_public_shell_has_critical_accessibility_semantics(page: Page, live_base_url: str) -> None:
    page.goto(live_base_url, wait_until="networkidle")

    violations = page.locator("body").evaluate(
        """
        () => {
          const failures = [];
          const ids = [...document.querySelectorAll('[id]')].map((node) => node.id);
          if (new Set(ids).size !== ids.length) failures.push('duplicate_ids');
          if (!document.querySelector('main')) failures.push('missing_main');
          if (!document.querySelector('h1')) failures.push('missing_h1');
          for (const image of document.querySelectorAll('img')) {
            if (!image.hasAttribute('alt')) failures.push('image_without_alt');
          }
          const controls = document.querySelectorAll(
            'button, input:not([type=hidden]), select, textarea'
          );
          for (const control of controls) {
            const named = control.getAttribute('aria-label') ||
              control.getAttribute('aria-labelledby') || control.labels?.length ||
              (control.tagName === 'BUTTON' && control.textContent?.trim());
            if (!named) failures.push(`unnamed_${control.tagName.toLowerCase()}`);
          }
          for (const link of document.querySelectorAll('a[href]')) {
            if (!(link.getAttribute('aria-label') || link.textContent?.trim())) {
              failures.push('unnamed_link');
            }
          }
          return failures;
        }
        """
    )
    assert violations == []


def test_public_home_can_browse_scholarships_without_an_account(
    page: Page, live_base_url: str
) -> None:
    page.goto(live_base_url, wait_until="networkidle")

    page.get_by_role("link", name="Scholarships", exact=True).click()

    expect(page).to_have_url(f"{live_base_url}/catalogue")
    expect(
        page.get_by_role("heading", name="Find the opportunities worth your attention.")
    ).to_be_visible()
    page.get_by_label("Availability").select_option("upcoming")
    page.get_by_role("button", name="Apply filters").click()
    expect(page).to_have_url(
        f"{live_base_url}/catalogue?availability=upcoming&limit=10&offset=0&application_window_state=upcoming"
    )
    expect(page.get_by_text("Upcoming verified opportunities")).to_be_visible()

    page.get_by_label("Availability").select_option("all")
    page.get_by_role("button", name="Apply filters").click()
    expect(page).to_have_url(f"{live_base_url}/catalogue?availability=all&limit=10&offset=0")
    expect(page.get_by_text("All verified opportunities")).to_be_visible()


def test_react_frontend_can_register_and_sign_out(page: Page, live_base_url: str) -> None:
    email = f"phase3-{uuid4().hex}@example.com"

    page.goto(live_base_url, wait_until="networkidle")
    expect(
        page.get_by_role("heading", name="Find scholarships you can actually act on.")
    ).to_be_visible()

    page.get_by_role("link", name="Sign in").click()
    page.get_by_role("tab", name="Create account").click()
    page.get_by_label("Email address", exact=True).fill(email)
    page.get_by_label("Password").fill("PhaseThree!2026")
    page.get_by_role("button", name="Create account").click()

    expect(page).to_have_url(f"{live_base_url}/dashboard")
    expect(
        page.get_by_role("heading", name=f"Good to see you, {email.split('@')[0]}.")
    ).to_be_visible()
    for link_name in ["Scholarships", "Dashboard", "Applications"]:
        expect(page.get_by_role("link", name=link_name, exact=True)).to_be_visible()
    page.get_by_text("More", exact=True).click()
    for link_name in ["Profile", "Matches"]:
        expect(page.get_by_role("link", name=re.compile(rf"^{link_name}\b"))).to_be_visible()
    expect(page.get_by_role("link", name="Admin", exact=True)).to_have_count(0)
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("link", name="Sign in")).to_be_visible()


def test_react_email_verification_and_password_reset(page: Page, live_base_url: str) -> None:
    email = f"lifecycle-{uuid4().hex}@example.com"
    new_password = "UpdatedPassword2026"

    page.goto(live_base_url, wait_until="networkidle")
    page.get_by_role("link", name="Sign in").click()
    page.get_by_role("tab", name="Create account").click()
    page.get_by_label("Email address", exact=True).fill(email)
    page.get_by_label("Password").fill("LifecyclePassword2026")
    page.get_by_role("button", name="Create account").click()

    page.get_by_role("link", name="Verify email").click()
    page.get_by_role("button", name="Send verification email").click()
    verification_token = page.get_by_label("Development verification token").inner_text()
    page.get_by_role("textbox", name="Verification token", exact=True).fill(verification_token)
    page.get_by_role("button", name="Verify email").click()
    expect(page.get_by_role("heading", name="Email address confirmed.")).to_be_visible()

    page.get_by_role("link", name="Return to workspace").click()
    page.goto(f"{live_base_url}/auth/password-reset", wait_until="networkidle")
    page.get_by_label("Email address", exact=True).fill(email)
    page.get_by_role("button", name="Request password reset").click()
    reset_token = page.get_by_label("Development password reset token").inner_text()
    page.get_by_role("textbox", name="Reset token", exact=True).fill(reset_token)
    page.get_by_label("New password").fill(new_password)
    page.get_by_role("button", name="Update password").click()
    expect(page.get_by_role("heading", name="Password updated.")).to_be_visible()

    page.get_by_role("link", name="Sign in", exact=True).last.click()
    expect(page.get_by_label("Email address", exact=True)).to_be_visible()
    page.get_by_label("Email address", exact=True).fill(email)
    page.get_by_label("Password").fill(new_password)
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(f"{live_base_url}/dashboard")


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
        "verification_freshness": "recent",
        "funding_display_label": "All tracked funding components confirmed",
        "catalogue_decision_tier": "informational_only",
        "structured_eligibility_complete": False,
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
    page.goto(f"{live_base_url}/catalogue", wait_until="networkidle")

    expect(
        page.get_by_role("heading", name="Find the opportunities worth your attention.")
    ).to_be_visible()
    expect(page.get_by_role("heading", name="Phase Three Test Scholarship")).to_be_visible()
    expect(page.get_by_text("Recently verified official source")).to_be_visible()
    page.get_by_role("link", name="View opportunity").click()

    expect(page).to_have_url(f"{live_base_url}/catalogue/{opportunity_id}")
    expect(page.get_by_role("heading", name="Official scholarship call")).to_be_visible()
    expect(page.get_by_role("link", name="Open official source")).to_have_attribute(
        "href", "https://example.com/official-scholarship"
    )
    expect(page.get_by_role("link", name="Create an account to save and track")).to_have_attribute(
        "href", "/auth"
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
        "verification_freshness": "recent",
        "funding_display_label": "All tracked funding components confirmed",
        "catalogue_decision_tier": "informational_only",
        "structured_eligibility_complete": False,
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
                        "score_label": "strong_match",
                        "fit_band": "high_alignment",
                        "display_label": "High criteria alignment",
                        "eligibility_status": "potentially_eligible",
                        "fit_score": 82,
                        "preference_fit": 75,
                        "evidence_completeness": 80,
                        "profile_completeness": 90,
                        "confidence": "medium",
                        "confidence_factors": ["Most evaluated requirements have known outcomes."],
                        "eligibility_failures": [],
                        "preference_mismatches": [],
                        "missing_information": [],
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
    page.route(
        "**/api/v1/applications/command-centre",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={
                "urgent_tasks": [],
                "blocked_tasks": [],
                "blocked_applications": [],
                "approaching_deadlines": [],
                "submitted_applications": [],
                "upcoming_reminders": [],
                "recently_changed_opportunities": [],
            },
        ),
    )
    page.route(
        "**/api/v1/applications",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={"items": [], "pagination": {"total": 0}},
        ),
    )
    page.route(
        "**/api/v1/applications/notification-preferences",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={"in_app_enabled": True},
        ),
    )
    page.goto(f"{live_base_url}/profile", wait_until="networkidle")
    expect(page.get_by_role("heading", name="Build a profile you can trust.")).to_be_visible()
    page.get_by_label("Nationality").fill("Pakistani")
    page.get_by_role("button", name="Save profile").click()
    expect(page.get_by_role("status")).to_contain_text("Profile saved")

    page.goto(f"{live_base_url}/matches", wait_until="networkidle")
    expect(page.get_by_role("heading", name="Recommendations you can inspect.")).to_be_visible()
    expect(page.get_by_role("heading", name="Student Workspace Test Scholarship")).to_be_visible()
    expect(page.get_by_text("Information to add")).to_be_visible()

    page.goto(f"{live_base_url}/tracker", wait_until="networkidle")
    expect(page).to_have_url(f"{live_base_url}/applications")
    expect(page.get_by_role("heading", name="Know what needs your attention.")).to_be_visible()
    expect(page.get_by_role("heading", name="No applications yet.")).to_be_visible()


def test_phase_three_admin_workspace_is_browsable(page: Page, live_base_url: str) -> None:
    user = {
        "id": "b841a458-bb0e-4c31-98ef-f8e2e9f8c2b4",
        "email": "reviewer@example.com",
        "role": "admin",
        "is_active": True,
        "email_verified_at": "2099-01-01T00:00:00Z",
        "created_at": "2099-01-01T00:00:00Z",
    }
    source = {
        "id": "4a8420dc-8de0-4f40-938d-df45ce13c884",
        "url": "https://example.com/official-call",
        "source_type": "official",
        "title": "Official scholarship call",
        "relevant_excerpt": (
            "The official source needs a curator decision after its deadline changed."
        ),
        "verification_status": "needs_review",
        "last_verified_at": None,
    }
    opportunity = {
        "id": "52c07256-ad65-4169-841e-c23189874049",
        "name": "Admin Review Test Scholarship",
        "provider_name": "Verified Test Provider",
        "university_name": None,
        "country": "Malaysia",
        "degree_level": "masters",
        "application_deadline": "2099-12-31T23:59:59Z",
        "funding_type": "full",
        "funding_summary": "Tuition is covered.",
        "verification_status": "needs_review",
        "last_verified_at": None,
        "official_source_url": source["url"],
        "application_window_state": "open",
        "source_is_fresh": True,
        "verification_freshness": "recent",
        "funding_display_label": "All tracked funding components confirmed",
        "catalogue_decision_tier": "informational_only",
        "structured_eligibility_complete": False,
        "status": "draft",
        "data_confidence": "medium",
        "source": source,
        "sources": [source],
    }
    issue = {
        "code": "source_requires_review",
        "severity": "high",
        "message": "The official source changed and must be reviewed before publication.",
        "opportunity_id": opportunity["id"],
        "opportunity_name": opportunity["name"],
        "source_id": source["id"],
    }
    pagination = {
        "total": 1,
        "limit": 50,
        "offset": 0,
        "count": 1,
        "has_next": False,
        "has_previous": False,
    }
    catalogue_queries: list[str] = []

    page.route(
        "**/api/v1/auth/refresh",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={"access_token": "test-access-token", "expires_in": 900, "user": user},
        ),
    )
    page.route(
        "**/api/v1/admin/review-queue**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={
                "items": [{"opportunity": opportunity, "reasons": [issue]}],
                "pagination": pagination,
            },
        ),
    )
    page.route(
        "**/api/v1/admin/data-quality-issues**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={"items": [issue], "pagination": pagination},
        ),
    )

    def catalogue_records_route(route) -> None:
        catalogue_queries.append(route.request.url)
        route.fulfill(
            status=200,
            content_type="application/json",
            json={"items": [opportunity], "pagination": {**pagination, "limit": 20}},
        )

    page.route("**/api/v1/admin/opportunities**", catalogue_records_route)

    page.goto(f"{live_base_url}/admin", wait_until="networkidle")

    expect(page.get_by_role("heading", name="Keep scholarships trustworthy.")).to_be_visible()
    expect(page.get_by_role("heading", name="Admin Review Test Scholarship")).to_be_visible()
    expect(page.get_by_role("heading", name="Build a cited scholarship record.")).to_be_visible()
    page.get_by_role("button", name="Add supporting URL").click()
    supporting_url = page.get_by_label("Supporting official URL 1")
    expect(supporting_url).to_be_visible()
    supporting_url.fill("https://www.mext.go.jp/current-guidelines.pdf")
    page.get_by_role("button", name="Remove").click()
    assert page.get_by_label("Supporting official URL 1").count() == 0
    expect(page.get_by_text("source requires review").first).to_be_visible()
    assert page.get_by_label("Administrator password").count() == 3
    expect(page.get_by_role("button", name="Record source check")).to_be_visible()
    expect(page.get_by_role("button", name="Reverify selected source")).to_be_visible()
    page.get_by_label("Upload opportunity import file").set_input_files(
        {
            "name": "opportunities.csv",
            "mimeType": "text/csv",
            "buffer": (
                b"name,provider_name,country,degree_level\n"
                b"Uploaded Scholarship,Example Provider,Malaysia,masters\n"
            ),
        }
    )
    expect(
        page.get_by_text(
            "Loaded opportunities.csv. Review the contents before running a dry import."
        )
    ).to_be_visible()
    page.get_by_label("Country").last.fill("Malaysia")
    page.get_by_role("button", name="Apply filters").last.click()
    expect(page.get_by_text("Showing 1 of 1").last).to_be_visible()
    assert any("country=Malaysia" in query for query in catalogue_queries)


def test_phase_five_application_command_centre_journey(page: Page, live_base_url: str) -> None:
    """A student can create an application and advance its source-aware workflow."""
    user = {
        "id": "4a2aa936-4dfa-4d69-8b17-e6a9fc38c067",
        "email": "phase-five@example.com",
        "role": "student",
        "is_active": True,
        "email_verified_at": "2099-01-01T00:00:00Z",
        "created_at": "2099-01-01T00:00:00Z",
    }
    opportunity_id = "6d7268a9-5e6f-4fa5-841e-7b554369877a"
    application_id = "800a7a52-3e22-4731-b12a-722f3c73a322"
    opportunity = {
        "id": opportunity_id,
        "name": "Phase Five Verified Scholarship",
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
        "verification_freshness": "recent",
        "funding_display_label": "All tracked funding components confirmed",
        "catalogue_decision_tier": "informational_only",
        "structured_eligibility_complete": False,
    }
    detail = {
        **opportunity,
        "field_eligibility": "Computer Science",
        "nationality_eligibility": "International applicants",
        "intake_year": 2100,
        "tuition_coverage": "Full tuition",
        "monthly_stipend_amount": None,
        "monthly_stipend_currency": None,
        "accommodation_coverage": None,
        "travel_allowance": None,
        "health_insurance": None,
        "application_fee_info": "No fee",
        "english_language_requirement": None,
        "standardized_test_requirement": None,
        "minimum_academic_requirement": None,
        "required_documents": ["Transcript"],
        "application_method": "Official online portal",
        "application_url": "https://example.com/apply",
        "data_confidence": "high",
        "notes": None,
        "eligibility_warnings": [],
        "source": {
            "id": "eea4e950-6f5d-4112-9d72-bc48961bcde2",
            "url": "https://example.com/official",
            "source_type": "official",
            "title": "Official scholarship call",
            "relevant_excerpt": "Official requirements and application deadline.",
            "verification_status": "officially_verified",
            "last_verified_at": "2099-01-01T00:00:00Z",
        },
    }
    lifecycle = "saved"
    created = False
    tasks = [
        {
            "id": "de7e6e5d-7d8d-4947-a3e4-5064201866d4",
            "category": "document",
            "title": "Prepare Transcript",
            "status": "todo",
            "priority": "normal",
            "due_at": None,
            "source_id": detail["source"]["id"],
            "source_excerpt_id": None,
            "is_generated": True,
            "completion_evidence": None,
            "completed_at": None,
            "notes": None,
        }
    ]
    reminders: list[dict[str, object]] = []

    def application() -> dict[str, object]:
        return {
            "id": application_id,
            "lifecycle": lifecycle,
            "official_deadline": "2099-12-31T23:59:59Z",
            "official_deadline_timezone": "UTC",
            "official_deadline_state": "known",
            "official_deadline_source_id": detail["source"]["id"],
            "official_deadline_excerpt_id": None,
            "official_deadline_verified_at": "2099-01-01T00:00:00Z",
            "personal_deadline": None,
            "personal_deadline_timezone": "UTC",
            "deadline_urgency": "upcoming",
            "notes": None,
            "submitted_at": None,
            "decision_notes": None,
            "version": 1,
            "created_at": "2099-01-01T00:00:00Z",
            "updated_at": "2099-01-01T00:00:00Z",
            "opportunity": opportunity,
            "tasks": tasks,
            "reminders": reminders,
            "documents": [],
        }

    page.route(
        "**/api/v1/auth/refresh",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={"access_token": "test-access-token", "expires_in": 900, "user": user},
        ),
    )
    page.route(
        f"**/api/v1/opportunities/{opportunity_id}",
        lambda route: route.fulfill(status=200, content_type="application/json", json=detail),
    )
    page.route(
        "**/api/v1/saved-opportunities",
        lambda route: route.fulfill(status=201, content_type="application/json", json={}),
    )
    page.route(
        "**/api/v1/applications/command-centre",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={
                "urgent_tasks": tasks,
                "blocked_tasks": [],
                "blocked_applications": [],
                "approaching_deadlines": [application()] if created else [],
                "submitted_applications": [application()] if lifecycle == "submitted" else [],
                "upcoming_reminders": reminders,
                "recently_changed_opportunities": [],
            },
        ),
    )
    page.route(
        "**/api/v1/applications/notification-preferences",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={"in_app_enabled": True, "updated_at": "2099-01-01T00:00:00Z"},
        ),
    )
    page.route(
        f"**/api/v1/applications/{application_id}/events",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json=[
                {
                    "id": "116bf5ae-106c-44cb-bef7-5392d3ce6c5b",
                    "event_type": "application.created",
                    "metadata_json": {},
                    "created_at": "2099-01-01T00:00:00Z",
                }
            ],
        ),
    )

    def tasks_route(route) -> None:
        if route.request.method == "POST":
            payload = route.request.post_data_json
            task = {
                "id": "16f8f3bd-cf8a-4682-9bbd-30d5c0978f9f",
                "category": payload["category"],
                "title": payload["title"],
                "status": "todo",
                "priority": "normal",
                "due_at": None,
                "source_id": None,
                "source_excerpt_id": None,
                "is_generated": False,
                "completion_evidence": None,
                "completed_at": None,
                "notes": None,
            }
            tasks.append(task)
            route.fulfill(status=201, content_type="application/json", json=task)
        else:
            route.fulfill(status=200, content_type="application/json", json=application())

    def reminders_route(route) -> None:
        payload = route.request.post_data_json
        reminder = {
            "id": "da56673b-3a8f-45ba-882f-4ea93b625dc8",
            "task_id": None,
            "scheduled_at": payload["scheduled_at"],
            "timezone": payload["timezone"],
            "message": payload["message"],
            "status": "scheduled",
            "delivered_at": None,
            "read_at": None,
        }
        reminders.append(reminder)
        route.fulfill(status=201, content_type="application/json", json=reminder)

    page.route(f"**/api/v1/applications/{application_id}/tasks", tasks_route)
    page.route(f"**/api/v1/applications/{application_id}/reminders", reminders_route)

    def application_route(route) -> None:
        nonlocal lifecycle, created
        if route.request.method == "POST":
            created = True
        elif route.request.method == "PATCH":
            payload = route.request.post_data_json
            if payload.get("lifecycle"):
                lifecycle = payload["lifecycle"]
        route.fulfill(
            status=201 if route.request.method == "POST" else 200,
            content_type="application/json",
            json=application(),
        )

    page.route(f"**/api/v1/applications/{application_id}", application_route)

    def applications_route(route) -> None:
        nonlocal created
        if route.request.method == "POST":
            created = True
            route.fulfill(status=201, content_type="application/json", json=application())
        else:
            route.fulfill(
                status=200,
                content_type="application/json",
                json={
                    "items": [application()] if created else [],
                    "pagination": {
                        "total": 1 if created else 0,
                        "limit": 25,
                        "offset": 0,
                        "count": 1 if created else 0,
                        "has_next": False,
                        "has_previous": False,
                    },
                },
            )

    page.route("**/api/v1/applications", applications_route)

    page.goto(f"{live_base_url}/catalogue/{opportunity_id}", wait_until="networkidle")
    page.get_by_role("button", name="Save & track").click()
    expect(page.get_by_role("status")).to_contain_text("Saved. Your application plan is ready.")
    page.get_by_role("link", name="Applications", exact=True).click()
    expect(page.get_by_role("heading", name="Phase Five Verified Scholarship")).to_be_visible()
    page.get_by_role("link", name="Open workspace").click()
    expect(page.get_by_role("heading", name="Task board")).to_be_visible()
    page.get_by_label("New task").fill("Confirm portal account")
    page.get_by_role("button", name="Add task").click()
    expect(page.get_by_text("Confirm portal account")).to_be_visible()
    page.get_by_label("When").fill("2099-10-01T09:00")
    page.get_by_label("Message").fill("Check portal receipt")
    page.get_by_role("button", name="Schedule").click()
    expect(page.get_by_text("Check portal receipt")).to_be_visible()
    page.get_by_role("button", name="Move to preparing").click()
    page.get_by_role("button", name="Move to ready to submit").click()
    page.get_by_role("button", name="Move to submitted").click()
    expect(page.get_by_text("Current: submitted")).to_be_visible()


def _delete_staging_application(page: Page, application_id: str) -> None:
    status = page.evaluate(
        """
        async (applicationId) => {
          const csrf = document.cookie
            .split(';')
            .map((item) => item.trim())
            .find((item) => item.startsWith('csrf_token='))
            ?.split('=')[1];
          const headers = {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            ...(csrf ? {'X-CSRF-Token': decodeURIComponent(csrf)} : {}),
          };
          const refresh = await fetch('/api/v1/auth/refresh', {
            method: 'POST',
            headers,
            body: '{}',
            credentials: 'same-origin',
          });
          if (!refresh.ok) return refresh.status;
          const session = await refresh.json();
          const deletion = await fetch(`/api/v1/applications/${applicationId}`, {
            method: 'DELETE',
            headers: {...headers, Authorization: `Bearer ${session.access_token}`},
            credentials: 'same-origin',
          });
          return deletion.status;
        }
        """,
        application_id,
    )
    assert status == 204


def _get_staging_profile(page: Page) -> dict[str, object] | None:
    result = page.evaluate(
        """
        async () => {
          const csrf = document.cookie.split(';').map((item) => item.trim())
            .find((item) => item.startsWith('csrf_token='))?.split('=')[1];
          const headers = {Accept: 'application/json', 'Content-Type': 'application/json',
            ...(csrf ? {'X-CSRF-Token': decodeURIComponent(csrf)} : {})};
          const refresh = await fetch('/api/v1/auth/refresh', {
            method: 'POST', headers, body: '{}', credentials: 'same-origin',
          });
          if (!refresh.ok) return {status: refresh.status, profile: null};
          const session = await refresh.json();
          const response = await fetch('/api/v1/profiles/me', {
            headers: {...headers, Authorization: `Bearer ${session.access_token}`},
            credentials: 'same-origin',
          });
          return {
            status: response.status,
            profile: response.status === 204 ? null : await response.json(),
          };
        }
        """
    )
    assert result["status"] in {200, 204}
    return result["profile"]


def _restore_staging_profile(page: Page, original: dict[str, object]) -> None:
    status = page.evaluate(
        """
        async (original) => {
          const csrf = document.cookie.split(';').map((item) => item.trim())
            .find((item) => item.startsWith('csrf_token='))?.split('=')[1];
          const headers = {Accept: 'application/json', 'Content-Type': 'application/json',
            ...(csrf ? {'X-CSRF-Token': decodeURIComponent(csrf)} : {})};
          const refresh = await fetch('/api/v1/auth/refresh', {
            method: 'POST', headers, body: '{}', credentials: 'same-origin',
          });
          if (!refresh.ok) return refresh.status;
          const session = await refresh.json();
          const authHeaders = {...headers, Authorization: `Bearer ${session.access_token}`};
          const currentResponse = await fetch('/api/v1/profiles/me', {
            headers: authHeaders, credentials: 'same-origin',
          });
          if (!currentResponse.ok) return currentResponse.status;
          const current = await currentResponse.json();
          const payload = {...original, expected_version: current.version};
          for (const key of ['id', 'user_id', 'version', 'profile_completeness',
            'missing_recommended_fields', 'completeness_context']) delete payload[key];
          const restore = await fetch('/api/v1/profiles/me', {
            method: 'PUT', headers: authHeaders, body: JSON.stringify(payload),
            credentials: 'same-origin',
          });
          return restore.status;
        }
        """,
        original,
    )
    assert status == 200


def _delete_staging_match_evaluation(page: Page, evaluation_id: str) -> None:
    status = page.evaluate(
        """
        async (evaluationId) => {
          const csrf = document.cookie.split(';').map((item) => item.trim())
            .find((item) => item.startsWith('csrf_token='))?.split('=')[1];
          const headers = {Accept: 'application/json', 'Content-Type': 'application/json',
            ...(csrf ? {'X-CSRF-Token': decodeURIComponent(csrf)} : {})};
          const refresh = await fetch('/api/v1/auth/refresh', {
            method: 'POST', headers, body: '{}', credentials: 'same-origin',
          });
          if (!refresh.ok) return refresh.status;
          const session = await refresh.json();
          const deletion = await fetch(`/api/v1/matches/me/evaluations/${evaluationId}`, {
            method: 'DELETE',
            headers: {...headers, Authorization: `Bearer ${session.access_token}`},
            credentials: 'same-origin',
          });
          return deletion.status;
        }
        """,
        evaluation_id,
    )
    assert status == 204


def test_truth_first_mvp_launch_journey(
    page: Page,
    truth_first_staging_environment: dict[str, str],
) -> None:
    """A protected synthetic student traverses the complete reviewed launch journey."""
    base_url = truth_first_staging_environment["E2E_BASE_URL"]
    manifest = json.loads(Path("data/launch-scholarships.json").read_text(encoding="utf-8"))
    manifest_entry = next(
        entry
        for entry in manifest
        if entry["canonical_name"] == TRUTH_FIRST_MATCH_EXPECTATION["canonical_name"]
    )
    page.goto(base_url, wait_until="networkidle")

    for deferred_product in ("Assistant", "Document Lab", "Community"):
        expect(page.get_by_role("link", name=deferred_product, exact=True)).to_have_count(0)

    verified_section = page.get_by_role(
        "region", name="Verified scholarships worth exploring"
    )
    expect(verified_section).to_be_visible()
    homepage_links = verified_section.locator("h3 a")
    homepage_card_link = None
    for index in range(homepage_links.count()):
        candidate_link = homepage_links.nth(index)
        candidate_entry = _manifest_entry_for_name(candidate_link.inner_text().strip(), manifest)
        if candidate_entry == manifest_entry:
            homepage_card_link = candidate_link
            break
    assert homepage_card_link is not None, (
        "The homepage must expose the source-controlled DAAD EPOS launch flagship."
    )
    expect(homepage_card_link).to_be_visible()
    scholarship_name = homepage_card_link.inner_text().strip()
    direct_detail_href = homepage_card_link.get_attribute("href")
    assert direct_detail_href and re.fullmatch(r"/catalogue/[0-9a-f-]{36}", direct_detail_href)
    opportunity_id = direct_detail_href.rsplit("/", maxsplit=1)[-1]

    verified_section.get_by_role("link", name="View all scholarships").click()
    expect(page).to_have_url(re.compile(rf"^{re.escape(base_url)}/catalogue(?:\?.*)?$"))
    catalogue_result = page.get_by_role("heading", name=scholarship_name, exact=True).first
    expect(catalogue_result).to_be_visible()
    catalogue_result.get_by_role("link", name=scholarship_name, exact=True).click()

    expect(page).to_have_url(f"{base_url}{direct_detail_href}")
    expect(page.get_by_role("heading", name=scholarship_name, exact=True).first).to_be_visible()
    evidence = page.get_by_role("region", name="Reviewed source citations")
    expect(evidence).to_be_visible()
    cited_sources = evidence.get_by_role("link", name="Open cited source")
    cited_source_urls = [
        cited_sources.nth(index).get_attribute("href") or ""
        for index in range(cited_sources.count())
    ]
    assert any(
        _url_matches_official_root(url, manifest_entry["official_root_url"])
        for url in cited_source_urls
    ), "The detail must cite the reviewed official root for the selected flagship."

    page.get_by_role("link", name="Sign in", exact=True).click()
    page.get_by_label("Email address", exact=True).fill(
        truth_first_staging_environment["E2E_STAGING_EMAIL"]
    )
    page.get_by_label("Password").fill(
        truth_first_staging_environment["E2E_STAGING_PASSWORD"]
    )
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page).to_have_url(f"{base_url}/dashboard")

    original_profile = _get_staging_profile(page)
    assert original_profile is not None, (
        "The dedicated staging student must have a restorable baseline profile."
    )
    evaluation_id = None
    application_id = None
    try:
        page.goto(f"{base_url}/profile", wait_until="networkidle")
        expect(page.get_by_role("heading", name="Build a profile you can trust.")).to_be_visible()
        page.get_by_label("Nationality").fill("Singaporean")
        page.get_by_label("Target degree").select_option(
            TRUTH_FIRST_MATCH_EXPECTATION["target_degree_level"]
        )
        page.get_by_label("Intended field").fill("Public policy")
        page.get_by_role("button", name="Save profile").click()
        expect(page.get_by_role("status")).to_contain_text("Profile saved")

        with page.expect_response(
            lambda response: urlparse(response.url).path == "/api/v1/matches/me"
            and response.request.method == "GET"
        ) as match_response_info:
            page.goto(f"{base_url}/matches", wait_until="networkidle")
        match_payload = match_response_info.value.json()
        evaluation_id = match_payload["evaluation_id"]
        assert evaluation_id
        match_result = next(
            result
            for result in match_payload["results"]
            if result["opportunity"]["id"] == opportunity_id
        )
        assert match_result["score_label"] == TRUTH_FIRST_MATCH_EXPECTATION["score_label"]
        assert (
            match_result["eligibility_status"]
            == TRUTH_FIRST_MATCH_EXPECTATION["eligibility_status"]
        )
        assert match_result["fit_score"] is None
        assert TRUTH_FIRST_MATCH_EXPECTATION["warning"] in match_result["warnings"]
        assert any(match_result["explanation"].values())
        expect(
            page.get_by_role("heading", name="Recommendations you can inspect.")
        ).to_be_visible()
        match_heading = page.get_by_role("heading", name=scholarship_name, exact=True)
        expect(match_heading).to_be_visible()
        match_card = match_heading.locator("xpath=ancestor::article")
        fit_score = match_card.locator(".fit-score")
        expect(fit_score).to_be_visible()
        score = fit_score.locator("strong").inner_text().strip()
        score_label = fit_score.locator("span").inner_text().strip()
        assert score == "--"
        assert score_label == "ineligible"
        expect(match_card.get_by_text("Known eligibility conflict", exact=True)).to_be_visible()
        expect(match_card.locator(".hard-gate")).to_contain_text(
            "known hard eligibility failures"
        )
        expect(
            match_card.get_by_text(TRUTH_FIRST_MATCH_EXPECTATION["warning"], exact=True)
        ).to_be_visible()
        assert match_card.locator(".explanation li").count() > 0
        expect(match_card.locator(".match-disclaimer")).to_contain_text(
            "not a probability"
        )
        expect(match_card.get_by_text("Next steps")).to_be_visible()
        match_card.get_by_role("link", name="Review official opportunity details").click()

        with page.expect_response(
            lambda response: urlparse(response.url).path == "/api/v1/applications"
            and response.request.method == "POST"
        ) as application_response_info:
            page.get_by_role("button", name="Save & track", exact=True).first.click()
        application_response = application_response_info.value
        assert application_response.status == 201, (
            "The protected E2E account must be dedicated to this journey and must not already "
            "contain an application for DAAD EPOS. Pre-existing application data was preserved."
        )
        application_id = application_response.json()["id"]
        assert application_id
        expect(page.get_by_role("status").first).to_contain_text(
            "Saved. Your application plan is ready."
        )
        page.get_by_role("link", name=re.compile("Open application plan")).first.click()
        expect(page.get_by_role("heading", name="Task board")).to_be_visible()
        expect(page.get_by_role("link", name="Open official evidence")).to_be_visible()

        evidence_dir = os.getenv("E2E_EVIDENCE_DIR", "").strip()
        if evidence_dir:
            output_dir = Path(evidence_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(
                path=str(output_dir / "truth-first-application-plan.png"), full_page=True
            )
    finally:
        try:
            if application_id is not None:
                _delete_staging_application(page, application_id)
        finally:
            try:
                if evaluation_id is not None:
                    _delete_staging_match_evaluation(page, evaluation_id)
            finally:
                _restore_staging_profile(page, original_profile)
