from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from app.modules.opportunities.models import (
    ApplicationWindowState,
    DataConfidence,
    DegreeLevel,
    EligibilityOperator,
    EligibilityRuleType,
    FundingType,
    OpportunityStatus,
    SourceType,
    VerificationStatus,
)

EligibilityRuleValue = str | int | float | list[str | int | float]


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
    content_hash: str | None = Field(default=None, min_length=32, max_length=64)
    relevant_excerpt: str = Field(min_length=20)
    verification_status: VerificationStatus = VerificationStatus.NEEDS_REVIEW


class OpportunityCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    provider_name: str = Field(min_length=2, max_length=255)
    provider_website_url: HttpUrl | None = None
    university_name: str | None = Field(default=None, min_length=2, max_length=255)
    university_website_url: HttpUrl | None = None
    country: str = Field(min_length=2, max_length=100)
    degree_level: DegreeLevel
    field_eligibility: str | None = None
    nationality_eligibility: str | None = None
    application_opening_date: datetime | None = None
    application_deadline: datetime | None = None
    intake_year: int | None = Field(default=None, ge=2000, le=2100)
    funding_type: FundingType = FundingType.UNKNOWN
    tuition_coverage: str | None = None
    monthly_stipend_amount: Decimal | None = Field(default=None, ge=0)
    monthly_stipend_currency: str | None = Field(default=None, min_length=3, max_length=3)
    accommodation_coverage: str | None = None
    travel_allowance: str | None = None
    health_insurance: str | None = None
    application_fee_info: str | None = None
    english_language_requirement: str | None = None
    standardized_test_requirement: str | None = None
    minimum_academic_requirement: str | None = None
    required_documents: list[str] = Field(default_factory=list)
    application_method: str | None = None
    application_url: HttpUrl | None = None
    status: OpportunityStatus = OpportunityStatus.DRAFT
    data_confidence: DataConfidence = DataConfidence.LOW
    notes: str | None = None
    eligibility_warnings: list[str] = Field(default_factory=list)
    eligibility_rules: list[EligibilityRuleCreate] = Field(default_factory=list)
    application_cycles: list[OpportunityCycleCreate] = Field(default_factory=list)
    source: SourceCreate

    @field_validator("name", "provider_name", "university_name", "country", mode="before")
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
        return [item.strip() for item in values if item.strip()]

    @model_validator(mode="after")
    def validate_dates_and_funding(self) -> OpportunityCreate:
        if (
            self.application_opening_date is not None
            and self.application_deadline is not None
            and self.application_deadline < self.application_opening_date
        ):
            raise ValueError("Application deadline cannot be before the opening date")

        funding_fields = [
            self.tuition_coverage,
            self.monthly_stipend_amount,
            self.accommodation_coverage,
            self.travel_allowance,
            self.health_insurance,
        ]
        if self.funding_type is FundingType.FULL and not any(funding_fields):
            raise ValueError("Full funding requires explicit structured coverage evidence")

        if self.monthly_stipend_amount is not None and self.monthly_stipend_currency is None:
            raise ValueError("Monthly stipend currency is required when amount is present")

        return self


class VerificationUpdate(BaseModel):
    source_id: uuid.UUID | None = None
    verification_status: VerificationStatus
    notes: str | None = None


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
    verification_status: VerificationStatus
    last_verified_at: datetime | None


class SourceExcerptCreate(BaseModel):
    section_label: str | None = Field(default=None, max_length=255)
    locator: str | None = Field(default=None, max_length=255)
    text: str = Field(min_length=20)
    content_hash: str | None = Field(default=None, min_length=32, max_length=64)

    @field_validator("text", "section_label", "locator", mode="before")
    @classmethod
    def strip_excerpt_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class SourceExcerptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    section_label: str | None
    locator: str | None
    text: str
    content_hash: str | None
    captured_at: datetime


class SourceCheckRequest(BaseModel):
    content_hash: str | None = Field(default=None, min_length=32, max_length=64)
    observed_at: datetime | None = None
    change_summary: str | None = Field(default=None, max_length=2000)
    excerpt: SourceExcerptCreate | None = None


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
    application_deadline: datetime | None
    funding_type: FundingType
    funding_summary: str
    verification_status: VerificationStatus
    last_verified_at: datetime | None
    official_source_url: str
    application_window_state: ApplicationWindowState
    source_is_fresh: bool


class OpportunitySearchResponse(BaseModel):
    items: list[OpportunitySummaryResponse]
    pagination: PaginationMeta


class OpportunityDetailResponse(OpportunitySummaryResponse):
    field_eligibility: str | None
    nationality_eligibility: str | None
    intake_year: int | None
    tuition_coverage: str | None
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
