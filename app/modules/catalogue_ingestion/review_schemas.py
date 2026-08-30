"""Administrator contracts for proposal review, materialization, and publication readiness."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.catalogue_ingestion.review_models import CatalogueProposalState

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class CatalogueProposalVersionRequest(BaseModel):
    expected_proposal_hash: str = Field(pattern=_SHA256_PATTERN)
    notes: str | None = Field(default=None, max_length=2000)


class CatalogueProposalReasonRequest(BaseModel):
    expected_proposal_hash: str = Field(pattern=_SHA256_PATTERN)
    reason: str = Field(min_length=10, max_length=2000)


class CatalogueCandidateReviewResponse(BaseModel):
    candidate_id: uuid.UUID
    review_id: uuid.UUID | None
    state: CatalogueProposalState
    proposal_schema_version: str | None
    proposal_hash: str | None
    current_proposal_hash: str | None
    approved_proposal_hash: str | None
    proposal_changed_since_review: bool
    review_revision: int
    reviewed_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_reason: str | None
    materialization_revision: str | None
    materialization_attempt_count: int
    materialization_failure_code: str | None
    materialization_failure_reason: str | None
    opportunity_id: uuid.UUID | None
    materialized_at: datetime | None
    publication_ready_at: datetime | None
    published_at: datetime | None
    readiness_blockers: list[str] = Field(default_factory=list)


class CataloguePublicationReadinessResponse(BaseModel):
    candidate_id: uuid.UUID
    opportunity_id: uuid.UUID | None
    proposal_hash: str | None
    ready: bool
    blockers: list[str]
    official_source_id: uuid.UUID | None = None


__all__ = [
    "CatalogueCandidateReviewResponse",
    "CatalogueProposalReasonRequest",
    "CatalogueProposalVersionRequest",
    "CataloguePublicationReadinessResponse",
]
