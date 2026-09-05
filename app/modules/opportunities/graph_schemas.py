"""Administrator-facing graph and citation contracts."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class GraphModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class GraphTrackResponse(GraphModel):
    id: uuid.UUID
    parent_track_id: uuid.UUID | None
    code: str
    name: str
    track_type: str
    application_method: str | None
    application_url: str | None
    status: str | None
    display_order: int


class GraphInstitutionResponse(GraphModel):
    id: uuid.UUID
    canonical_name: str
    institution_type: str
    country_code: str | None
    official_domain: str | None
    official_website: str | None
    identity_status: str | None


class GraphInstitutionParticipationResponse(GraphModel):
    id: uuid.UUID
    track_id: uuid.UUID | None
    institution_id: uuid.UUID
    role: str
    participation_status: str | None
    application_url: str | None
    source_id: uuid.UUID | None


class GraphDeadlineResponse(GraphModel):
    id: uuid.UUID
    track_id: uuid.UUID | None
    institution_id: uuid.UUID | None
    deadline_type: str
    deadline_at: datetime
    local_date: date | None
    deadline_precision: str
    timezone: str | None
    label: str | None
    notes: str | None


class GraphFundingResponse(GraphModel):
    id: uuid.UUID
    track_id: uuid.UUID | None
    institution_id: uuid.UUID | None
    component_type: str
    coverage_status: str
    amount: Decimal | None
    currency: str | None
    frequency: str | None
    description: str | None


class GraphDocumentResponse(GraphModel):
    id: uuid.UUID
    track_id: uuid.UUID | None
    institution_id: uuid.UUID | None
    document_key: str
    name: str
    required: bool
    notes: str | None
    display_order: int


class GraphStepResponse(GraphModel):
    id: uuid.UUID
    track_id: uuid.UUID | None
    institution_id: uuid.UUID | None
    step_code: str
    title: str
    description: str | None
    application_url: str | None
    display_order: int


class GraphCitationResponse(GraphModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    field_path: str
    source_snapshot_id: uuid.UUID
    source_title: str
    source_url: str
    content_hash: str
    excerpt: str
    excerpt_start: int
    excerpt_end: int
    validator_status: str


class OpportunityGraphResponse(GraphModel):
    opportunity_id: uuid.UUID
    cycle_id: uuid.UUID
    intake_year: int | None
    degree_levels: list[str]
    tracks: list[GraphTrackResponse]
    institutions: list[GraphInstitutionResponse]
    institution_participations: list[GraphInstitutionParticipationResponse]
    deadlines: list[GraphDeadlineResponse]
    funding: list[GraphFundingResponse]
    documents: list[GraphDocumentResponse]
    steps: list[GraphStepResponse]
    citations: list[GraphCitationResponse]
