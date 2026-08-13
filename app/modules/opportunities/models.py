import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.auth.models import User, enum_values, utc_now


class DegreeLevel(StrEnum):
    BACHELORS = "bachelors"
    MASTERS = "masters"
    PHD = "phd"
    POSTDOC = "postdoc"
    SHORT_COURSE = "short_course"


class FundingType(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    TUITION_ONLY = "tuition_only"
    STIPEND_ONLY = "stipend_only"
    UNKNOWN = "unknown"


class OpportunityStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class SourceType(StrEnum):
    OFFICIAL = "official"
    GOVERNMENT = "government"
    UNIVERSITY = "university"
    PROVIDER = "provider"
    OTHER = "other"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    NEEDS_REVIEW = "needs_review"
    OFFICIALLY_VERIFIED = "officially_verified"
    EXPIRED = "expired"
    CONFLICTING_INFORMATION = "conflicting_information"
    ARCHIVED = "archived"


class DataConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DuplicateSuggestionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED_DUPLICATE = "confirmed_duplicate"
    DISMISSED = "dismissed"


class ApplicationWindowState(StrEnum):
    UPCOMING = "upcoming"
    OPEN = "open"
    CLOSED = "closed"
    ROLLING = "rolling"
    DEADLINE_UNKNOWN = "deadline_unknown"
    ARCHIVED = "archived"


class EligibilityRuleType(StrEnum):
    NATIONALITY = "nationality"
    RESIDENCE = "residence"
    TARGET_DEGREE = "target_degree"
    FIELD = "field"
    CGPA = "cgpa"
    PERCENTAGE = "percentage"
    IELTS = "ielts"
    TOEFL = "toefl"
    WORK_EXPERIENCE_MONTHS = "work_experience_months"
    APPLICATION_WINDOW = "application_window"
    STUDY_MODE = "study_mode"
    INTAKE_YEAR = "intake_year"
    CURRENT_EDUCATION_LEVEL = "current_education_level"
    ENGLISH_TEST_STATUS = "english_test_status"
    GRE_STATUS = "gre_status"
    DUOLINGO = "duolingo"
    GRE = "gre"


class EligibilityOperator(StrEnum):
    EQUALS = "equals"
    IN = "in"
    NOT_IN = "not_in"
    GTE = "gte"
    LTE = "lte"


class Provider(Base):
    __tablename__ = "providers"
    __table_args__ = (
        CheckConstraint("name = trim(name)", name="ck_providers_name_trimmed"),
        UniqueConstraint("name", name="uq_providers_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    canonical_id: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    website_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="provider")


class University(Base):
    __tablename__ = "universities"
    __table_args__ = (
        CheckConstraint("name = trim(name)", name="ck_universities_name_trimmed"),
        UniqueConstraint("name", "country", name="uq_universities_name_country"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    country: Mapped[str] = mapped_column(String(100))
    website_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="university")


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint("name = trim(name)", name="ck_opportunities_name_trimmed"),
        CheckConstraint("country = trim(country)", name="ck_opportunities_country_trimmed"),
        CheckConstraint(
            "application_deadline IS NULL OR application_opening_date IS NULL "
            "OR application_deadline >= application_opening_date",
            name="ck_opportunities_deadline_after_opening",
        ),
        CheckConstraint(
            "monthly_stipend_amount IS NULL OR monthly_stipend_amount >= 0",
            name="ck_opportunities_non_negative_stipend",
        ),
        CheckConstraint(
            "intake_year IS NULL OR intake_year >= 2000",
            name="ck_intake_year_range",
        ),
        Index("ix_opportunities_country_degree", "country", "degree_level"),
        Index(
            "ix_opportunities_canonical_identity",
            "provider_id",
            "programme_family_id",
            "cycle_id",
            "degree_level",
            "funding_type",
        ),
        Index(
            "ix_opportunities_catalogue_window",
            "status",
            "catalogue_cycle_is_archived",
            "catalogue_application_opening_date",
            "catalogue_application_deadline",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"), index=True)
    university_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("universities.id"))
    name: Mapped[str] = mapped_column(String(255))
    programme_family_id: Mapped[str | None] = mapped_column(String(120), index=True)
    cycle_id: Mapped[str | None] = mapped_column(String(120), index=True)
    country: Mapped[str] = mapped_column(String(100), index=True)
    degree_level: Mapped[DegreeLevel] = mapped_column(
        Enum(
            DegreeLevel,
            name="degree_level",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        index=True,
    )
    field_eligibility: Mapped[str | None] = mapped_column(Text)
    nationality_eligibility: Mapped[str | None] = mapped_column(Text)
    application_opening_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # These fields mirror the cycle that controls the public catalogue.  They
    # make time-window filtering and ordering database-queryable without
    # discarding the historical application-cycle records.
    catalogue_application_opening_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    catalogue_application_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    catalogue_is_rolling: Mapped[bool] = mapped_column(default=False)
    catalogue_cycle_is_archived: Mapped[bool] = mapped_column(default=False, index=True)
    intake_year: Mapped[int | None] = mapped_column(index=True)
    funding_type: Mapped[FundingType] = mapped_column(
        Enum(
            FundingType,
            name="funding_type",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=FundingType.UNKNOWN,
        index=True,
    )
    tuition_coverage: Mapped[str | None] = mapped_column(Text)
    monthly_stipend_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    monthly_stipend_currency: Mapped[str | None] = mapped_column(String(3))
    accommodation_coverage: Mapped[str | None] = mapped_column(Text)
    travel_allowance: Mapped[str | None] = mapped_column(Text)
    health_insurance: Mapped[str | None] = mapped_column(Text)
    application_fee_info: Mapped[str | None] = mapped_column(Text)
    english_language_requirement: Mapped[str | None] = mapped_column(Text)
    standardized_test_requirement: Mapped[str | None] = mapped_column(Text)
    minimum_academic_requirement: Mapped[str | None] = mapped_column(Text)
    required_documents: Mapped[list[str]] = mapped_column(JSON, default=list)
    application_method: Mapped[str | None] = mapped_column(Text)
    application_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(
            OpportunityStatus,
            name="opportunity_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=OpportunityStatus.DRAFT,
        index=True,
    )
    data_confidence: Mapped[DataConfidence] = mapped_column(
        Enum(
            DataConfidence,
            name="data_confidence",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=DataConfidence.LOW,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    eligibility_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    provider: Mapped[Provider] = relationship(back_populates="opportunities")
    university: Mapped[University | None] = relationship(back_populates="opportunities")
    created_by: Mapped[User | None] = relationship()
    sources: Mapped[list["Source"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    verification_records: Mapped[list["VerificationRecord"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    duplicate_suggestions: Mapped[list["DuplicateSuggestion"]] = relationship(
        foreign_keys="DuplicateSuggestion.opportunity_id",
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )
    cycles: Mapped[list["OpportunityCycle"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    eligibility_rules: Mapped[list["EligibilityRule"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )


class OpportunityCycle(Base):
    """A historical or recurring application window; never overwrite a prior cycle."""

    __tablename__ = "opportunity_cycles"
    __table_args__ = (
        CheckConstraint(
            "application_deadline IS NULL OR application_opening_date IS NULL "
            "OR application_deadline >= application_opening_date",
            name="ck_opportunity_cycles_deadline_after_opening",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    intake_year: Mapped[int | None] = mapped_column()
    application_opening_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    is_rolling: Mapped[bool] = mapped_column(default=False)
    is_archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    opportunity: Mapped[Opportunity] = relationship(back_populates="cycles")


class EligibilityRule(Base):
    __tablename__ = "eligibility_rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    rule_type: Mapped[EligibilityRuleType] = mapped_column(
        Enum(
            EligibilityRuleType,
            name="eligibility_rule_type",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        )
    )
    operator: Mapped[EligibilityOperator] = mapped_column(
        Enum(
            EligibilityOperator,
            name="eligibility_operator",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        )
    )
    value_json: Mapped[object] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(64))
    grading_scale: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    required: Mapped[bool] = mapped_column(default=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    source_excerpt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_excerpts.id", ondelete="SET NULL")
    )
    confidence: Mapped[DataConfidence] = mapped_column(
        Enum(
            DataConfidence,
            name="eligibility_rule_confidence",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=DataConfidence.MEDIUM,
    )
    curator_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    opportunity: Mapped[Opportunity] = relationship(back_populates="eligibility_rules")
    source: Mapped["Source | None"] = relationship()
    source_excerpt: Mapped["SourceExcerpt | None"] = relationship()


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("url = trim(url)", name="ck_sources_url_trimmed"),
        UniqueConstraint("opportunity_id", "url", name="uq_sources_opportunity_url"),
        Index(
            "ix_sources_review_status_freshness",
            "verification_status",
            "last_verified_at",
            "opportunity_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str | None] = mapped_column(String(2048), index=True)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(
            SourceType,
            name="source_type",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=SourceType.OFFICIAL,
    )
    title: Mapped[str] = mapped_column(String(255))
    publication_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_collected: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    relevant_excerpt: Mapped[str] = mapped_column(Text)
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(
            VerificationStatus,
            name="verification_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=VerificationStatus.NEEDS_REVIEW,
        index=True,
    )

    opportunity: Mapped[Opportunity] = relationship(back_populates="sources")
    verified_by: Mapped[User | None] = relationship()
    excerpts: Mapped[list["SourceExcerpt"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class DuplicateSuggestion(Base):
    """A potential duplicate that must be confirmed by a human reviewer."""

    __tablename__ = "duplicate_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "matched_opportunity_id", name="uq_duplicate_suggestion_pair"
        ),
        Index("ix_duplicate_suggestions_status_score", "status", "score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    matched_opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    status: Mapped[DuplicateSuggestionStatus] = mapped_column(
        Enum(
            DuplicateSuggestionStatus,
            name="duplicate_suggestion_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=DuplicateSuggestionStatus.PENDING,
        index=True,
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    opportunity: Mapped[Opportunity] = relationship(
        foreign_keys=[opportunity_id], back_populates="duplicate_suggestions"
    )
    matched_opportunity: Mapped[Opportunity] = relationship(foreign_keys=[matched_opportunity_id])
    reviewed_by: Mapped[User | None] = relationship()


class SourceExcerpt(Base):
    """Immutable evidence snapshot captured from a source at review time."""

    __tablename__ = "source_excerpts"
    __table_args__ = (
        CheckConstraint("text = trim(text)", name="ck_source_excerpts_text_trimmed"),
        Index("ix_source_excerpts_source_captured", "source_id", "captured_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    section_label: Mapped[str | None] = mapped_column(String(255))
    locator: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    captured_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    source: Mapped[Source] = relationship(back_populates="excerpts")
    captured_by: Mapped[User | None] = relationship()


class VerificationRecord(Base):
    __tablename__ = "verification_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(
            VerificationStatus,
            name="verification_record_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        )
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    checked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    opportunity: Mapped[Opportunity] = relationship(back_populates="verification_records")
    source: Mapped[Source | None] = relationship()
    checked_by: Mapped[User | None] = relationship()
