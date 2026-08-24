"""Tests for the Crawlee scheduling bridge and safe fetch boundary."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.catalogue_ingestion.crawlee_static_acquirer import (
    CrawleeStaticEvidenceAcquirer,
    is_crawlee_installed,
    select_evidence_acquirer,
)
from app.modules.catalogue_ingestion.evidence_acquirer import (
    AcquisitionRequest,
    LegacySafeEvidenceAcquirer,
    SourceRoleHint,
)
from app.modules.catalogue_ingestion.service import CatalogueIngestionService
from app.modules.opportunities.source_monitor import (
    FetchedLink,
    FetchedSource,
    SourceFetchError,
)


class _FakeFetcher:
    def __init__(self, result: FetchedSource) -> None:
        self.result = result
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchedSource:
        self.calls.append(url)
        return self.result


class _FailingFetcher:
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchedSource:
        self.calls.append(url)
        raise SourceFetchError(self.error_code)


def _sample() -> FetchedSource:
    return FetchedSource(
        url="https://example.gov/scholarship",
        final_url="https://example.gov/scholarship",
        content_hash="abc",
        excerpt_text="Eligibility text",
        section_label="Eligibility",
        bytes_read=100,
        normalized_text="Eligibility text for the programme.",
        normalized_content_hash="def",
        content_type="text/html",
        links=(FetchedLink(url="https://example.gov/apply", text="Apply"),),
    )


def test_default_select_returns_legacy() -> None:
    acquirer = select_evidence_acquirer()
    assert isinstance(acquirer, LegacySafeEvidenceAcquirer)


def test_prefer_crawlee_without_package_fails_closed() -> None:
    if is_crawlee_installed():
        pytest.skip("crawlee is installed in this environment")
    with pytest.raises(SourceFetchError, match="crawlee_not_installed"):
        select_evidence_acquirer(prefer_crawlee_static=True)


def test_crawlee_acquirer_construct_fails_without_package() -> None:
    if is_crawlee_installed():
        pytest.skip("crawlee is installed in this environment")
    with pytest.raises(SourceFetchError, match="crawlee_not_installed"):
        CrawleeStaticEvidenceAcquirer(fetcher=_FakeFetcher(_sample()))


@pytest.mark.skipif(not is_crawlee_installed(), reason="optional crawlee not installed")
def test_crawlee_acquirer_schedules_one_request_through_safe_fetcher() -> None:
    fetched = _sample()
    fetcher = _FakeFetcher(fetched)
    acquirer = CrawleeStaticEvidenceAcquirer(fetcher=fetcher)
    result = acquirer.acquire(AcquisitionRequest(url=fetched.url, role_hint=SourceRoleHint.PRIMARY))

    # Crawlee schedules the handler, but the only source request is the injected
    # safe boundary. No Crawlee request-context HTTP method is used.
    assert fetcher.calls == [fetched.url]
    assert result.fetched is fetched
    assert result.artifact.parser_version == "crawlee-static.v2-safe-bridge"
    assert result.artifact.content_hash == "abc"


@pytest.mark.skipif(not is_crawlee_installed(), reason="optional crawlee not installed")
def test_crawlee_bridge_preserves_safe_fetcher_rejection() -> None:
    fetcher = _FailingFetcher("ssrf_private_address")
    acquirer = CrawleeStaticEvidenceAcquirer(fetcher=fetcher)

    with pytest.raises(SourceFetchError, match="ssrf_private_address"):
        acquirer.acquire(AcquisitionRequest(url="https://example.gov/scholarship"))

    assert fetcher.calls == ["https://example.gov/scholarship"]


def test_select_default_acquire_still_works() -> None:
    fetched = _sample()
    acquirer = select_evidence_acquirer(fetcher=_FakeFetcher(fetched))
    result = acquirer.acquire(AcquisitionRequest(url=fetched.url))
    assert result.artifact.parser_version == "legacy-safe-fetcher.v1"


@pytest.mark.skipif(not is_crawlee_installed(), reason="optional crawlee not installed")
def test_service_wires_opt_in_static_requests_through_crawlee(db_session) -> None:
    fetched = _sample()
    fetcher = _FakeFetcher(fetched)
    service = CatalogueIngestionService(
        db_session,
        Settings(catalogue_crawlee_static_enabled=True),
        fetcher=fetcher,
    )

    result = service.evidence_acquirer.acquire(AcquisitionRequest(url=fetched.url))

    assert isinstance(service.evidence_acquirer, CrawleeStaticEvidenceAcquirer)
    assert fetcher.calls == [fetched.url]
    assert result.artifact.parser_version == "crawlee-static.v2-safe-bridge"
