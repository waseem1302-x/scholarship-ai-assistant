"""Read-only administrator preflight for routed paid catalogue extraction."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.errors import AppError
from app.modules.catalogue_ingestion.evidence_block_models import (
    CatalogueEvidenceBlock,
    CatalogueEvidenceRoute,
)
from app.modules.catalogue_ingestion.extraction_planner import EXTRACTION_JOB_PLANNER_VERSION
from app.modules.catalogue_ingestion.provider_config import (
    CATALOGUE_CONFIGURATION_REVISION,
    catalogue_configuration_fingerprint,
)
from app.modules.catalogue_ingestion.schemas import (
    CandidateExtractionPlanResponse,
    ExtractionPlanJobResponse,
)

if TYPE_CHECKING:
    from app.modules.catalogue_ingestion.production_service import (
        ProductionCatalogueIngestionService,
    )


def build_candidate_extraction_preflight(
    service: "ProductionCatalogueIngestionService",
    candidate_id: uuid.UUID,
) -> CandidateExtractionPlanResponse:
    """Calculate routed call/cost bounds without fetching sources or dispatching a provider.

    Missing deterministic route records are created only inside this request transaction so the
    planner can see them, then rolled back before returning. Existing durable evidence, topology,
    cache, provider accounting, and candidate state are never mutated by this preflight.
    """

    candidate = service.repository.get_candidate(candidate_id)
    if candidate is None:
        raise AppError("catalogue_candidate_not_found", "Candidate was not found", 404)
    run = service.repository.get_run(candidate.run_id)
    if run is None:
        raise AppError("ingestion_run_not_found", "Ingestion run was not found", 404)

    try:
        service.evidence_router.persist_candidate(candidate.id)
        service.session.flush()
        plan = service.extraction_planner.plan_candidate(
            candidate.id,
            max_input_characters=run.max_input_characters,
            run_max_output_tokens=run.max_output_tokens,
            input_cost_per_million=service.settings.catalogue_ai_input_cost_per_million,
            output_cost_per_million=service.settings.catalogue_ai_output_cost_per_million,
        )
        block_ids = {item.block_id for job in plan.jobs for item in job.evidence}
        blocks_by_id = (
            {
                block.id: block
                for block in service.session.scalars(
                    select(CatalogueEvidenceBlock).where(
                        CatalogueEvidenceBlock.id.in_(block_ids)
                    )
                )
            }
            if block_ids
            else {}
        )
        routes = list(
            service.session.scalars(
                select(CatalogueEvidenceRoute).where(
                    CatalogueEvidenceRoute.candidate_id == candidate.id,
                    CatalogueEvidenceRoute.selected.is_(True),
                )
            )
        )
        maximum_calls, maximum_cost = service._maximum_execution_envelope(
            plan.jobs,
            blocks_by_id=blocks_by_id,
            routes=routes,
            run=run,
        )
        service.repository.refresh_provider_accounting(run)
        remaining_calls = max(0, run.max_model_calls - run.model_calls)
        remaining_cost = max(
            Decimal("0"),
            run.max_estimated_cost - run.estimated_cost,
        )
        effective_fingerprint = catalogue_configuration_fingerprint(service.settings)
        configuration_matches = (
            run.configuration_revision == CATALOGUE_CONFIGURATION_REVISION
            and run.configuration_fingerprint == effective_fingerprint
        )
        refusal_reasons = list(plan.refusal_reasons)
        if not configuration_matches:
            refusal_reasons.append("provider_configuration_drift")
        if plan.estimated_calls > remaining_calls:
            refusal_reasons.append("provider_call_budget_exhausted")
        if plan.estimated_cost_upper > remaining_cost:
            refusal_reasons.append("provider_cost_budget_exhausted")
        refusal_reasons = list(dict.fromkeys(refusal_reasons))

        response = CandidateExtractionPlanResponse(
            candidate_id=candidate.id,
            run_id=run.id,
            planner_version=EXTRACTION_JOB_PLANNER_VERSION,
            configuration_revision=CATALOGUE_CONFIGURATION_REVISION,
            configuration_fingerprint=effective_fingerprint,
            run_configuration_matches=configuration_matches,
            ready_for_paid_execution=not refusal_reasons,
            refusal_reasons=refusal_reasons,
            estimated_calls=plan.estimated_calls,
            estimated_input_tokens=plan.estimated_input_tokens,
            estimated_output_tokens_upper=plan.max_output_tokens,
            estimated_cost_upper=plan.estimated_cost_upper,
            maximum_physical_calls_with_split_and_retry=maximum_calls,
            maximum_cost_upper_with_split_and_retry=maximum_cost,
            remaining_call_budget=remaining_calls,
            remaining_cost_budget=remaining_cost,
            jobs=[
                ExtractionPlanJobResponse(
                    job_key=job.job_key,
                    source_id=job.source_id,
                    source_artifact_id=job.source_artifact_id,
                    objectives=[item.value for item in job.objectives],
                    scope_target_count=len(job.scopes),
                    evidence_block_keys=[item.block_key for item in job.evidence],
                    evidence_character_count=job.evidence_character_count,
                    estimated_input_tokens=job.estimated_input_tokens,
                    max_output_tokens=job.max_output_tokens,
                    estimated_cost_upper=job.estimated_cost_upper,
                )
                for job in plan.jobs
            ],
        )
    finally:
        service.session.rollback()
    return response


__all__ = ["build_candidate_extraction_preflight"]
