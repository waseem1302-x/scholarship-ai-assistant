"""Crawlee scheduling bridge that preserves the safe acquisition boundary.

``BasicCrawler`` is used only to schedule an acquisition handler. The handler
always calls ``LegacySafeEvidenceAcquirer``; it never calls Crawlee's request
context or HTTP client. That keeps HTTPS, SSRF, DNS/IP, redirect, robots, MIME,
and byte enforcement in ``SafeSourceFetcher``.
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from dataclasses import replace

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
    """Schedule one static acquisition with Crawlee without using its HTTP stack.

    The synchronous ``EvidenceAcquirer`` protocol is intentionally usable from
    the worker CLI. It fails closed when called from an already-running event
    loop instead of attempting a nested loop. Browser, document, and OCR flags
    retain the ``LegacySafeEvidenceAcquirer`` fail-closed behaviour.
    """

    def __init__(self, *, fetcher: SourceFetcher | None = None) -> None:
        if not is_crawlee_installed():
            raise SourceFetchError("crawlee_not_installed")
        self._inner = LegacySafeEvidenceAcquirer(fetcher=fetcher)

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise SourceFetchError("crawlee_static_requires_worker_context")

        result = asyncio.run(self._acquire_with_crawlee(request))
        relabelled = replace(
            result.artifact,
            parser_version="crawlee-static.v2-safe-bridge",
        )
        return AcquisitionResult(artifact=relabelled, fetched=result.fetched)

    async def _acquire_with_crawlee(self, request: AcquisitionRequest) -> AcquisitionResult:
        # Imports stay local so the production default remains importable
        # without the optional Crawlee extra.
        from crawlee import ConcurrencySettings, Request
        from crawlee.configuration import Configuration
        from crawlee.crawlers import BasicCrawler

        results: list[AcquisitionResult] = []
        failures: list[SourceFetchError] = []

        async def acquire_from_safe_boundary(_context: object) -> None:
            # Do not use context.send_request: that would create a second HTTP
            # path and bypass SafeSourceFetcher policy enforcement.
            try:
                results.append(self._inner.acquire(request))
            except SourceFetchError as exc:
                failures.append(exc)

        # The durable database job owns resume state. Crawlee's ephemeral
        # scheduler metadata must not leak into the repository working tree or
        # become a second persistence authority.
        with tempfile.TemporaryDirectory(prefix="scholarship-crawlee-") as storage_dir:
            crawler = BasicCrawler(
                configuration=Configuration(storage_dir=storage_dir, purge_on_start=True),
                request_handler=acquire_from_safe_boundary,
                max_request_retries=0,
                max_requests_per_crawl=1,
                use_session_pool=False,
                retry_on_blocked=False,
                respect_robots_txt_file=False,
                concurrency_settings=ConcurrencySettings(
                    min_concurrency=1,
                    desired_concurrency=1,
                    max_concurrency=1,
                ),
                configure_logging=False,
            )
            # Crawlee's local queue normally de-duplicates URLs. A distinct
            # scheduler key prevents a previously handled URL from suppressing
            # a legitimate durable-job retry; content idempotency remains in
            # the immutable artifact/extraction layers, not Crawlee's queue.
            queued_request = Request.from_url(
                request.url,
                unique_key=f"safe-static-acquisition:{uuid.uuid4().hex}",
            )
            await crawler.run([queued_request])
        if failures:
            raise failures[0]
        if len(results) != 1:
            raise SourceFetchError("crawlee_static_acquisition_missing_result")
        return results[0]


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
