"""Opt-in browser rendering fallback behind the catalogue source-safety policy."""

from __future__ import annotations

import hashlib
import urllib.parse
import urllib.robotparser
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import ClassVar, Protocol

from app.modules.opportunities.source_monitor import (
    UNSAFE_EVIDENCE_CONTROL_CHARACTERS,
    FetchedSource,
    NormalizedSourcePayload,
    SafeSourceFetcher,
    SourceFetchError,
    extract_evidence_section,
    extract_html_links,
    is_low_information_source_text,
    validate_monitor_url,
)


class BrowserRenderer(Protocol):
    def robots_allowed(
        self,
        url: str,
        *,
        user_agent: str,
        timeout_seconds: int,
        request_validator: Callable[[str], None],
    ) -> bool: ...

    def render(
        self,
        url: str,
        *,
        user_agent: str,
        timeout_seconds: int,
        request_validator: Callable[[str], None],
    ) -> tuple[str, bytes, str]: ...


class PlaywrightBrowserRenderer:
    """Render one page in a short-lived, headless Chromium context."""

    @staticmethod
    def _browser_user_agent(browser_version: str, crawler_user_agent: str) -> str:
        version = browser_version.split(" ", 1)[-1]
        return (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{version} Safari/537.36 {crawler_user_agent}"
        )

    def robots_allowed(
        self,
        url: str,
        *,
        user_agent: str,
        timeout_seconds: int,
        request_validator: Callable[[str], None],
    ) -> bool:
        parsed = urllib.parse.urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        request_validator(robots_url)
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise SourceFetchError("browser_runtime_not_installed") from exc

        timeout_ms = timeout_seconds * 1_000
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=["--disable-dev-shm-usage"],
                )
                try:
                    context = browser.new_context(
                        accept_downloads=False,
                        java_script_enabled=False,
                        service_workers="block",
                        user_agent=self._browser_user_agent(browser.version, user_agent),
                    )
                    page = context.new_page()
                    page.route("**/*", self._safe_route(request_validator))
                    response = page.goto(
                        robots_url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    if response is None:
                        raise SourceFetchError("robots_unreachable")
                    request_validator(page.url)
                    if response.status == 429 or response.status >= 500:
                        raise SourceFetchError(f"robots_unreachable: http_{response.status}")
                    if 400 <= response.status <= 499:
                        return True
                    if not 200 <= response.status <= 299:
                        raise SourceFetchError(f"robots_check_failed: http_{response.status}")
                    rules = page.locator("body").inner_text(timeout=timeout_ms)
                finally:
                    browser.close()
        except SourceFetchError:
            raise
        except PlaywrightTimeoutError as exc:
            raise SourceFetchError("robots_unreachable") from exc
        except PlaywrightError as exc:
            raise SourceFetchError("robots_unreachable") from exc

        robots = urllib.robotparser.RobotFileParser(robots_url)
        robots.parse(rules.splitlines())
        return robots.can_fetch(user_agent, url)

    @staticmethod
    def _safe_route(request_validator: Callable[[str], None]):
        def route_request(route) -> None:
            try:
                request_validator(route.request.url)
            except SourceFetchError:
                route.abort()
                return
            route.continue_()

        return route_request

    def render(
        self,
        url: str,
        *,
        user_agent: str,
        timeout_seconds: int,
        request_validator: Callable[[str], None],
    ) -> tuple[str, bytes, str]:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise SourceFetchError("browser_runtime_not_installed") from exc

        request_count = 0

        def route_request(route) -> None:
            nonlocal request_count
            request_count += 1
            request = route.request
            if request_count > 200 or request.resource_type in {"font", "image", "media"}:
                route.abort()
                return
            try:
                request_validator(request.url)
            except SourceFetchError:
                route.abort()
                return
            route.continue_()

        timeout_ms = timeout_seconds * 1_000
        expects_download = urllib.parse.urlparse(url).path.casefold().endswith(".pdf")
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=["--disable-dev-shm-usage"],
                )
                try:
                    context = browser.new_context(
                        accept_downloads=expects_download,
                        java_script_enabled=True,
                        service_workers="block",
                        user_agent=self._browser_user_agent(browser.version, user_agent),
                    )
                    page = context.new_page()
                    page.route("**/*", route_request)
                    if expects_download:
                        with page.expect_download(timeout=timeout_ms) as download_info:
                            try:
                                page.goto(url, wait_until="commit", timeout=timeout_ms)
                            except PlaywrightError as exc:
                                if "Download is starting" not in str(exc):
                                    raise
                        download = download_info.value
                        final_url = download.url
                        request_validator(final_url)
                        download_path = download.path()
                        if download_path is None:
                            raise SourceFetchError("browser_download_unavailable")
                        payload = Path(download_path).read_bytes()
                        return final_url, payload, "application/pdf"
                    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    if response is None:
                        raise SourceFetchError("browser_source_unreachable")
                    if response.status >= 400:
                        raise SourceFetchError(f"browser_source_http_error: http_{response.status}")
                    with suppress(PlaywrightTimeoutError):
                        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10_000))
                    final_url = page.url
                    request_validator(final_url)
                    payload = page.content().encode("utf-8")
                finally:
                    browser.close()
        except SourceFetchError:
            raise
        except PlaywrightTimeoutError as exc:
            raise SourceFetchError("browser_source_timeout") from exc
        except PlaywrightError as exc:
            raise SourceFetchError("browser_source_failed") from exc
        return final_url, payload, "text/html"


