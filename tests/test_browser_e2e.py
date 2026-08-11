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
