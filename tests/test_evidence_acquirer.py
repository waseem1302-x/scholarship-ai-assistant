"""Unit tests for the EvidenceAcquirer boundary (Phase 1a)."""

from __future__ import annotations

import pytest

from app.modules.catalogue_ingestion.evidence_acquirer import (
    EVIDENCE_ACQUIRER_CONTRACT_VERSION,
    AcquiredArtifact,
    AcquisitionRequest,
    AcquisitionTier,
    AcquisitionTiers,
    LegacySafeEvidenceAcquirer,
    SourceRoleHint,
    default_evidence_acquirer,
)
from app.modules.opportunities.source_monitor import (
    FetchedLink,
    FetchedSource,
    SourceFetchError,
)


class _FakeFetcher:
    def __init__(self, result: FetchedSource | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchedSource:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _sample_fetched(*, url: str = "https://example.gov/scholarship") -> FetchedSource:
    return FetchedSource(
        url=url,
        final_url=url,
        content_hash="abc123",
        excerpt_text="Eligibility requires citizenship.",
        section_label="Eligibility",
        bytes_read=1200,
        normalized_text="Eligibility requires citizenship. Funding covers tuition.",
        normalized_content_hash="def456",
        content_type="text/html",
        links=(FetchedLink(url=f"{url}/apply", text="Apply", title="Apply now"),),
    )


def test_legacy_acquirer_returns_static_http_artifact() -> None:
    fetched = _sample_fetched()
    acquirer = LegacySafeEvidenceAcquirer(fetcher=_FakeFetcher(result=fetched))
    result = acquirer.acquire(AcquisitionRequest(url=fetched.url, role_hint=SourceRoleHint.PRIMARY))

    assert result.fetched is fetched
    artifact = result.artifact
    assert isinstance(artifact, AcquiredArtifact)
    assert artifact.requested_url == fetched.url
    assert artifact.final_url == fetched.final_url
    assert artifact.content_hash == "abc123"
    assert artifact.normalized_content_hash == "def456"
    assert artifact.normalized_text == fetched.normalized_text
    assert artifact.bytes_read == 1200
    assert artifact.tier is AcquisitionTier.STATIC_HTTP
    assert artifact.tier is AcquisitionTiers.STATIC_HTTP
    assert artifact.role_hint is SourceRoleHint.PRIMARY
    assert artifact.acquirer_contract_version == EVIDENCE_ACQUIRER_CONTRACT_VERSION
    assert artifact.parser_version == "legacy-safe-fetcher.v1"
    assert artifact.links == fetched.links
    assert artifact.retrieved_at.tzinfo is not None


def test_legacy_acquirer_rejects_browser_flag() -> None:
    acquirer = LegacySafeEvidenceAcquirer(fetcher=_FakeFetcher(result=_sample_fetched()))
    with pytest.raises(SourceFetchError, match="browser_acquisition_not_enabled"):
        acquirer.acquire(
            AcquisitionRequest(
                url="https://example.gov/scholarship",
                allow_browser=True,
            )
        )


def test_legacy_acquirer_rejects_document_and_ocr_flags() -> None:
    acquirer = LegacySafeEvidenceAcquirer(fetcher=_FakeFetcher(result=_sample_fetched()))
    with pytest.raises(SourceFetchError, match="document_parser_not_enabled"):
        acquirer.acquire(
            AcquisitionRequest(
                url="https://example.gov/doc.pdf",
                allow_document_parser=True,
            )
        )
    with pytest.raises(SourceFetchError, match="ocr_not_enabled"):
        acquirer.acquire(
            AcquisitionRequest(
                url="https://example.gov/scan.pdf",
                allow_ocr=True,
            )
        )


def test_legacy_acquirer_propagates_fetch_errors() -> None:
    acquirer = LegacySafeEvidenceAcquirer(
        fetcher=_FakeFetcher(error=SourceFetchError("robots_disallowed"))
    )
    with pytest.raises(SourceFetchError, match="robots_disallowed"):
        acquirer.acquire(AcquisitionRequest(url="https://example.gov/blocked"))


def test_legacy_acquirer_enforces_max_bytes_on_plain_fetcher() -> None:
    large = _sample_fetched()
    large = FetchedSource(
        url=large.url,
        final_url=large.final_url,
        content_hash=large.content_hash,
        excerpt_text=large.excerpt_text,
        section_label=large.section_label,
        bytes_read=50_000,
        normalized_text=large.normalized_text,
        normalized_content_hash=large.normalized_content_hash,
        content_type=large.content_type,
        links=large.links,
    )
    acquirer = LegacySafeEvidenceAcquirer(fetcher=_FakeFetcher(result=large))
    with pytest.raises(SourceFetchError, match="source_too_large"):
        acquirer.acquire(AcquisitionRequest(url=large.url, max_bytes=10_000))


def test_acquisition_request_rejects_empty_url() -> None:
    with pytest.raises(ValueError, match="url is required"):
        AcquisitionRequest(url="")


def test_acquisition_request_rejects_non_positive_max_bytes() -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        AcquisitionRequest(url="https://example.gov/x", max_bytes=0)


def test_default_factory_returns_legacy_acquirer() -> None:
    acquirer = default_evidence_acquirer()
    assert isinstance(acquirer, LegacySafeEvidenceAcquirer)


def test_tier_alias_is_identical() -> None:
    assert AcquisitionTiers is AcquisitionTier
