"""Runtime helpers connecting persisted catalogue state to bounded acquisition contracts."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.core.config import Settings
from app.modules.catalogue_ingestion.acquisition_planner import AcquisitionPlan
from app.modules.catalogue_ingestion.crawler import (
    AcquisitionAuthority,
    AcquisitionSeed,
    CrawlBudget,
    CrawlResult,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceRole,
    CatalogueCandidateSource,
    CatalogueIngestionRun,
)


def crawl_budget_for_run(run: CatalogueIngestionRun, settings: Settings) -> CrawlBudget:
    """Derive independent acquisition limits from the existing run receipt/settings.

    No new environment variable is required in Batch 4. The accepted-artifact ceiling preserves
    the existing run page budget while attempts, host requests, bytes, conversions, and wall time
    are independently bounded.
    """

    if settings.catalogue_completeness_mode_enabled:
        attempts = settings.catalogue_completeness_max_fetch_attempts
        return CrawlBudget(
            max_fetch_attempts=attempts,
            max_accepted_artifacts=None,
            max_depth=3,
            max_total_bytes=20_000_000,
            max_host_requests=attempts,
            max_wall_seconds=None,
            max_browser_renders=1 if settings.catalogue_browser_fetching_enabled else 0,
            max_document_conversions=attempts,
            max_links_per_page=500,
            per_host_interval_seconds=float(settings.source_monitor_per_host_interval_seconds),
        )

    accepted = max(1, min(run.max_pages_per_candidate, 25))
    attempts = max(accepted, min(accepted * 3, 100))
    per_page_bytes = settings.catalogue_source_max_bytes_per_page
    total_bytes = min(per_page_bytes * accepted, 20_000_000)
    wall_seconds = float(min(max(settings.catalogue_ai_timeout_seconds * attempts, 30), 300))
    return CrawlBudget(
        max_fetch_attempts=attempts,
        max_accepted_artifacts=accepted,
        max_depth=2,
        max_total_bytes=total_bytes,
        max_host_requests=attempts,
        max_wall_seconds=wall_seconds,
        max_browser_renders=1 if settings.catalogue_browser_fetching_enabled else 0,
        # Built-in static PDF/DOCX/XLSX/CSV conversion is local and bounded. This is not
        # Azure Document Intelligence and therefore does not require the OCR feature switch.
        max_document_conversions=min(accepted, 10),
        max_links_per_page=100,
        per_host_interval_seconds=float(settings.source_monitor_per_host_interval_seconds),
    )


def acquisition_seeds(
    sources: list[CatalogueCandidateSource],
) -> list[AcquisitionSeed]:
    """Map operator-bound sources to conservative typed acquisition authorities."""

    seeds: list[AcquisitionSeed] = []
    for source in sources:
        authority = (
            AcquisitionAuthority.PROGRAMME_OWNER
            if source.source_role is CandidateSourceRole.PRIMARY
            else AcquisitionAuthority.REVIEWED_AUXILIARY
        )
        seeds.append(AcquisitionSeed(source.url, authority))
    return seeds


def acquisition_snapshot_payload(
    *,
    plan: AcquisitionPlan,
    budget: CrawlBudget,
    result: CrawlResult,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return secret-free JSON payloads for the append-only acquisition snapshot."""

    plan_json = {
        "candidate_id": str(plan.candidate_id),
        "coverage_revision": plan.coverage_revision,
        "needs": [asdict(item) for item in plan.needs],
    }
    budget_json = {
        "max_fetch_attempts": budget.max_fetch_attempts,
        "max_accepted_artifacts": budget.max_accepted_artifacts,
        "max_depth": budget.max_depth,
        "max_total_bytes": budget.max_total_bytes,
        "max_host_requests": budget.max_host_requests,
        "max_wall_seconds": budget.max_wall_seconds,
        "max_browser_renders": budget.max_browser_renders,
        "max_document_conversions": budget.max_document_conversions,
        "max_links_per_page": budget.max_links_per_page,
        "per_host_interval_seconds": budget.per_host_interval_seconds,
    }
    result_json = {
        "root_url": result.root_url,
        "accepted_urls": [page.url for page in result.pages],
        "accepted_artifacts": result.accepted_artifacts,
        "fetch_attempts": result.fetch_attempts,
        "total_bytes": result.total_bytes,
        "host_requests": [list(item) for item in result.host_requests],
        "elapsed_seconds": result.elapsed_seconds,
        "duplicate_content_urls": list(result.duplicate_content_urls),
        "near_duplicate_content_urls": list(result.near_duplicate_content_urls),
        "failures": [asdict(item) for item in result.failures],
        "rejected": [asdict(item) for item in result.rejected],
        "escalations": [
            {
                **asdict(item),
                "kind": item.kind.value,
            }
            for item in result.escalations
        ],
        "budget_exhausted": result.budget_exhausted,
        "budget_reasons": list(result.budget_reasons),
        "unresolved_frontier": list(result.unresolved_frontier),
    }
    return plan_json, budget_json, result_json


__all__ = [
    "acquisition_seeds",
    "acquisition_snapshot_payload",
    "crawl_budget_for_run",
]
