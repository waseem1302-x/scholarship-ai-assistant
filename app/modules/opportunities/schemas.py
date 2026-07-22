import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.modules.opportunities.models import (
    DataConfidence,
    DegreeLevel,
    FundingType,
    OpportunityStatus,
    SourceType,
    VerificationStatus,
)


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
    def validate_dates_and_funding(self) -> "OpportunityCreate":
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


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    source_type: SourceType
    title: str
    relevant_excerpt: str
    verification_status: VerificationStatus
    last_verified_at: datetime | None


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


class AdminOpportunityResponse(OpportunityDetailResponse):
    sources: list[SourceResponse]
