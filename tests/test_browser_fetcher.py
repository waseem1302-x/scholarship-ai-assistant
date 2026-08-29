from __future__ import annotations

import hashlib

import pytest

from app.modules.catalogue_ingestion.browser_fetcher import (
    BrowserFallbackSourceFetcher,
)
from app.modules.catalogue_ingestion.evidence_acquirer import (
    AcquisitionRequest,
    AcquisitionTier,
    LegacySafeEvidenceAcquirer,
)
from app.modules.opportunities.source_monitor import SafeSourceFetcher, SourceFetchError

URL = "https://example.gov/scholarship"


class FailingStaticFetcher(SafeSourceFetcher):
    def __init__(self, code: str) -> None:
        super().__init__()
        self.code = code
        self.robots_checks: list[str] = []

    def fetch(self, url: str):
        self._assert_robots_allowed(url, self.policy_for(url))
        raise SourceFetchError(self.code)

    def fetch_with_limit(self, url: str, *, max_bytes: int):
        return self.fetch(url)

    def _assert_robots_allowed(self, url, policy):
        self.robots_checks.append(url)


class FakeRenderer:
    def __init__(self, payload: bytes, *, robots_allowed: bool = True) -> None:
        self.payload = payload
        self.calls: list[str] = []
        self.robots_allowed_result = robots_allowed

    def robots_allowed(self, url, *, user_agent, timeout_seconds, request_validator):
        return self.robots_allowed_result

    def render(self, url, *, user_agent, timeout_seconds, request_validator):
        self.calls.append(url)
        return url, self.payload, "text/html"


def test_browser_fallback_renders_access_denied_html_and_preserves_lineage(monkeypatch) -> None:
    static = FailingStaticFetcher("source_access_denied: http_412")
    renderer = FakeRenderer(
        b"<html><main><h1>Official Scholarship</h1>"
        b"<p>Eligibility and funding details.</p>"
        b"<a href='/apply'>How to apply</a></main></html>"
    )
    monkeypatch.setattr(
        "app.modules.catalogue_ingestion.browser_fetcher.validate_monitor_url",
        lambda _url: None,
    )
    fetcher = BrowserFallbackSourceFetcher(static_fetcher=static, renderer=renderer)

    fetched = fetcher.fetch_with_limit(URL, max_bytes=10_000)
    acquired = LegacySafeEvidenceAcquirer(fetcher=fetcher).acquire(
        AcquisitionRequest(url=URL)
    )

    assert renderer.calls == [URL, URL]
    assert static.robots_checks == [URL, URL, URL, URL]
    assert fetched.parser_version.startswith("playwright-browser.v1+")
    assert fetched.normalized_content_hash == hashlib.sha256(
        fetched.normalized_text.encode()
    ).hexdigest()
    assert fetched.links[0].url == "https://example.gov/apply"
    assert acquired.artifact.tier is AcquisitionTier.BROWSER


def test_browser_fallback_does_not_bypass_robots_or_non_renderable_failures(monkeypatch) -> None:
    renderer = FakeRenderer(b"<main>Should not render</main>")
    static = FailingStaticFetcher("robots_disallowed")
    monkeypatch.setattr(
        "app.modules.catalogue_ingestion.browser_fetcher.validate_monitor_url",
        lambda _url: None,
    )
    fetcher = BrowserFallbackSourceFetcher(static_fetcher=static, renderer=renderer)

    with pytest.raises(SourceFetchError, match="robots_disallowed"):
        fetcher.fetch(URL)

    assert renderer.calls == []


def test_browser_fallback_enforces_rendered_payload_limit(monkeypatch) -> None:
    static = FailingStaticFetcher("source_access_denied: http_412")
    renderer = FakeRenderer(b"<main>Official scholarship evidence</main>")
    monkeypatch.setattr(
        "app.modules.catalogue_ingestion.browser_fetcher.validate_monitor_url",
        lambda _url: None,
    )
    fetcher = BrowserFallbackSourceFetcher(static_fetcher=static, renderer=renderer)

    with pytest.raises(SourceFetchError, match="source_too_large"):
        fetcher.fetch_with_limit(URL, max_bytes=10)


def test_browser_fallback_can_verify_robots_when_static_tls_probe_fails(monkeypatch) -> None:
    static = FailingStaticFetcher("robots_unreachable")
    renderer = FakeRenderer(b"<main>Official scholarship evidence</main>")
    monkeypatch.setattr(
        "app.modules.catalogue_ingestion.browser_fetcher.validate_monitor_url",
        lambda _url: None,
    )
    fetcher = BrowserFallbackSourceFetcher(static_fetcher=static, renderer=renderer)

    fetched = fetcher.fetch(URL)

    assert fetched.parser_version.startswith("playwright-browser.v1+")
    assert renderer.calls == [URL]


def test_browser_fallback_respects_browser_verified_robots_disallow(monkeypatch) -> None:
    static = FailingStaticFetcher("robots_unreachable")
    renderer = FakeRenderer(
        b"<main>Official scholarship evidence</main>", robots_allowed=False
    )
    monkeypatch.setattr(
        "app.modules.catalogue_ingestion.browser_fetcher.validate_monitor_url",
        lambda _url: None,
    )
    fetcher = BrowserFallbackSourceFetcher(static_fetcher=static, renderer=renderer)

    with pytest.raises(SourceFetchError, match="robots_disallowed"):
        fetcher.fetch(URL)

    assert renderer.calls == []
