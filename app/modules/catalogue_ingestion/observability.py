"""Consolidated, non-sensitive operational views for catalogue administrators."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.catalogue_ingestion.acquisition_models import CatalogueAcquisitionSnapshot
from app.modules.catalogue_ingestion.claim_schemas import ScopedCoverageState
from app.modules.catalogue_ingestion.extraction_cache_models import CatalogueExtractionCacheEvent
from app.modules.catalogue_ingestion.models import (
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueIngestionRun,
)
from app.modules.catalogue_ingestion.observability_schemas import (
    AcquisitionObservability,
    CacheDecisionObservability,
    CandidateObservabilityResponse,
    CostObservability,
    CoverageObservability,
    LeaseObservability,
    ProviderAttemptObservability,
    ProviderCircuitObservability,
    ReviewObservability,
    RunObservabilityResponse,
    ScopeEdgeObservability,
    ScopeNodeObservability,
    TopologyObservability,
)
from app.modules.catalogue_ingestion.provider_attempts import CatalogueProviderAttempt
from app.modules.catalogue_ingestion.review_models import CatalogueCandidateReview
from app.modules.catalogue_ingestion.scheduling_models import (
    CatalogueProviderCircuit,
    CatalogueProviderLane,
    CatalogueSchedulingDecision,
)
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueCoverageCell,
    CatalogueScopeEdge,
    CatalogueScopeNode,
)
from app.modules.opportunities.materialization_models import CatalogueMaterializedClaimLink

_RESOLVED_COVERAGE_STATES = {
    ScopedCoverageState.COMPLETE,
    ScopedCoverageState.NOT_APPLICABLE,
}


class CatalogueObservabilityService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def run(self, run_id: uuid.UUID) -> RunObservabilityResponse:
        run = self.session.get(CatalogueIngestionRun, run_id)
        if run is None:
            raise AppError("catalogue_ingestion_run_not_found", "Ingestion run was not found", 404)
        attempts = list(
            self.session.scalars(
                select(CatalogueProviderAttempt).where(CatalogueProviderAttempt.run_id == run.id)
            )
        )
        lanes = list(
            self.session.execute(
                select(CatalogueProviderCircuit, CatalogueProviderLane)
                .join(
                    CatalogueProviderLane,
                    CatalogueProviderLane.id == CatalogueProviderCircuit.lane_id,
                )
                .where(
                    CatalogueProviderLane.provider.in_({item.provider for item in attempts})
                    if attempts
                    else CatalogueProviderLane.id.is_(None)
                )
            )
        )
        outcome_rows = self.session.execute(
            select(CatalogueCandidate.status, func.count())
            .where(CatalogueCandidate.run_id == run.id)
            .group_by(CatalogueCandidate.status)
        ).all()
        decision_rows = self.session.execute(
            select(CatalogueSchedulingDecision.decision, func.count())
            .where(CatalogueSchedulingDecision.run_id == run.id)
            .group_by(CatalogueSchedulingDecision.decision)
        ).all()
        return RunObservabilityResponse(
            run_id=run.id,
            status=run.status,
            dry_run=run.dry_run,
            configuration_revision=run.configuration_revision,
            configuration_fingerprint=run.configuration_fingerprint,
            kill_switch_enabled=self.settings.catalogue_ai_ingestion_enabled,
            candidate_outcomes={key.value: int(value) for key, value in outcome_rows},
            provider_attempt_states=_enum_counts(attempts, "state"),
            provider_accounting_states=_enum_counts(attempts, "accounting_state"),
            provider_failure_classes=_enum_counts(attempts, "failure_class"),
            scheduling_decisions={key.value: int(value) for key, value in decision_rows},
            costs=CostObservability(
                reserved_upper=sum((item.reserved_cost_upper for item in attempts), Decimal("0")),
                lower_bound=sum((item.cost_lower_bound for item in attempts), Decimal("0")),
                upper_bound=sum((item.cost_upper_bound for item in attempts), Decimal("0")),
            ),
            circuits=[
                ProviderCircuitObservability(
                    provider=lane.provider,
                    deployment=lane.deployment,
                    failure_class=circuit.failure_class,
                    state=circuit.state,
                    consecutive_failures=circuit.consecutive_failures,
                    opened_until=circuit.opened_until,
                )
                for circuit, lane in lanes
            ],
        )

    def candidate(self, candidate_id: uuid.UUID) -> CandidateObservabilityResponse:
        candidate = self.session.get(CatalogueCandidate, candidate_id)
        if candidate is None:
            raise AppError("catalogue_candidate_not_found", "Candidate was not found", 404)
        nodes = list(
            self.session.scalars(
                select(CatalogueScopeNode)
                .where(CatalogueScopeNode.candidate_id == candidate.id)
                .order_by(CatalogueScopeNode.node_type, CatalogueScopeNode.display_label)
            )
        )
        edges = list(
            self.session.scalars(
                select(CatalogueScopeEdge)
                .where(CatalogueScopeEdge.candidate_id == candidate.id)
                .order_by(CatalogueScopeEdge.created_at)
            )
        )
        cells = list(
            self.session.scalars(
                select(CatalogueCoverageCell)
                .where(CatalogueCoverageCell.candidate_id == candidate.id)
                .order_by(CatalogueCoverageCell.objective, CatalogueCoverageCell.scope_node_id)
            )
        )
        coverage = [_coverage(item) for item in cells]
        attempts = list(
            self.session.scalars(
                select(CatalogueProviderAttempt)
                .where(CatalogueProviderAttempt.candidate_id == candidate.id)
                .order_by(CatalogueProviderAttempt.created_at)
            )
        )
        cache_events = list(
            self.session.scalars(
                select(CatalogueExtractionCacheEvent)
                .where(CatalogueExtractionCacheEvent.candidate_id == candidate.id)
                .order_by(CatalogueExtractionCacheEvent.created_at)
            )
        )
        acquisition = self.session.scalar(
            select(CatalogueAcquisitionSnapshot)
            .where(CatalogueAcquisitionSnapshot.candidate_id == candidate.id)
            .order_by(CatalogueAcquisitionSnapshot.created_at.desc())
            .limit(1)
        )
        review = self.session.scalar(
            select(CatalogueCandidateReview).where(
                CatalogueCandidateReview.candidate_id == candidate.id
            )
        )
        materialized_count = (
            self.session.scalar(
                select(func.count())
                .select_from(CatalogueMaterializedClaimLink)
                .where(CatalogueMaterializedClaimLink.candidate_id == candidate.id)
            )
            or 0
        )
        source_count = (
            self.session.scalar(
                select(func.count())
                .select_from(CatalogueCandidateSource)
                .where(CatalogueCandidateSource.candidate_id == candidate.id)
            )
            or 0
        )
        now = datetime.now(UTC)
        lease_expires = candidate.claimed_until
        if lease_expires is not None and lease_expires.tzinfo is None:
            lease_expires = lease_expires.replace(tzinfo=UTC)
        return CandidateObservabilityResponse(
            candidate_id=candidate.id,
            run_id=candidate.run_id,
            status=candidate.status,
            failure_code=candidate.failure_code,
            lease=LeaseObservability(
                is_active=bool(candidate.lease_token and lease_expires and lease_expires > now),
                expires_at=lease_expires,
            ),
            source_count=int(source_count),
            topology=TopologyObservability(
                nodes=[
                    ScopeNodeObservability(
                        id=item.id,
                        node_type=item.node_type,
                        canonical_key=item.canonical_key,
                        display_label=item.display_label,
                        lifecycle_key=item.lifecycle_key,
                        discovery_confidence=item.discovery_confidence,
                        expected_child_counts=item.expected_child_counts,
                    )
                    for item in nodes
                ],
                edges=[
                    ScopeEdgeObservability(
                        parent_node_id=item.parent_node_id,
                        child_node_id=item.child_node_id,
                        relationship_type=item.relationship_type,
                        objective_keys=item.objective_keys,
                        confidence=item.confidence,
                    )
                    for item in edges
                ],
            ),
            coverage=coverage,
            unresolved_branches=[
                item for item in coverage if item.state not in _RESOLVED_COVERAGE_STATES
            ],
            conflicts=list(candidate.conflicts or []),
            validation_errors=list(candidate.validation_errors or []),
            acquisition=(
                AcquisitionObservability(
                    revision=acquisition.revision,
                    coverage_revision=acquisition.coverage_revision,
                    plan=acquisition.plan_json,
                    budget=acquisition.budget_json,
                    result=acquisition.result_json,
                    created_at=acquisition.created_at,
                )
                if acquisition is not None
                else None
            ),
            provider_attempts=[
                ProviderAttemptObservability.model_validate(item, from_attributes=True)
                for item in attempts
            ],
            cache_decisions=[
                CacheDecisionObservability(
                    decision=item.decision,
                    reason=item.reason,
                    created_at=item.created_at,
                )
                for item in cache_events
            ],
            review=(
                ReviewObservability(
                    state=review.state,
                    proposal_hash=review.proposal_hash,
                    approved_proposal_hash=review.approved_proposal_hash,
                    review_revision=review.review_revision,
                    materialization_revision=review.materialization_revision,
                    materialization_attempt_count=review.materialization_attempt_count,
                    materialization_failure_code=review.materialization_failure_code,
                    materialized_claim_count=int(materialized_count),
                    publication_ready_at=review.publication_ready_at,
                    published_at=review.published_at,
                )
                if review is not None
                else None
            ),
        )


def _coverage(cell: CatalogueCoverageCell) -> CoverageObservability:
    return CoverageObservability(
        objective=cell.objective,
        scope_node_id=cell.scope_node_id,
        state=cell.state,
        required=cell.required,
        reason=cell.reason,
        expected_item_count=cell.expected_item_count,
        resolved_item_count=cell.resolved_item_count,
        missing_frontier_reasons=list(cell.missing_frontier_reasons or []),
    )


def _enum_counts(items: list[object], attribute: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = getattr(item, attribute)
        if value is None:
            continue
        key = value.value
        counts[key] = counts.get(key, 0) + 1
    return counts
