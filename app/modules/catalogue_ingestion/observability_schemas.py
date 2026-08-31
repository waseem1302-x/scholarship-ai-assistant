"""Authorized administrator read models for catalogue ingestion operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ScopedCoverageState
from app.modules.catalogue_ingestion.models import CandidateStatus, IngestionRunStatus
from app.modules.catalogue_ingestion.provider_attempts import (
    ProviderAccountingState,
    ProviderAttemptState,
    ProviderFailureClass,
)
from app.modules.catalogue_ingestion.review_models import CatalogueProposalState
from app.modules.catalogue_ingestion.scheduling_models import ProviderCircuitState
from app.modules.catalogue_ingestion.topology_models import (
    ScopeDiscoveryConfidence,
    ScopeEdgeType,
    ScopeNodeType,
)


class LeaseObservability(BaseModel):
    is_active: bool
    expires_at: datetime | None


class ScopeNodeObservability(BaseModel):
    id: uuid.UUID
    node_type: ScopeNodeType
    canonical_key: str
    display_label: str
    lifecycle_key: str
    discovery_confidence: ScopeDiscoveryConfidence
    expected_child_counts: dict[str, int]


class ScopeEdgeObservability(BaseModel):
    parent_node_id: uuid.UUID
    child_node_id: uuid.UUID
    relationship_type: ScopeEdgeType
    objective_keys: list[str]
    confidence: ScopeDiscoveryConfidence


class TopologyObservability(BaseModel):
    nodes: list[ScopeNodeObservability]
    edges: list[ScopeEdgeObservability]


class CoverageObservability(BaseModel):
    objective: ClaimObjective
    scope_node_id: uuid.UUID
    state: ScopedCoverageState
    required: bool
    reason: str
    expected_item_count: int | None
    resolved_item_count: int
    missing_frontier_reasons: list[str]


class ProviderAttemptObservability(BaseModel):
    id: uuid.UUID
    objective: str | None
    objective_bundle: list[str]
    provider: str
    deployment: str | None
    state: ProviderAttemptState
    failure_class: ProviderFailureClass | None
    error_code: str | None
    accounting_state: ProviderAccountingState
    reserved_cost_upper: Decimal
    cost_lower_bound: Decimal
    cost_upper_bound: Decimal
    input_tokens: int | None
    output_tokens: int | None
    retry_ordinal: int
    created_at: datetime
    completed_at: datetime | None


class CacheDecisionObservability(BaseModel):
    decision: str
    reason: str
    created_at: datetime


class AcquisitionObservability(BaseModel):
    revision: str
    coverage_revision: str | None
    plan: dict[str, object]
    budget: dict[str, object]
    result: dict[str, object]
    created_at: datetime


class ReviewObservability(BaseModel):
    state: CatalogueProposalState
    proposal_hash: str | None
    approved_proposal_hash: str | None
    review_revision: int
    materialization_revision: str | None
    materialization_attempt_count: int
    materialization_failure_code: str | None
    materialized_claim_count: int
    publication_ready_at: datetime | None
    published_at: datetime | None


class CandidateObservabilityResponse(BaseModel):
    candidate_id: uuid.UUID
    run_id: uuid.UUID
    status: CandidateStatus
    failure_code: str | None
    lease: LeaseObservability
    source_count: int
    topology: TopologyObservability
    coverage: list[CoverageObservability]
    unresolved_branches: list[CoverageObservability]
    conflicts: list[str]
    validation_errors: list[str]
    acquisition: AcquisitionObservability | None
    provider_attempts: list[ProviderAttemptObservability]
    cache_decisions: list[CacheDecisionObservability]
    review: ReviewObservability | None


class ProviderCircuitObservability(BaseModel):
    provider: str
    deployment: str
    failure_class: ProviderFailureClass
    state: ProviderCircuitState
    consecutive_failures: int
    opened_until: datetime | None


class CostObservability(BaseModel):
    reserved_upper: Decimal
    lower_bound: Decimal
    upper_bound: Decimal


class RunObservabilityResponse(BaseModel):
    run_id: uuid.UUID
    status: IngestionRunStatus
    dry_run: bool
    configuration_revision: str | None
    configuration_fingerprint: str | None
    kill_switch_enabled: bool
    candidate_outcomes: dict[str, int]
    provider_attempt_states: dict[str, int]
    provider_accounting_states: dict[str, int]
    provider_failure_classes: dict[str, int]
    scheduling_decisions: dict[str, int]
    costs: CostObservability
    circuits: list[ProviderCircuitObservability] = Field(default_factory=list)
