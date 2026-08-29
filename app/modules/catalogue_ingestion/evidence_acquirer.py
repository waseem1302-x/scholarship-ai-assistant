"""Replaceable evidence acquisition boundary (blueprint §5).

Product code depends on ``EvidenceAcquirer``. Network safety remains centralized
in ``SafeSourceFetcher`` (or a future adapter that enforces the same policy).
Crawlee, Playwright acquisition, and Docling are out of scope for this module
until later phases land behind this protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from app.modules.opportunities.source_monitor import (
    FetchedLink,
    FetchedSource,
    SafeSourceFetcher,
    SourceFetcher,
    SourceFetchError,
)

EVIDENCE_ACQUIRER_CONTRACT_VERSION = "evidence-acquirer.v1"


class AcquisitionTier(StrEnum):
    """Cost ladder tier from the engineering blueprint.

    Only ``CACHE`` and ``STATIC_HTTP`` are exercised by the legacy adapter in
    this phase. Browser, document, and OCR tiers are reserved for later work.
    """

    CACHE = "cache"
    STATIC_HTTP = "static_http"
    BROWSER = "browser"
    DOCUMENT = "document"
    OCR = "ocr"


# Compatibility alias (older draft name)
AcquisitionTiers = AcquisitionTier


class SourceRoleHint(StrEnum):
    """Optional role hint supplied by the operator or planner (not authority)."""

    UNKNOWN = "unknown"
    OVERVIEW = "overview"
    CYCLE_GUIDELINE = "cycle_guideline"
    ROUTE = "route"
    DEGREE_TRACK = "degree_track"
    INSTITUTION = "institution"
    PROGRAMME = "programme"
    FUNDING = "funding"
    DOCUMENTS = "documents"
    DEADLINE = "deadline"
    APPLICATION_PORTAL = "application_portal"
    RESULT_NOTICE = "result_notice"
    PRIMARY = "primary"
    SUPPORTING = "supporting"


@dataclass(frozen=True, slots=True)
class AcquisitionRequest:
    """One official URL acquisition request with hard budgets."""

    url: str
    role_hint: SourceRoleHint = SourceRoleHint.UNKNOWN
    max_bytes: int | None = None
    allow_browser: bool = False
    allow_document_parser: bool = False
    allow_ocr: bool = False

    def __post_init__(self) -> None:
        if not self.url or not str(self.url).strip():
            raise ValueError("url is required")
        if self.max_bytes is not None and self.max_bytes < 1:
            raise ValueError("max_bytes must be positive when set")


@dataclass(frozen=True, slots=True)
class AcquiredArtifact:
    """Immutable fetch result ready for content-addressed persistence.

    Raw bytes are intentionally omitted from this in-memory record so callers
    decide persistence (Blob / DB) without forcing every adapter to buffer
    large payloads twice. Hashes and normalized text remain authoritative for
    citation checks.
    """

    requested_url: str
    final_url: str
    content_type: str
    content_hash: str
    normalized_content_hash: str | None
    normalized_text: str | None
    excerpt_text: str | None
    bytes_read: int
    links: tuple[FetchedLink, ...]
    tier: AcquisitionTier
    role_hint: SourceRoleHint
    retrieved_at: datetime
    acquirer_contract_version: str = EVIDENCE_ACQUIRER_CONTRACT_VERSION
    parser_version: str = "legacy-safe-fetcher.v1"


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    """Successful acquisition outcome for one request."""

    artifact: AcquiredArtifact
    fetched: FetchedSource


class EvidenceAcquirer(Protocol):
    """Internal acquisition engine. Implementations must not bypass URL policy."""

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        """Fetch one official URL and return an immutable artifact record."""


class LegacySafeEvidenceAcquirer:
    """Default acquirer: existing ``SafeSourceFetcher`` only (static HTTP tier).

    Browser, document, and OCR flags are rejected rather than silently ignored
    so callers cannot assume capabilities that this phase does not provide.
    """

    def __init__(self, *, fetcher: SourceFetcher | None = None) -> None:
        self.fetcher = fetcher or SafeSourceFetcher()

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        if request.allow_browser:
            raise SourceFetchError("browser_acquisition_not_enabled")
        if request.allow_document_parser:
            raise SourceFetchError("document_parser_not_enabled")
        if request.allow_ocr:
            raise SourceFetchError("ocr_not_enabled")

        if request.max_bytes is not None:
            fetched = self._fetch_with_optional_limit(request.url, max_bytes=request.max_bytes)
        else:
            fetched = self.fetcher.fetch(request.url)

        now = datetime.now(UTC)
        tier = (
            AcquisitionTier.BROWSER
            if fetched.parser_version.startswith("playwright-browser.")
            else AcquisitionTier.STATIC_HTTP
        )
        artifact = AcquiredArtifact(
            requested_url=fetched.url,
            final_url=fetched.final_url,
            content_type=fetched.content_type,
            content_hash=fetched.content_hash,
            normalized_content_hash=fetched.normalized_content_hash,
            normalized_text=fetched.normalized_text,
            excerpt_text=fetched.excerpt_text,
            bytes_read=fetched.bytes_read,
            links=fetched.links,
            tier=tier,
            role_hint=request.role_hint,
            retrieved_at=now,
            parser_version=fetched.parser_version,
        )
        return AcquisitionResult(artifact=artifact, fetched=fetched)

    def _fetch_with_optional_limit(self, url: str, *, max_bytes: int) -> FetchedSource:
        bounded = getattr(self.fetcher, "fetch_with_limit", None)
        if callable(bounded):
            return bounded(url, max_bytes=max_bytes)
        if isinstance(self.fetcher, SafeSourceFetcher):
            original = self.fetcher
            limited = SafeSourceFetcher(
                timeout_seconds=original.timeout_seconds,
                max_bytes=min(original.max_bytes, max_bytes),
                crawl_policies={
                    host: replace(policy, max_bytes=min(policy.max_bytes, max_bytes))
                    for host, policy in original.crawl_policies.items()
                },
                payload_normalizer=original.payload_normalizer,
            )
            limited.opener = original.opener
            limited._robots = original._robots
            return limited.fetch(url)
        fetched = self.fetcher.fetch(url)
        if fetched.bytes_read > max_bytes:
            raise SourceFetchError("source_too_large")
        return fetched


def default_evidence_acquirer() -> EvidenceAcquirer:
    """Factory for the production default (legacy safe static HTTP)."""

    return LegacySafeEvidenceAcquirer()


__all__ = [
    "EVIDENCE_ACQUIRER_CONTRACT_VERSION",
    "AcquiredArtifact",
    "AcquisitionRequest",
    "AcquisitionResult",
    "AcquisitionTier",
    "AcquisitionTiers",
    "EvidenceAcquirer",
    "LegacySafeEvidenceAcquirer",
    "SourceRoleHint",
    "default_evidence_acquirer",
]
