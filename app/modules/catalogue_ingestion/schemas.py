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
    IngestionRunRetryClass,
    IngestionRunStage,
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
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    # Retained only to reject callers that still expect HTTP work execution.
    process_now: Literal[False] = False


class ExtractionUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost: Decimal = Field(default=Decimal("0"), ge=0)
    latency_ms: int = Field(default=0, ge=0)


class ExtractionResult(BaseModel):
    output: CatalogueExtractionOutput
    usage: ExtractionUsage


class IngestionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_label: str
    source_fingerprint: str
    idempotency_key: str
    input_kind: IngestionInputKind
    operator_url: str | None
    mode: IngestionMode
    status: IngestionRunStatus
    stage: IngestionRunStage
    dry_run: bool
    checkpoint_cursor: int
    max_candidates: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    aggregate_summary: dict[str, object]
    failure_code: str | None
    retry_class: IngestionRunRetryClass | None
    max_attempts: int
    attempt_count: int
    next_attempt_at: datetime | None
    claimed_by: str | None
    claimed_at: datetime | None
    claimed_until: datetime | None
    # Fencing tokens are credentials. Operators may see lease state, never its token.
    lease_active: bool = False
    dead_lettered_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class OperatorArtifactStatus(StrictExtractionModel):
    id: uuid.UUID
    final_url: str
    content_type: str
    content_hash: str
    extraction_method: str
    parser_version: str | None
    page_count: int | None
    byte_count: int
    character_count: int
    evidence_block_count: int
    canonicalization_versions: list[str]
    ocr_decision: str
    ocr_reason: str
    browser_decision: str
    browser_reason: str


class OperatorSourceRoutingStatus(StrictExtractionModel):
    role: str
    cycle: str
    classifier_version: str
    deterministic_signals: list[str]
    ambiguity_reason: str | None
    requires_manual_review: bool
    applicable_objectives: list[str]


class OperatorSourceStatus(StrictExtractionModel):
    id: uuid.UUID
    url: str
    final_url: str | None
    source_role: CandidateSourceRole
    status: str
    is_official: bool
    trust_tier: int | None
    failure_code: str | None
    artifacts: list[OperatorArtifactStatus]
    routing: list[OperatorSourceRoutingStatus]


class OperatorExtractionAttemptStatus(StrictExtractionModel):
    id: uuid.UUID
    source_id: uuid.UUID
    provider: str
    model: str
    schema_version: str
    prompt_hash: str
    status: str
    error_code: str | None
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    latency_ms: int
    created_at: datetime


class OperatorCandidateStatus(StrictExtractionModel):
    id: uuid.UUID
    seed_index: int
    status: CandidateStatus
    failure_code: str | None
    accepted_claim_count: int
    rejected_claim_count: int
    conflict_count: int
    objective_coverage: dict[str, str]
    missing_mandatory_objectives: list[str]
    sources: list[OperatorSourceStatus]
    attempts: list[OperatorExtractionAttemptStatus]


class OperatorRunStatusResponse(IngestionRunResponse):
    """Safe operational lineage; deliberately excludes artifacts' source text."""

    terminal_failure: bool
    candidates: list[OperatorCandidateStatus]
    executed_objective_count: int
    reused_objective_count: int


class ReviewFactScope(StrictExtractionModel):
    cycle_key: str | None
    track_key: str | None
    institution_key: str | None
    programme_key: str | None


class ReviewEvidenceBlock(StrictExtractionModel):
    artifact_id: uuid.UUID
    block_id: str
    canonicalization_version: str
    start_offset: int
    end_offset: int
    locator: dict[str, int]
    text: str
    text_format: Literal["plain_text"] = "plain_text"


class ReviewProposedFact(StrictExtractionModel):
    entity_type: str
    entity_key: str
    field_path: str
    value: dict[str, object]
    scope: ReviewFactScope
    source_url: str
    source_role: CandidateSourceRole
    source_content_role: str | None
    authority_tier: Literal["T0", "T1", "T2", "T3", "unresolved"]
    evidence: ReviewEvidenceBlock


class ReviewAuditHistoryItem(StrictExtractionModel):
    action: str
    actor_user_id: uuid.UUID | None
    reason: str | None
    created_at: datetime
    integrity_hash: str


class CandidateReviewProjectionResponse(StrictExtractionModel):
    candidate_id: uuid.UUID
    candidate_status: CandidateStatus
    proposed_facts: list[ReviewProposedFact]
    conflicts: list[str]
    rejected_claims: list[str]
    missing_mandatory_objectives: list[str]
    audit_history: list[ReviewAuditHistoryItem]


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
