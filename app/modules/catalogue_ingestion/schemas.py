"""Strict extraction and minimal administrator API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.modules.catalogue_ingestion.models import (
    CandidateSourceRole,
    CandidateStatus,
    IngestionInputKind,
    IngestionMode,
    IngestionRunStatus,
)
from app.modules.opportunities.models import (
    ApplicationFeeStatus,
    DataConfidence,
    DegreeLevel,
    EligibilityOperator,
    EligibilityRuleType,
    FundingCoverageStatus,
    FundingType,
)

EXTRACTION_SCHEMA_VERSION = "catalogue-extraction.v1"


class StrictExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedIdentity(StrictExtractionModel):
    name: str | None
    provider_name: str | None
    provider_canonical_id: str | None
    provider_website_url: str | None
    university_name: str | None
    university_website_url: str | None
    country: str | None
    country_code: str | None
    programme_family_id: str | None


class ExtractedStudy(StrictExtractionModel):
    degree_level: DegreeLevel | None
    field_eligibility: str | None
    intake_year: int | None
    cycle_id: str | None


class ExtractedFunding(StrictExtractionModel):
    funding_type: FundingType
    funding_policy: str | None
    tuition_coverage_status: FundingCoverageStatus
    stipend_coverage_status: FundingCoverageStatus
    accommodation_coverage_status: FundingCoverageStatus
    travel_coverage_status: FundingCoverageStatus
    insurance_coverage_status: FundingCoverageStatus
    fees_coverage_status: FundingCoverageStatus
    application_fee_status: ApplicationFeeStatus
    tuition_coverage: str | None
    monthly_stipend_amount: Decimal | None
    monthly_stipend_currency: str | None
    accommodation_coverage: str | None
    travel_allowance: str | None
    health_insurance: str | None
    application_fee_info: str | None


class ExtractedEligibilityRule(StrictExtractionModel):
    rule_type: EligibilityRuleType
    operator: EligibilityOperator
    value: str | int | float | list[str | int | float]
    unit: str | None
    grading_scale: Decimal | None
    required: bool
    confidence: DataConfidence


class ExtractedEligibility(StrictExtractionModel):
    nationality_eligibility: str | None
    minimum_academic_requirement: str | None
    english_language_requirement: str | None
    standardized_test_requirement: str | None
    rules: list[ExtractedEligibilityRule]


class ExtractedApplication(StrictExtractionModel):
    application_opening_date: datetime | None
    application_deadline: datetime | None
    timezone: str | None
    application_url: str | None
    application_method: str | None
    required_documents: list[str]
    is_rolling: bool


class FieldEvidence(StrictExtractionModel):
    field_path: str
    source_url: str
    section_label: str | None
    locator: str | None
    excerpt: str
    basis: Literal["explicit", "normalized", "unknown"]


class CatalogueExtractionOutput(StrictExtractionModel):
    identity: ExtractedIdentity
    study: ExtractedStudy
    funding: ExtractedFunding
    eligibility: ExtractedEligibility
    application: ExtractedApplication
    evidence: list[FieldEvidence]
    unknown_fields: list[str]
    conflicts: list[str]
    warnings: list[str]


class SeedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=255)
    provider: str | None = Field(default=None, max_length=255)
    university: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=100)
    cycle: str | None = Field(default=None, max_length=120)
    intake_year: int | None = Field(default=None, ge=2000, le=2100)
    possible_official_url: HttpUrl | None = None
    keywords: list[str] = Field(default_factory=list, max_length=20)


class DirectUrlIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    supporting_urls: list[HttpUrl] = Field(default_factory=list, max_length=9)
    target_name: str | None = Field(default=None, min_length=3, max_length=255)
    provider: str | None = Field(default=None, max_length=255)
    university: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=100)
    mode: IngestionMode = IngestionMode.CANDIDATE_ONLY
    dry_run: bool = True
    process_now: bool = True


class ExtractionUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost: Decimal = Field(default=Decimal("0"), ge=0)
    latency_ms: int = Field(default=0, ge=0)
    provider_request_id: str | None = Field(default=None, max_length=255)


class ExtractionResult(BaseModel):
    output: CatalogueExtractionOutput
    usage: ExtractionUsage


class IngestionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_label: str
    source_fingerprint: str
    input_kind: IngestionInputKind
    operator_url: str | None
    mode: IngestionMode
    status: IngestionRunStatus
    dry_run: bool
    checkpoint_cursor: int
    max_candidates: int
    configuration_revision: str | None = None
    configuration_fingerprint: str | None = None
    model_calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    aggregate_summary: dict[str, object]
    failure_code: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class SourceArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    final_url: str
    content_type: str
    content_hash: str
    extraction_method: str
    byte_count: int
    character_count: int
    created_at: datetime


class CandidateSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    final_url: str | None
    source_role: CandidateSourceRole
    is_official: bool
    trust_tier: int | None
    classification_reason: str
    content_type: str | None
    content_hash: str | None
    relevant_excerpt: str | None
    failure_code: str | None
    artifacts: list[SourceArtifactResponse] = Field(default_factory=list)


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    seed_index: int
    seed_name: str
    seed_provider: str | None
    seed_university: str | None
    seed_country: str | None
    seed_cycle: str | None
    seed_intake_year: int | None
    seed_official_url: str | None
    identity_hint_is_asserted: bool
    seed_keywords: list[str]
    status: CandidateStatus
    proposed_payload: dict[str, object] | None
    validation_errors: list[str]
    conflicts: list[str]
    duplicate_opportunity_ids: list[str]
    failure_code: str | None
    failure_reason: str | None
    opportunity_id: uuid.UUID | None
    sources: list[CandidateSourceResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class IngestionRunListResponse(BaseModel):
    items: list[IngestionRunResponse]
    total: int


class CandidateListResponse(BaseModel):
    items: list[CandidateResponse]
    total: int


class CandidateRetryRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class CandidateSubmitRequest(BaseModel):
    notes: str = Field(min_length=10, max_length=2000)
