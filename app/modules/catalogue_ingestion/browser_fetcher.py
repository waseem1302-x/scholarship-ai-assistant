"""Policy-restricted Playwright rendering for JavaScript-only official pages."""

from __future__ import annotations

import hashlib
from contextlib import suppress
from urllib.parse import urlsplit

from app.modules.catalogue_ingestion.acquisition_fetcher import (
    CATALOGUE_CONVERSION_VERSION,
    CatalogueFetchedSource,
    convert_catalogue_payload,
)
from app.modules.opportunities.source_monitor import (
    SafeSourceFetcher,
    SourceFetchError,
    extract_evidence_section,
    is_authentication_destination,
    validate_monitor_url,
)


class PlaywrightBrowserSourceFetcher:
    """Render one authorized URL while preventing cross-origin navigation."""

    def __init__(self, safety_fetcher: SafeSourceFetcher) -> None:
        self.safety_fetcher = safety_fetcher

    def fetch(self, url: str) -> CatalogueFetchedSource:
        return self.fetch_with_limit(url, max_bytes=self.safety_fetcher.policy_for(url).max_bytes)

    def fetch_with_limit(self, url: str, *, max_bytes: int) -> CatalogueFetchedSource:
        if max_bytes < 1:
            raise SourceFetchError("crawl_byte_budget_exceeded")
        validate_monitor_url(url)
        policy = self.safety_fetcher.policy_for(url)
        effective_max = min(policy.max_bytes, max_bytes)
        self.safety_fetcher._assert_robots_allowed(url, policy)
        origin = _origin(url)

        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright

            with sync_playwright() as runtime:
                browser = runtime.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        user_agent=policy.user_agent,
                        service_workers="block",
                    )
                    page = context.new_page()

                    def guard_request(route) -> None:
                        request_url = route.request.url
                        if request_url.startswith(("data:", "blob:")):
                            route.continue_()
                            return
                        try:
                            validate_monitor_url(request_url)
                        except SourceFetchError:
                            route.abort()
                            return
                        if route.request.is_navigation_request() and _origin(request_url) != origin:
                            route.abort()
                            return
                        route.continue_()

                    page.route("**/*", guard_request)
                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=policy.timeout_seconds * 1_000,
                    )
                    with suppress(PlaywrightTimeoutError):
                        page.wait_for_load_state(
                            "networkidle",
                            timeout=min(policy.timeout_seconds * 1_000, 10_000),
                        )
                    final_url = page.url
                    validate_monitor_url(final_url)
                    if _origin(final_url) != origin:
                        raise SourceFetchError("browser_redirect_left_verified_domain")
                    if is_authentication_destination(final_url):
                        raise SourceFetchError("source_authentication_required")
                    payload = page.content().encode("utf-8")
                finally:
                    browser.close()
        except SourceFetchError:
            raise
        except ImportError as exc:
            raise SourceFetchError("browser_renderer_unavailable") from exc
        except (PlaywrightError, OSError) as exc:
            raise SourceFetchError(f"browser_render_failed: {type(exc).__name__}") from exc

        if len(payload) > effective_max:
            raise SourceFetchError("crawl_byte_budget_exceeded")
        converted = convert_catalogue_payload(
            payload,
            content_type="text/html",
            final_url=final_url,
        )
        text = converted.text.strip()
        if len(" ".join(text.split())) < 20:
            raise SourceFetchError("browser_render_has_no_extractable_evidence")
        section = extract_evidence_section(text)
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        return CatalogueFetchedSource(
            url=url,
            final_url=final_url,
            content_hash=content_hash,
            excerpt_text=section.text[:500] if section else text[:500],
            section_label=section.label if section else None,
            bytes_read=len(payload),
            normalized_text=text,
            normalized_content_hash=content_hash,
            content_type="text/html",
            links=converted.links,
            original_artifact_hash=hashlib.sha256(payload).hexdigest(),
            sniffed_content_type="text/html",
            conversion_version=CATALOGUE_CONVERSION_VERSION,
            canonical_url_hint=converted.canonical_url_hint,
            language_hints=converted.language_hints,
        )


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    return parsed.scheme.casefold(), (parsed.hostname or "").casefold(), parsed.port


__all__ = ["PlaywrightBrowserSourceFetcher"]
