"""Tests for Phase 1b.1 Crawlee scaffolding (works without crawlee installed)."""

from __future__ import annotations

import pytest

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
from app.modules.opportunities.source_monitor import (
    FetchedLink,
    FetchedSource,
    SourceFetchError,
)


class _FakeFetcher:
    def __init__(self, result: FetchedSource) -> None:
        self.result = result

    def fetch(self, url: str) -> FetchedSource:
        return self.result


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
def test_crawlee_acquirer_delegates_to_safe_fetcher() -> None:
    fetched = _sample()
    acquirer = CrawleeStaticEvidenceAcquirer(fetcher=_FakeFetcher(fetched))
    result = acquirer.acquire(AcquisitionRequest(url=fetched.url, role_hint=SourceRoleHint.PRIMARY))
    assert result.fetched is fetched
    assert result.artifact.parser_version == "crawlee-static.v1-safe-delegate"
    assert result.artifact.content_hash == "abc"


def test_select_default_acquire_still_works() -> None:
    fetched = _sample()
    acquirer = select_evidence_acquirer(fetcher=_FakeFetcher(fetched))
    result = acquirer.acquire(AcquisitionRequest(url=fetched.url))
    assert result.artifact.parser_version == "legacy-safe-fetcher.v1"
