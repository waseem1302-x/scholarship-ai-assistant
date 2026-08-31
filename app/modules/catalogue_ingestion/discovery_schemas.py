"""Administrator contracts for review-gated catalogue discovery."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.catalogue_ingestion.discovery import DiscoveryObjectiveKind
from app.modules.catalogue_ingestion.discovery_models import (
    DiscoveryLeadReviewStatus,
    DiscoveryRunStatus,
)


class CandidateDiscoveryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: uuid.UUID
    objective_kind: DiscoveryObjectiveKind = DiscoveryObjectiveKind.RESOLVE_CANONICAL_SOURCE
    field_paths: tuple[str, ...] = ("identity.official_source", "identity.provider")
    reason_codes: tuple[str, ...] = ("OFFICIAL_SOURCE_MISSING",)
    criticality_tier: int = Field(default=0, ge=0, le=3)
    reviewed_domains: tuple[str, ...] = Field(default=(), max_length=20)
    dry_run: bool = True


class DiscoveryRunProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_queries: int = Field(default=1, ge=1, le=10)


class DiscoveryLeadReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "rejected"]
    reason: str = Field(min_length=10, max_length=500)


class DiscoveryLeadBindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    assessment_id: uuid.UUID


class DiscoveryRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_candidate_id: uuid.UUID | None
    objective_kind: str
    provider: str
    model: str
    status: DiscoveryRunStatus
    dry_run: bool
    max_queries: int
    max_provider_calls: int
    max_leads: int
    max_estimated_cost: Decimal
    provider_calls_completed: int
    estimated_cost_settled: Decimal
    raw_leads_seen: int
    unique_leads: int
    promotions: int
    failure_code: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class DiscoveryRunListResponse(BaseModel):
    items: list[DiscoveryRunResponse]
    total: int


class DiscoveryLeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    normalized_url: str
    host: str
    active: bool
    review_status: DiscoveryLeadReviewStatus
    review_reason: str | None
    reviewed_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime


class DiscoveryLeadListResponse(BaseModel):
    items: list[DiscoveryLeadResponse]
    total: int


class DiscoveryLeadBindingResponse(BaseModel):
    lead_id: uuid.UUID
    candidate_source_id: uuid.UUID
    created: bool
    candidate_resumed: bool
