"""Review-gated control plane for bounded catalogue web discovery."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.catalogue_ingestion.azure_discovery_provider import get_discovery_provider
from app.modules.catalogue_ingestion.discovery import (
    DiscoveryObjective,
    DiscoveryPrioritySnapshot,
    DiscoveryQueryPlanner,
)
from app.modules.catalogue_ingestion.discovery_models import (
    CatalogueDiscoveryLead,
    CatalogueDiscoveryObservation,
    CatalogueDiscoveryQuery,
    CatalogueDiscoveryRun,
    DiscoveryQueryStatus,
)
from app.modules.catalogue_ingestion.discovery_repository import (
    CatalogueDiscoveryRepository,
    DiscoveryRunLimits,
    DiscoveryStateError,
)
from app.modules.catalogue_ingestion.discovery_schemas import (
    CandidateDiscoveryRunRequest,
    DiscoveryLeadBindingResponse,
    DiscoveryLeadListResponse,
    DiscoveryLeadResponse,
    DiscoveryRunListResponse,
    DiscoveryRunResponse,
)
from app.modules.catalogue_ingestion.discovery_service import (
    CatalogueDiscoveryExecutionService,
    CatalogueDiscoveryLeadIngestionService,
)
from app.modules.catalogue_ingestion.models import CatalogueCandidate


class CatalogueDiscoveryControlService:
    """Connect durable discovery primitives without creating an autonomous publication path."""

    def __init__(self, session: Session, settings: Settings, *, provider=None) -> None:
        self.session = session
        self.settings = settings
        self.repository = CatalogueDiscoveryRepository(session)
        self.provider = provider or get_discovery_provider(settings)

    def create_candidate_run(
        self,
        request: CandidateDiscoveryRunRequest,
    ) -> DiscoveryRunResponse:
        candidate = self.session.get(CatalogueCandidate, request.candidate_id)
        if candidate is None:
            raise DiscoveryStateError("catalogue_discovery_candidate_not_found")
        objective = DiscoveryObjective(
            objective_kind=request.objective_kind,
            candidate_id=candidate.id,
            field_paths=request.field_paths,
            reason_codes=request.reason_codes,
            criticality_tier=request.criticality_tier,
            scholarship_name=candidate.seed_name,
            provider_name=candidate.seed_provider,
            country=candidate.seed_country,
            reviewed_domains=request.reviewed_domains,
        )
        plans = DiscoveryQueryPlanner(
            max_queries=self.settings.catalogue_discovery_max_queries_per_run
        ).plan(objective)
        priority = DiscoveryPrioritySnapshot(
            blocking_class=0,
            criticality_tier=objective.criticality_tier,
            conflict_or_stale_rank=0,
            current_cycle_rank=0,
            deterministic_tiebreak=f"candidate:{candidate.id}:{objective.objective_kind.value}",
            reason_codes=objective.reason_codes,
        )
        run = self.repository.create_run(
            objective=objective,
            priority=priority,
            plans=plans,
            provider=getattr(self.provider, "name", self.settings.catalogue_web_discovery_provider),
            model=getattr(self.provider, "model", self.settings.catalogue_web_discovery_model),
            limits=DiscoveryRunLimits(
                max_queries=self.settings.catalogue_discovery_max_queries_per_run,
                max_provider_calls=self.settings.catalogue_discovery_max_provider_calls_per_run,
                max_tool_calls=(
                    self.settings.catalogue_discovery_max_queries_per_run
                    * self.settings.catalogue_discovery_max_tool_calls_per_provider_request
                ),
                max_leads=self.settings.catalogue_discovery_max_leads_per_run,
                max_response_bytes=self.settings.catalogue_web_discovery_max_response_bytes,
                max_estimated_cost=self.settings.catalogue_discovery_max_estimated_cost_per_run,
            ),
            dry_run=request.dry_run,
        )
        return DiscoveryRunResponse.model_validate(run)

    def process_run(
        self,
        run_id: uuid.UUID,
        *,
        worker_id: str,
        max_queries: int,
    ) -> DiscoveryRunResponse:
        if not self.settings.catalogue_web_discovery_enabled:
            raise DiscoveryStateError("catalogue_web_discovery_disabled")
        claimed = self.repository.claim_queries(
            run_id=run_id,
            worker_id=worker_id,
            limit=max_queries,
            lease_seconds=self.settings.catalogue_worker_claim_seconds,
            max_attempts=self.settings.catalogue_web_discovery_max_retries + 1,
        )
        executor = CatalogueDiscoveryExecutionService(self.session, self.provider)
        lead_ingestion = CatalogueDiscoveryLeadIngestionService(self.session)
        for query in claimed:
            try:
                result = executor.execute_claimed_query(
                    query_id=query.id,
                    worker_id=worker_id,
                    max_urls=self.settings.catalogue_discovery_max_urls_per_query,
                    max_tool_calls=(
                        self.settings.catalogue_discovery_max_tool_calls_per_provider_request
                    ),
                    max_estimated_cost=(
                        self.settings.catalogue_discovery_max_estimated_cost_per_provider_request
                    ),
                )
                lead_ingestion.ingest_provider_result(query_id=query.id, result=result)
                self.repository.complete_query(query.id)
            except Exception:
                current = self.repository.get_query(query.id)
                if (
                    current is not None
                    and current.status
                    in {
                        DiscoveryQueryStatus.PROVIDER_RATE_LIMITED,
                        DiscoveryQueryStatus.PROVIDER_FAILED,
                    }
                    and current.attempt_count
                    < self.settings.catalogue_web_discovery_max_retries + 1
                ):
                    self.repository.schedule_retry(
                        current.id,
                        next_attempt_at=datetime.now(UTC)
                        + timedelta(seconds=min(60, 2 ** max(0, current.attempt_count - 1))),
                        max_attempts=self.settings.catalogue_web_discovery_max_retries + 1,
                    )
                continue
        run = self.session.get(CatalogueDiscoveryRun, run_id)
        if run is None:
            raise DiscoveryStateError("catalogue_discovery_run_not_found")
        return DiscoveryRunResponse.model_validate(run)

    def list_runs(self, *, limit: int, offset: int) -> DiscoveryRunListResponse:
        items = list(
            self.session.scalars(
                select(CatalogueDiscoveryRun)
                .order_by(CatalogueDiscoveryRun.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        total = self.session.scalar(select(func.count()).select_from(CatalogueDiscoveryRun)) or 0
        return DiscoveryRunListResponse(
            items=[DiscoveryRunResponse.model_validate(item) for item in items],
            total=int(total),
        )

    def list_leads(
        self,
        *,
        run_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> DiscoveryLeadListResponse:
        statement = select(CatalogueDiscoveryLead)
        count_statement = select(func.count()).select_from(CatalogueDiscoveryLead)
        if run_id is not None:
            observed_leads = (
                select(CatalogueDiscoveryObservation.lead_id)
                .join(
                    CatalogueDiscoveryQuery,
                    CatalogueDiscoveryQuery.id == CatalogueDiscoveryObservation.query_id,
                )
                .where(CatalogueDiscoveryQuery.run_id == run_id)
            )
            statement = statement.where(CatalogueDiscoveryLead.id.in_(observed_leads))
            count_statement = count_statement.where(CatalogueDiscoveryLead.id.in_(observed_leads))
        items = list(
            self.session.scalars(
                statement.order_by(CatalogueDiscoveryLead.last_seen_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        total = self.session.scalar(count_statement) or 0
        return DiscoveryLeadListResponse(
            items=[DiscoveryLeadResponse.model_validate(item) for item in items],
            total=int(total),
        )

    def review_lead(
        self,
        lead_id: uuid.UUID,
        *,
        status: str,
        reviewer_id: uuid.UUID,
        reason: str,
    ) -> DiscoveryLeadResponse:
        lead = self.repository.review_lead(
            lead_id=lead_id,
            status=status,
            reviewer_id=reviewer_id,
            reason=reason,
        )
        return DiscoveryLeadResponse.model_validate(lead)

    def bind_lead(
        self,
        lead_id: uuid.UUID,
        *,
        run_id: uuid.UUID,
        assessment_id: uuid.UUID,
    ) -> DiscoveryLeadBindingResponse:
        outcome = self.repository.bind_candidate_source(
            run_id=run_id,
            lead_id=lead_id,
            assessment_id=assessment_id,
        )
        return DiscoveryLeadBindingResponse(
            lead_id=lead_id,
            candidate_source_id=outcome.source.id,
            created=outcome.created,
            candidate_resumed=outcome.candidate_resumed,
        )
