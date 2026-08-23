"""Tests for Phase 1b.2a multi-URL safe acquisition session."""

from __future__ import annotations

import pytest

from app.modules.catalogue_ingestion.evidence_acquirer import (
    AcquisitionRequest,
    AcquisitionResult,
    LegacySafeEvidenceAcquirer,
)
from app.modules.catalogue_ingestion.safe_multi_url_session import (
    MultiUrlAcquisitionPlan,
    SafeMultiUrlAcquisitionSession,
)
from app.modules.opportunities.source_monitor import (
    FetchedLink,
    FetchedSource,
    SourceFetchError,
)


class _ScriptedFetcher:
    def __init__(self, mapping: dict[str, FetchedSource | Exception]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchedSource:
        self.calls.append(url)
        value = self.mapping[url]
        if isinstance(value, Exception):
            raise value
        return value


def _fetched(url: str) -> FetchedSource:
    return FetchedSource(
        url=url,
        final_url=url,
        content_hash=f"hash-{url}",
        excerpt_text="Eligibility requires official documentation.",
        section_label="Eligibility",
        bytes_read=200,
        normalized_text="Eligibility requires official documentation for applicants.",
        normalized_content_hash=f"norm-{url}",
        content_type="text/html",
        links=(FetchedLink(url=f"{url}/apply", text="Apply"),),
    )


def test_plan_rejects_over_budget_url_count() -> None:
    with pytest.raises(ValueError, match="max_urls"):
        MultiUrlAcquisitionPlan(
            urls=tuple(f"https://example.gov/{i}" for i in range(3)),
            max_urls=2,
        )


def test_plan_rejects_empty_url() -> None:
    with pytest.raises(ValueError, match="empty"):
        MultiUrlAcquisitionPlan(urls=("https://example.gov/a", ""))


def test_session_acquires_all_successful_urls() -> None:
    a = "https://example.gov/a"
    b = "https://example.gov/b"
    fetcher = _ScriptedFetcher({a: _fetched(a), b: _fetched(b)})
    session = SafeMultiUrlAcquisitionSession(
        acquirer=LegacySafeEvidenceAcquirer(fetcher=fetcher)
    )
    outcome = session.run(MultiUrlAcquisitionPlan(urls=(a, b)))
    assert len(outcome.results) == 2
    assert outcome.failures == ()
    assert fetcher.calls == [a, b]
    assert all(isinstance(item, AcquisitionResult) for item in outcome.results)


def test_session_records_failures_and_continues() -> None:
    a = "https://example.gov/a"
    b = "https://example.gov/b"
    fetcher = _ScriptedFetcher(
        {a: SourceFetchError("robots_disallowed"), b: _fetched(b)}
    )
    session = SafeMultiUrlAcquisitionSession(
        acquirer=LegacySafeEvidenceAcquirer(fetcher=fetcher)
    )
    outcome = session.run(MultiUrlAcquisitionPlan(urls=(a, b), stop_on_error=False))
    assert len(outcome.results) == 1
    assert outcome.results[0].artifact.requested_url == b
    assert outcome.failures == ((a, "robots_disallowed"),)


def test_session_stop_on_error() -> None:
    a = "https://example.gov/a"
    b = "https://example.gov/b"
    fetcher = _ScriptedFetcher(
        {a: SourceFetchError("unsafe_source_url"), b: _fetched(b)}
    )
    session = SafeMultiUrlAcquisitionSession(
        acquirer=LegacySafeEvidenceAcquirer(fetcher=fetcher)
    )
    outcome = session.run(MultiUrlAcquisitionPlan(urls=(a, b), stop_on_error=True))
    assert outcome.results == ()
    assert outcome.failures == ((a, "unsafe_source_url"),)
    assert fetcher.calls == [a]


def test_session_rejects_browser_flags_via_acquirer() -> None:
    """Multi-URL session always constructs requests with browser disabled."""

    class _RecordingAcquirer:
        def __init__(self) -> None:
            self.requests: list[AcquisitionRequest] = []

        def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
            self.requests.append(request)
            raise SourceFetchError("not_used")

    acquirer = _RecordingAcquirer()
    session = SafeMultiUrlAcquisitionSession(acquirer=acquirer)
    session.run(MultiUrlAcquisitionPlan(urls=("https://example.gov/x",)))
    assert acquirer.requests[0].allow_browser is False
    assert acquirer.requests[0].allow_document_parser is False
    assert acquirer.requests[0].allow_ocr is False
