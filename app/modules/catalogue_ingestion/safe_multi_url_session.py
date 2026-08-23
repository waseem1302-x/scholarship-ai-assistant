"""Bounded multi-URL acquisition through the safe EvidenceAcquirer path.

Phase 1b.2a: sequential session with hard budgets. Does not open a second
network stack. Future Crawlee queue workers should call the same acquirer
per URL (ADR 0016).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.catalogue_ingestion.evidence_acquirer import (
    AcquisitionRequest,
    AcquisitionResult,
    EvidenceAcquirer,
    LegacySafeEvidenceAcquirer,
    SourceRoleHint,
)
from app.modules.opportunities.source_monitor import SourceFetchError

DEFAULT_MAX_URLS = 20


@dataclass(frozen=True, slots=True)
class MultiUrlAcquisitionPlan:
    """One bounded batch of official URLs to acquire."""

    urls: tuple[str, ...]
    role_hint: SourceRoleHint = SourceRoleHint.UNKNOWN
    max_urls: int = DEFAULT_MAX_URLS
    max_bytes_per_url: int | None = None
    stop_on_error: bool = False

    def __post_init__(self) -> None:
        if self.max_urls < 1:
            raise ValueError("max_urls must be positive")
        if len(self.urls) > self.max_urls:
            raise ValueError(f"url count exceeds max_urls={self.max_urls}")
        for url in self.urls:
            if not url or not str(url).strip():
                raise ValueError("urls must not contain empty entries")


@dataclass(frozen=True, slots=True)
class MultiUrlAcquisitionOutcome:
    """Results and failures for one plan."""

    results: tuple[AcquisitionResult, ...] = ()
    failures: tuple[tuple[str, str], ...] = ()
    """(url, error_code_or_message) pairs."""


@dataclass
class SafeMultiUrlAcquisitionSession:
    """Sequential multi-URL acquisition using a single EvidenceAcquirer.

    Concurrency is intentionally not introduced here; rate and host pacing can
    be added later without changing the security boundary.
    """

    acquirer: EvidenceAcquirer = field(default_factory=LegacySafeEvidenceAcquirer)

    def run(self, plan: MultiUrlAcquisitionPlan) -> MultiUrlAcquisitionOutcome:
        results: list[AcquisitionResult] = []
        failures: list[tuple[str, str]] = []

        for url in plan.urls:
            request = AcquisitionRequest(
                url=url,
                role_hint=plan.role_hint,
                max_bytes=plan.max_bytes_per_url,
                allow_browser=False,
                allow_document_parser=False,
                allow_ocr=False,
            )
            try:
                results.append(self.acquirer.acquire(request))
            except SourceFetchError as exc:
                failures.append((url, str(exc).split(":", 1)[0][:120]))
                if plan.stop_on_error:
                    break
            except ValueError as exc:
                failures.append((url, str(exc)[:120]))
                if plan.stop_on_error:
                    break

        return MultiUrlAcquisitionOutcome(
            results=tuple(results),
            failures=tuple(failures),
        )


__all__ = [
    "DEFAULT_MAX_URLS",
    "MultiUrlAcquisitionOutcome",
    "MultiUrlAcquisitionPlan",
    "SafeMultiUrlAcquisitionSession",
]
