"""Optional Crawlee-labelled static acquirer (Phase 1b.1).

This module does **not** open a second network path. Single-URL acquisition
still uses ``SafeSourceFetcher`` via ``LegacySafeEvidenceAcquirer``. Crawlee
is detected only so operators can opt into a labelled adapter after installing
the optional extra; full Crawlee queue orchestration is deferred to Phase 1b.2
(ADR 0015).
"""

from __future__ import annotations

from app.modules.catalogue_ingestion.evidence_acquirer import (
    AcquisitionRequest,
    AcquisitionResult,
    EvidenceAcquirer,
    LegacySafeEvidenceAcquirer,
)
from app.modules.opportunities.source_monitor import SourceFetcher, SourceFetchError


def is_crawlee_installed() -> bool:
    """Return True when the optional ``crawlee`` package is importable."""

    try:
        import crawlee  # noqa: F401
    except ImportError:
        return False
    return True


class CrawleeStaticEvidenceAcquirer:
    """EvidenceAcquirer labelled for the future Crawlee static path.

    Phase 1b.1: delegates to ``LegacySafeEvidenceAcquirer`` so SSRF, robots,
    redirect, MIME, and byte limits remain unchanged. Raises if browser,
    document, or OCR flags are set (same fail-closed rules).
    """

    def __init__(self, *, fetcher: SourceFetcher | None = None) -> None:
        if not is_crawlee_installed():
            raise SourceFetchError("crawlee_not_installed")
        self._inner = LegacySafeEvidenceAcquirer(fetcher=fetcher)

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        result = self._inner.acquire(request)
        artifact = result.artifact
        # Relabel parser identity so metrics can distinguish opt-in path without
        # changing security semantics.
        relabelled = type(artifact)(
            **{
                **{field: getattr(artifact, field) for field in artifact.__dataclass_fields__},
                "parser_version": "crawlee-static.v1-safe-delegate",
            }
        )
        return AcquisitionResult(artifact=relabelled, fetched=result.fetched)


def select_evidence_acquirer(
    *,
    prefer_crawlee_static: bool = False,
    fetcher: SourceFetcher | None = None,
) -> EvidenceAcquirer:
    """Choose the production default or an explicit Crawlee-labelled adapter.

    Defaults to legacy safe acquisition. Crawlee is never selected unless
    ``prefer_crawlee_static`` is True and the optional package is installed.
    """

    if prefer_crawlee_static:
        if not is_crawlee_installed():
            raise SourceFetchError("crawlee_not_installed")
        return CrawleeStaticEvidenceAcquirer(fetcher=fetcher)
    return LegacySafeEvidenceAcquirer(fetcher=fetcher)


__all__ = [
    "CrawleeStaticEvidenceAcquirer",
    "is_crawlee_installed",
    "select_evidence_acquirer",
]
