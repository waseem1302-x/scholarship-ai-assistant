from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from app.modules.opportunities.models import (
    ApplicationFeeStatus,
    ApplicationWindowState,
    DataConfidence,
    DegreeLevel,
    DuplicateSuggestionStatus,
    EligibilityOperator,
    EligibilityRuleType,
    FundingClassification,
    FundingCoverageStatus,
    FundingType,
    OpportunityStatus,
    SourceType,
    VerificationStatus,
)

EligibilityRuleValue = str | int | float | list[str | int | float]
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def validate_sha256_hash(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not SHA256_HEX_PATTERN.fullmatch(normalized):
        raise ValueError("Content hash must be a lowercase SHA-256 hexadecimal digest")
    return normalized


class EligibilityRuleCreate(BaseModel):
    rule_type: EligibilityRuleType
    operator: EligibilityOperator
    value: EligibilityRuleValue
    unit: str | None = Field(default=None, max_length=64)
    grading_scale: Decimal | None = Field(default=None, gt=0, le=100)
    required: bool = True
    source_id: uuid.UUID | None = None
    source_excerpt_id: uuid.UUID | None = None
    confidence: DataConfidence = DataConfidence.MEDIUM
    curator_notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_rule_shape(self) -> EligibilityRuleCreate:
        set_operators = {EligibilityOperator.IN, EligibilityOperator.NOT_IN}
        numeric_rules = {
            EligibilityRuleType.CGPA,
            EligibilityRuleType.PERCENTAGE,
            EligibilityRuleType.IELTS,
            EligibilityRuleType.TOEFL,
            EligibilityRuleType.WORK_EXPERIENCE_MONTHS,
            EligibilityRuleType.DUOLINGO,
            EligibilityRuleType.GRE,
        }
        categorical_rules = set(EligibilityRuleType) - numeric_rules
        if self.rule_type in categorical_rules and self.operator not in set_operators | {
            EligibilityOperator.EQUALS
        }:
            raise ValueError("Categorical eligibility rules support equals, in, and not_in only")
        if self.operator in set_operators and not isinstance(self.value, list):
            raise ValueError("IN and NOT_IN rules require a list value")
        if self.operator not in set_operators and isinstance(self.value, list):
            raise ValueError("EQUALS, GTE, and LTE rules require a scalar value")
        values = self.value if isinstance(self.value, list) else [self.value]
        if self.rule_type in numeric_rules and not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in values
        ):
            raise ValueError("Numeric eligibility rules require numeric values")
        if self.rule_type not in numeric_rules and not all(
            isinstance(value, str) for value in values
        ):
            raise ValueError("Categorical eligibility rules require text values")
        if self.rule_type is EligibilityRuleType.CGPA and self.grading_scale is None:
            raise ValueError("CGPA rules require a grading_scale")
        return self


class OpportunityCycleCreate(BaseModel):
    intake_year: int | None = Field(default=None, ge=2000, le=2100)
    application_opening_date: datetime | None = None
    application_deadline: datetime | None = None
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    is_rolling: bool = False
    is_archived: bool = False

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        timezone = value.strip()
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone must be a valid IANA timezone") from exc
        return timezone

    @model_validator(mode="after")
    def validate_dates(self) -> OpportunityCycleCreate:
        if (
            self.application_opening_date
            and self.application_deadline
            and self.application_deadline < self.application_opening_date
        ):
            raise ValueError("Application deadline cannot be before the opening date")
        return self


class SourceCreate(BaseModel):
    url: HttpUrl
    source_type: SourceType = SourceType.OFFICIAL
    title: str = Field(min_length=3, max_length=255)
    publication_date: datetime | None = None
    hash_algorithm: Literal["sha256"] = "sha256"
    content_hash: str | None = None
    relevant_excerpt: str = Field(min_length=20, max_length=12_000)
    verification_status: VerificationStatus = VerificationStatus.NEEDS_REVIEW

    _validate_content_hash = field_validator("content_hash")(validate_sha256_hash)


class OpportunityCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    provider_name: str = Field(min_length=2, max_length=255)
    provider_canonical_id: str | None = Field(default=None, min_length=2, max_length=120)
    programme_family_id: str | None = Field(default=None, min_length=2, max_length=120)
    cycle_id: str | None = Field(default=None, min_length=2, max_length=120)
    provider_website_url: HttpUrl | None = None
    university_name: str | None = Field(default=None, min_length=2, max_length=255)
    university_website_url: HttpUrl | None = None
    country: str = Field(min_length=2, max_length=100)
    degree_level: DegreeLevel
    field_eligibility: str | None = Field(default=None, max_length=2_000)
    nationality_eligibility: str | None = Field(default=None, max_length=2_000)
    application_opening_date: datetime | None = None
    application_deadline: datetime | None = None
    intake_year: int | None = Field(default=None, ge=2000, le=2100)
    funding_type: FundingType = FundingType.UNKNOWN
    funding_policy: str | None = Field(default=None, min_length=20, max_length=2000)
    tuition_coverage_status: FundingCoverageStatus = FundingCoverageStatus.UNKNOWN
    stipend_coverage_status: FundingCoverageStatus = FundingCoverageStatus.UNKNOWN
    accommodation_coverage_status: FundingCoverageStatus = FundingCoverageStatus.UNKNOWN
    travel_coverage_status: FundingCoverageStatus = FundingCoverageStatus.UNKNOWN
    insurance_coverage_status: FundingCoverageStatus = FundingCoverageStatus.UNKNOWN
    fees_coverage_status: FundingCoverageStatus = FundingCoverageStatus.UNKNOWN
    application_fee_status: ApplicationFeeStatus = ApplicationFeeStatus.UNKNOWN
    tuition_coverage: str | None = Field(default=None, max_length=2_000)
    monthly_stipend_amount: Decimal | None = Field(default=None, ge=0)
    monthly_stipend_currency: str | None = Field(default=None, min_length=3, max_length=3)
    accommodation_coverage: str | None = Field(default=None, max_length=2_000)
    travel_allowance: str | None = Field(default=None, max_length=2_000)
    health_insurance: str | None = Field(default=None, max_length=2_000)
    application_fee_info: str | None = Field(default=None, max_length=2_000)
    english_language_requirement: str | None = Field(default=None, max_length=2_000)
    standardized_test_requirement: str | None = Field(default=None, max_length=2_000)
    minimum_academic_requirement: str | None = Field(default=None, max_length=2_000)
    required_documents: list[str] = Field(default_factory=list, max_length=30)
    application_method: str | None = Field(default=None, max_length=1_000)
    application_url: HttpUrl | None = None
    status: OpportunityStatus = OpportunityStatus.DRAFT
    data_confidence: DataConfidence = DataConfidence.LOW
    notes: str | None = Field(default=None, max_length=8_000)
    eligibility_warnings: list[str] = Field(default_factory=list, max_length=30)
    eligibility_rules: list[EligibilityRuleCreate] = Field(default_factory=list, max_length=20)
    application_cycles: list[OpportunityCycleCreate] = Field(default_factory=list)
    source: SourceCreate

    @field_validator(
        "name",
        "provider_name",
        "provider_canonical_id",
        "programme_family_id",
        "cycle_id",
        "university_name",
        "country",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("monthly_stipend_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("required_documents", "eligibility_warnings")
    @classmethod
    def clean_list(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values if item.strip()]
        if any(len(item) > 500 for item in cleaned):
            raise ValueError("List items must not exceed 500 characters")
        return cleaned

    @model_validator(mode="after")
    def validate_dates_and_funding(self) -> OpportunityCreate:
        if (
            self.application_opening_date is not None
            and self.application_deadline is not None
            and self.application_deadline < self.application_opening_date
        ):
            raise ValueError("Application deadline cannot be before the opening date")

        components = [
            self.tuition_coverage_status,
            self.stipend_coverage_status,
            self.accommodation_coverage_status,
            self.travel_coverage_status,
            self.insurance_coverage_status,
            self.fees_coverage_status,
        ]
        if self.funding_type is FundingType.FULL and (
            not self.funding_policy
            or any(component is not FundingCoverageStatus.CONFIRMED for component in components)
        ):
            raise ValueError(
                "Full funding requires a documented policy and confirmed tuition, stipend, "
                "accommodation, travel, insurance, and fee coverage"
            )

        if self.monthly_stipend_amount is not None and self.monthly_stipend_currency is None:
            raise ValueError("Monthly stipend currency is required when amount is present")

        return self


class VerificationUpdate(BaseModel):
    source_id: uuid.UUID | None = None
    verification_status: VerificationStatus
    notes: str | None = Field(default=None, max_length=2_000)


class ReviewAction(StrEnum):
    PUBLISH = "publish"
    HOLD_FOR_REVIEW = "hold_for_review"
    FLAG_CONFLICT = "flag_conflict"
    REQUEST_RECHECK = "request_recheck"
    RESOLVE_CONFLICT = "resolve_conflict"
    EXPIRE = "expire"
    ARCHIVE = "archive"


class ReviewActionRequest(BaseModel):
    action: ReviewAction
    source_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ImportFormat(StrEnum):
    JSON = "json"
    CSV = "csv"


class ImportRowStatus(StrEnum):
    IMPORTED = "imported"
    DRY_RUN_READY = "dry_run_ready"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    FAILED_VALIDATION = "failed_validation"


class OpportunityImportRequest(BaseModel):
    source_format: ImportFormat = ImportFormat.JSON
    dry_run: bool = False
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    csv_content: str | None = Field(default=None, max_length=200_000)

    @model_validator(mode="after")
    def validate_import_payload(self) -> OpportunityImportRequest:
        if self.source_format is ImportFormat.JSON and not self.rows:
            raise ValueError("JSON imports require at least one row")
        if self.source_format is ImportFormat.CSV and not (self.csv_content or "").strip():
            raise ValueError("CSV imports require csv_content")
        return self


class OpportunityImportRowResult(BaseModel):
    row_number: int
    status: ImportRowStatus
    opportunity_id: uuid.UUID | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DuplicateSuggestionDecision(BaseModel):
    is_duplicate: bool


class DuplicateSuggestionResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    opportunity_name: str
    matched_opportunity_id: uuid.UUID
    matched_opportunity_name: str
    score: Decimal
    status: DuplicateSuggestionStatus
    created_at: datetime


class DuplicateSuggestionSearchResponse(BaseModel):
    items: list[DuplicateSuggestionResponse]
    pagination: PaginationMeta


class OpportunityImportResponse(BaseModel):
    source_format: ImportFormat
    dry_run: bool
    total_rows: int
    imported_count: int
    duplicate_count: int
    failed_count: int
    results: list[OpportunityImportRowResult]


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    source_type: SourceType
    title: str
    relevant_excerpt: str
    hash_algorithm: str
    content_hash: str | None
    verification_status: VerificationStatus
    last_verified_at: datetime | None


class SourceExcerptCreate(BaseModel):
    section_label: str | None = Field(default=None, max_length=255)
    locator: str | None = Field(default=None, max_length=255)
    text: str = Field(min_length=20, max_length=12_000)
    hash_algorithm: Literal["sha256"] = "sha256"
    content_hash: str | None = None

    @field_validator("text", "section_label", "locator", mode="before")
    @classmethod
    def strip_excerpt_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    _validate_content_hash = field_validator("content_hash")(validate_sha256_hash)


class SourceExcerptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    section_label: str | None
    locator: str | None
    text: str
    hash_algorithm: str
    content_hash: str | None
    captured_at: datetime


class SourceCheckRequest(BaseModel):
    hash_algorithm: Literal["sha256"] = "sha256"
    content_hash: str | None = None
    observed_at: datetime | None = None
    change_summary: str | None = Field(default=None, max_length=2000)
    excerpt: SourceExcerptCreate | None = None

    _validate_content_hash = field_validator("content_hash")(validate_sha256_hash)


class SourceCheckResponse(BaseModel):
    source: SourceResponse
    changed: bool
    previous_hash: str | None
    current_hash: str | None
    public_visibility_blocked: bool
    excerpt: SourceExcerptResponse | None = None


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    count: int
    has_next: bool
    has_previous: bool


class DataQualitySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VerificationFreshness(StrEnum):
    RECENT = "recent"
    RECHECK_RECOMMENDED = "recheck_recommended"
    HISTORICAL = "historical"


class CatalogueDecisionTier(StrEnum):
    DECISION_READY = "decision_ready"
    INFORMATIONAL_ONLY = "informational_only"


class DataQualityIssueResponse(BaseModel):
    code: str
    severity: DataQualitySeverity
    message: str
    opportunity_id: uuid.UUID
    opportunity_name: str
    source_id: uuid.UUID | None = None


class DataQualityIssueSearchResponse(BaseModel):
    items: list[DataQualityIssueResponse]
    pagination: PaginationMeta


class OpportunitySummaryResponse(BaseModel):
    id: uuid.UUID
    name: str
    provider_name: str
    university_name: str | None
    country: str
    degree_level: DegreeLevel
    degree_levels: list[DegreeLevel]
    application_deadline: datetime | None
    application_opening_date: datetime | None = None
    application_timezone: str = "UTC"
    effective_cycle_id: uuid.UUID | None = None
    funding_type: FundingType
    funding_classification: FundingClassification
    funding_summary: str
    verification_status: VerificationStatus
    last_verified_at: datetime | None
    official_source_url: str
    application_window_state: ApplicationWindowState
    source_is_fresh: bool
    verification_freshness: VerificationFreshness
    funding_display_label: str
    catalogue_decision_tier: CatalogueDecisionTier
    structured_eligibility_complete: bool


class OpportunitySearchResponse(BaseModel):
    items: list[OpportunitySummaryResponse]
    pagination: PaginationMeta


class PublicFactScopeResponse(BaseModel):
    cycle_id: uuid.UUID | None = None
    track_id: uuid.UUID | None = None
    institution_id: uuid.UUID | None = None
    programme_id: uuid.UUID | None = None
    scholarship_programme_id: uuid.UUID | None = None


class PublicEvidenceReferenceResponse(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    field_path: str
    source_snapshot_id: uuid.UUID
    source_title: str
    source_url: HttpUrl
    content_hash: str
    excerpt: str
    excerpt_start: int
    excerpt_end: int
    last_verified_at: datetime | None
    verification_status: VerificationStatus


class PublicScopedFactResponse(BaseModel):
    id: uuid.UUID
    scope: PublicFactScopeResponse
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)


class PublicCycleResponse(PublicScopedFactResponse):
    label: str | None = None
    intake_year: int | None = None
    application_opening_date: datetime | None = None
    application_deadline: datetime | None = None
    status: str | None = None
    timezone: str | None = None
    is_rolling: bool | None = None


class PublicTrackResponse(PublicScopedFactResponse):
    code: str
    parent_track_id: uuid.UUID | None = None
    name: str | None = None
    track_type: str | None = None
    application_method: str | None = None
    application_url: HttpUrl | None = None
    status: str | None = None
    display_order: int = 0


class PublicProgrammeResponse(PublicScopedFactResponse):
    programme_key: str
    name: str | None = None
    programme_type: str | None = None
    degree_levels: list[str] = Field(default_factory=list)
    fields_of_study: list[str] = Field(default_factory=list)
    duration: str | None = None
    description: str | None = None
    application_route_keys: list[str] = Field(default_factory=list)
    display_order: int = 0


class PublicEligibilityResponse(PublicScopedFactResponse):
    rule_key: str
    rule_type: str | None = None
    operator: str | None = None
    value: dict[str, Any] | None = None
    unit: str | None = None
    required: bool | None = None
    condition: str | None = None
    is_exclusion: bool | None = None
    critical: bool | None = None
    original_text: str | None = None
    notes: str | None = None
    display_order: int = 0


class PublicDeadlineResponse(PublicScopedFactResponse):
    deadline_type: str | None = None
    deadline_at: datetime | None = None
    deadline_text: str | None = None
    local_date: date | None = None
    precision: str | None = None
    timezone: str | None = None
    varies_by: str | None = None
    label: str | None = None
    notes: str | None = None


class PublicFundingResponse(PublicScopedFactResponse):
    component_type: str | None = None
    coverage_status: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    frequency: str | None = None
    unit: str | None = None
    qualifier: str | None = None
    original_text: str | None = None
    description: str | None = None


class PublicDocumentResponse(PublicScopedFactResponse):
    document_key: str
    name: str | None = None
    required: bool | None = None
    condition: str | None = None
    submission_stage: str | None = None
    original_count: int | None = None
    copy_count: int | None = None
    translation_requirement: str | None = None
    certification_requirement: str | None = None
    form_year: int | None = None
    notes: str | None = None
    display_order: int = 0


class PublicApplicationStepResponse(PublicScopedFactResponse):
    step_code: str
    title: str | None = None
    stage_type: str | None = None
    required: bool | None = None
    actor_type: str | None = None
    actor_name: str | None = None
    outcome: str | None = None
    original_text: str | None = None
    description: str | None = None
    application_url: HttpUrl | None = None
    display_order: int = 0


class PublicEventResponse(PublicScopedFactResponse):
    event_key: str
    event_type: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    date_text: str | None = None
    precision: str | None = None
    timezone: str | None = None
    label: str | None = None
    notes: str | None = None
    display_order: int = 0


class PublicResourceResponse(PublicScopedFactResponse):
    resource_key: str
    title: str | None = None
    resource_type: str | None = None
    url: HttpUrl | None = None
    contact_type: str | None = None
    organization: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    original_text: str | None = None
    required: bool | None = None
    notes: str | None = None
    display_order: int = 0


class PublicScholarshipProjectionResponse(BaseModel):
    cycle: PublicCycleResponse | None = None
    tracks: list[PublicTrackResponse] = Field(default_factory=list)
    programmes: list[PublicProgrammeResponse] = Field(default_factory=list)
    eligibility: list[PublicEligibilityResponse] = Field(default_factory=list)
    deadlines: list[PublicDeadlineResponse] = Field(default_factory=list)
    funding: list[PublicFundingResponse] = Field(default_factory=list)
    documents: list[PublicDocumentResponse] = Field(default_factory=list)
    steps: list[PublicApplicationStepResponse] = Field(default_factory=list)
    events: list[PublicEventResponse] = Field(default_factory=list)
    resources: list[PublicResourceResponse] = Field(default_factory=list)
    evidence: list[PublicEvidenceReferenceResponse] = Field(default_factory=list)
    known_unknowns: list[str] = Field(default_factory=list)


class OpportunityDetailResponse(OpportunitySummaryResponse):
    projection: PublicScholarshipProjectionResponse = Field(
        default_factory=PublicScholarshipProjectionResponse
    )
    field_eligibility: str | None
    nationality_eligibility: str | None
    intake_year: int | None
    tuition_coverage: str | None
    funding_policy: str | None
    tuition_coverage_status: FundingCoverageStatus
    stipend_coverage_status: FundingCoverageStatus
    accommodation_coverage_status: FundingCoverageStatus
    travel_coverage_status: FundingCoverageStatus
    insurance_coverage_status: FundingCoverageStatus
    fees_coverage_status: FundingCoverageStatus
    application_fee_status: ApplicationFeeStatus
    monthly_stipend_amount: Decimal | None
    monthly_stipend_currency: str | None
    accommodation_coverage: str | None
    travel_allowance: str | None
    health_insurance: str | None
    application_fee_info: str | None
    english_language_requirement: str | None
    standardized_test_requirement: str | None
    minimum_academic_requirement: str | None
    required_documents: list[str]
    application_method: str | None
    application_url: str | None
    status: OpportunityStatus
    data_confidence: DataConfidence
    notes: str | None
    eligibility_warnings: list[str]
    source: SourceResponse
    eligibility_rules: list[EligibilityRuleCreate]


class AdminOpportunityResponse(OpportunityDetailResponse):
    sources: list[SourceResponse]


class AdminOpportunitySearchResponse(BaseModel):
    items: list[AdminOpportunityResponse]
    pagination: PaginationMeta


class ReviewQueueItemResponse(BaseModel):
    opportunity: AdminOpportunityResponse
    reasons: list[DataQualityIssueResponse]


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItemResponse]
    pagination: PaginationMeta
