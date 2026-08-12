"""Citation-first assistant browser journey; requires a configured live app URL."""

import os

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


@pytest.fixture
def live_base_url() -> str:
    base_url = os.getenv("E2E_BASE_URL")
    if not base_url:
        pytest.skip("Set E2E_BASE_URL to run browser end-to-end tests.")
    return base_url.rstrip("/")


def test_student_can_inspect_citations_save_feedback_and_confirm_application(
    page: Page, live_base_url: str
) -> None:
    """The assistant must not silently create application workspace records."""
    user = {
        "id": "eaa6d577-9122-465a-bf7d-7f5a5eecc0bb",
        "email": "assistant-browser@example.com",
        "role": "student",
        "is_active": True,
        "email_verified_at": "2099-01-01T00:00:00Z",
        "created_at": "2099-01-01T00:00:00Z",
    }
    opportunity_id = "f5d655d8-4a32-4756-ae0d-7683dd1f09f0"
    answer = {
        "id": "85b013d8-c7aa-4f3a-852c-d4b2b4b19ac3",
        "conversation_id": "1069ee74-1e60-4ca0-b298-d91b2c57e01a",
        "status": "completed",
        "provider": "evidence-template",
        "model_version": "evidence-template-v1",
        "prompt_template_version": "phase6.citation-first.v1",
        "retrieval_version": "phase6.structured-official.v1",
        "evidence_packet_id": "8f9d743e-a8a9-4a35-95c3-ff45c7660a64",
        "created_at": "2099-01-01T00:00:00Z",
        "saved_to_workspace": False,
        "response": {
            "answer": "I found one verified catalogue record that may help.",
            "answer_type": "scholarship search",
            "confidence": "medium",
            "facts": [
                {
                    "text": "Browser Journey Scholarship is listed for masters study in Malaysia.",
                    "citation_ids": ["cdf65f91-5db1-4dca-b7d2-268dcfe7916d"],
                }
            ],
            "possible_matches": [
                {
                    "opportunity_id": opportunity_id,
                    "name": "Browser Journey Scholarship",
                    "reason": (
                        "Profile signals considered: target degree; "
                        "confirm every official condition."
                    ),
                    "citation_ids": ["cdf65f91-5db1-4dca-b7d2-268dcfe7916d"],
                }
            ],
            "requirements_to_check": [],
            "private_progress": [],
            "next_actions": ["Open the official source for each possible match."],
            "warnings": [],
            "citations": [
                {
                    "id": "cdf65f91-5db1-4dca-b7d2-268dcfe7916d",
                    "opportunity_id": opportunity_id,
                    "source_id": "b69fb49e-4012-4104-8715-e9788e1a0d8c",
                    "source_excerpt_id": None,
                    "claim": "Browser Journey Scholarship is listed for masters study in Malaysia.",
                    "claim_key": "degree_country",
                    "source_title": "Official scholarship call",
                    "source_url": "https://example.edu/official-scholarship-call",
                    "excerpt": "The official call lists the programme and application conditions.",
                    "last_verified_at": "2099-01-01T00:00:00Z",
                    "freshness": "current",
                }
            ],
            "abstained_reason": None,
        },
    }

    page.route(
        "**/api/v1/auth/refresh",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            json={"access_token": "test-access-token", "expires_in": 900, "user": user},
        ),
    )

    def assistant_route(route) -> None:
        if route.request.url.endswith("/preferences"):
            route.fulfill(
                status=200,
                content_type="application/json",
                json={
                    "consented": True,
                    "history_enabled": True,
                    "history_retention_days": 30,
                    "feedback_retention_days": 365,
                },
            )
        elif route.request.url.endswith("/conversations"):
            route.fulfill(status=200, content_type="application/json", json=[])
        elif route.request.url.endswith("/answers"):
            route.fulfill(status=200, content_type="application/json", json=answer)
        else:
            route.fulfill(status=204)

    page.route("**/api/v1/assistant/**", assistant_route)
    page.route(
        "**/api/v1/applications",
        lambda route: route.fulfill(
            status=201, content_type="application/json", json={"id": "new-id"}
        ),
    )

    page.goto(f"{live_base_url}/assistant", wait_until="networkidle")
    page.get_by_label(
        "Ask about scholarships, requirements, funding, deadlines, or your progress"
    ).fill("Find masters scholarships in Malaysia")
    page.get_by_role("button", name="Ask assistant").click()

    expect(page.get_by_text("Verified facts")).to_be_visible()
    expect(page.get_by_text("Official scholarship call")).to_be_visible()
    expect(
        page.get_by_role("link", name="Open official source: Official scholarship call")
    ).to_have_attribute("href", "https://example.edu/official-scholarship-call")
    page.get_by_role("button", name="Save result").click()
    expect(page.get_by_role("status")).to_contain_text("Saved privately")
    page.get_by_role("button", name="helpful", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("feedback was recorded")

    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Create application plan").click()
    expect(page.get_by_role("status")).to_contain_text("Created a private application plan")