class BrowserFallbackSourceFetcher:
    """Use browser rendering only after the safe static boundary cannot supply HTML."""

    _FALLBACK_CODES: ClassVar[set[str]] = {
        "source_access_denied",
        "source_has_no_extractable_evidence",
    }

    def __init__(
        self,
        *,
        static_fetcher: SafeSourceFetcher,
        renderer: BrowserRenderer | None = None,
    ) -> None:
        self.static_fetcher = static_fetcher
        self.renderer = renderer or PlaywrightBrowserRenderer()
        self._browser_robots_allowed_origins: set[str] = set()

    def fetch(self, url: str) -> FetchedSource:
        return self.fetch_with_limit(url, max_bytes=self.static_fetcher.policy_for(url).max_bytes)

    def fetch_with_limit(self, url: str, *, max_bytes: int) -> FetchedSource:
        try:
            return self._static_fetch_with_limit(url, max_bytes=max_bytes)
        except SourceFetchError as exc:
            failure_code = str(exc).split(":", 1)[0]
            if failure_code == "robots_unreachable":
                self._assert_browser_robots_allowed(url)
            elif failure_code not in self._FALLBACK_CODES:
                raise
        return self._browser_fetch(url, max_bytes=max_bytes)

    def _assert_browser_robots_allowed(self, url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._browser_robots_allowed_origins:
            return
        policy = self.static_fetcher.policy_for(url)
        if not self.renderer.robots_allowed(
            url,
            user_agent=policy.user_agent,
            timeout_seconds=policy.timeout_seconds,
            request_validator=validate_monitor_url,
        ):
            raise SourceFetchError("robots_disallowed")
        self._browser_robots_allowed_origins.add(origin)

    def _static_fetch_with_limit(self, url: str, *, max_bytes: int) -> FetchedSource:
        original = self.static_fetcher
        bounded_fetch = getattr(original, "fetch_with_limit", None)
        if callable(bounded_fetch):
            return bounded_fetch(url, max_bytes=max_bytes)
        policies = {
            host: policy.__class__(
                host=policy.host,
                check_interval_days=policy.check_interval_days,
                timeout_seconds=policy.timeout_seconds,
                max_bytes=min(policy.max_bytes, max_bytes),
                user_agent=policy.user_agent,
            )
            for host, policy in original.crawl_policies.items()
        }
        limited = SafeSourceFetcher(
            timeout_seconds=original.timeout_seconds,
            max_bytes=min(original.max_bytes, max_bytes),
            crawl_policies=policies,
            payload_normalizer=original.payload_normalizer,
        )
        limited.opener = original.opener
        limited._robots = original._robots
        return limited.fetch(url)

    def _browser_fetch(self, url: str, *, max_bytes: int) -> FetchedSource:
        validate_monitor_url(url)
        policy = self.static_fetcher.policy_for(url)
        # The failed static request already checked robots. Repeat it explicitly
        # so browser rendering never becomes an alternate robots bypass.
        origin = f"{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).netloc}"
        if origin not in self._browser_robots_allowed_origins:
            self.static_fetcher._assert_robots_allowed(url, policy)
        final_url, payload, content_type = self.renderer.render(
            url,
            user_agent=policy.user_agent,
            timeout_seconds=policy.timeout_seconds,
            request_validator=validate_monitor_url,
        )
        validate_monitor_url(final_url)
        if len(payload) > max_bytes:
            raise SourceFetchError(f"source_too_large: exceeded {max_bytes} bytes")
        normalized = self.static_fetcher.payload_normalizer(payload, content_type)
        if isinstance(normalized, NormalizedSourcePayload):
            evidence_text = normalized.text
            conversion_metadata = dict(normalized.conversion_metadata)
            normalizer_version = normalized.parser_version
        elif isinstance(normalized, str):
            evidence_text = normalized
            conversion_metadata = {}
            normalizer_version = getattr(
                self.static_fetcher.payload_normalizer,
                "parser_version",
                "legacy-safe-fetcher.v1",
            )
        else:
            raise SourceFetchError("source_payload_normalization_invalid")
        if UNSAFE_EVIDENCE_CONTROL_CHARACTERS.search(evidence_text):
            raise SourceFetchError("source_payload_contains_unsafe_control_characters")
        if len(evidence_text) < 20 or is_low_information_source_text(evidence_text):
            raise SourceFetchError("source_has_no_extractable_evidence")
        digest = hashlib.sha256(evidence_text.encode()).hexdigest()
        section = extract_evidence_section(evidence_text)
        content_hash = hashlib.sha256(
            (section.text if section else evidence_text).encode()
        ).hexdigest()
        return FetchedSource(
            url=url,
            final_url=final_url,
            content_hash=content_hash,
            excerpt_text=section.text[:500] if section else evidence_text[:500],
            section_label=section.label if section else None,
            bytes_read=len(payload),
            normalized_text=evidence_text,
            normalized_content_hash=digest,
            content_type=content_type,
            links=extract_html_links(payload, base_url=final_url),
            parser_version=f"playwright-browser.v1+{normalizer_version}",
            conversion_metadata=conversion_metadata,
        )


__all__ = [
    "BrowserFallbackSourceFetcher",
    "BrowserRenderer",
    "PlaywrightBrowserRenderer",
]
