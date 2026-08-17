import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.auth.models import User, enum_values, utc_now
from app.modules.opportunities.evidence_models import OfficialityStatus, SourceOwnerType


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


class FundingCoverageStatus(StrEnum):
    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    NOT_COVERED = "not_covered"
    UNKNOWN = "unknown"


class FundingClassification(StrEnum):
    FULLY_FUNDED = "fully_funded"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class ApplicationFeeStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    WAIVER_AVAILABLE = "waiver_available"
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


class IndependenceStatus(StrEnum):
    CONFIRMED_INDEPENDENT = "confirmed_independent"
    SAME_SCHEME = "same_scheme"
    DUPLICATE = "duplicate"
    UNRESOLVED = "unresolved"
    LEGACY_UNREVIEWED = "legacy_unreviewed"


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
        CheckConstraint(
            "parent_scholarship_id IS NULL OR parent_scholarship_id <> id",
            name="ck_opportunities_parent_not_self",
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
        Index(
            "uq_opportunity_canonical_slug",
            "canonical_slug",
            unique=True,
            sqlite_where=text("canonical_slug IS NOT NULL"),
            postgresql_where=text("canonical_slug IS NOT NULL"),
        ),
        Index(
            "ix_opportunity_provider_kind",
            "canonical_provider_id",
            "entity_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"), index=True)
    university_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("universities.id"))
    name: Mapped[str] = mapped_column(String(255))
    canonical_slug: Mapped[str | None] = mapped_column(String(255))
    entity_kind: Mapped[str] = mapped_column(
        String(32), default="scholarship", server_default="scholarship"
    )
    canonical_provider_id: Mapped[uuid.UUID | None] = mapped_column()
    parent_scholarship_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL")
    )
    independence_status: Mapped[IndependenceStatus] = mapped_column(
        Enum(
            IndependenceStatus,
            name="independence_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=IndependenceStatus.LEGACY_UNREVIEWED,
        server_default=IndependenceStatus.LEGACY_UNREVIEWED.value,
    )
    publication_completeness: Mapped[str] = mapped_column(
        String(32), default="incomplete", server_default="incomplete"
    )
    current_cycle_id: Mapped[uuid.UUID | None] = mapped_column()
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    funding_classification: Mapped[FundingClassification] = mapped_column(
        Enum(
            FundingClassification,
            name="funding_classification",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=FundingClassification.UNKNOWN,
        index=True,
    )
    funding_policy: Mapped[str | None] = mapped_column(Text)
    tuition_coverage_status: Mapped[FundingCoverageStatus] = mapped_column(
        Enum(
            FundingCoverageStatus,
            name="funding_coverage_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=FundingCoverageStatus.UNKNOWN,
    )
    stipend_coverage_status: Mapped[FundingCoverageStatus] = mapped_column(
        Enum(
            FundingCoverageStatus,
            name="funding_coverage_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=FundingCoverageStatus.UNKNOWN,
    )
    accommodation_coverage_status: Mapped[FundingCoverageStatus] = mapped_column(
        Enum(
            FundingCoverageStatus,
            name="funding_coverage_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=FundingCoverageStatus.UNKNOWN,
    )
    travel_coverage_status: Mapped[FundingCoverageStatus] = mapped_column(
        Enum(
            FundingCoverageStatus,
            name="funding_coverage_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=FundingCoverageStatus.UNKNOWN,
    )
    insurance_coverage_status: Mapped[FundingCoverageStatus] = mapped_column(
        Enum(
            FundingCoverageStatus,
            name="funding_coverage_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=FundingCoverageStatus.UNKNOWN,
    )
    fees_coverage_status: Mapped[FundingCoverageStatus] = mapped_column(
        Enum(
            FundingCoverageStatus,
            name="funding_coverage_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=FundingCoverageStatus.UNKNOWN,
    )
    application_fee_status: Mapped[ApplicationFeeStatus] = mapped_column(
        Enum(
            ApplicationFeeStatus,
            name="application_fee_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=ApplicationFeeStatus.UNKNOWN,
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
        CheckConstraint("version >= 1", name="ck_opportunity_cycles_version_positive"),
        UniqueConstraint(
            "opportunity_id",
            "label",
            name="uq_opportunity_cycles_opportunity_label",
        ),
        Index(
            "uq_opportunity_cycles_one_current",
            "opportunity_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str | None] = mapped_column(String(255))
    intake_year: Mapped[int | None] = mapped_column()
    application_opening_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(32), index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    is_current: Mapped[bool] = mapped_column(default=False)
    is_rolling: Mapped[bool] = mapped_column(default=False)
    is_archived: Mapped[bool] = mapped_column(default=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    opportunity: Mapped[Opportunity] = relationship(back_populates="cycles")


class EligibilityRule(Base):
    __tablename__ = "eligibility_rules"
    __table_args__ = (
        CheckConstraint(
            "track_id IS NULL OR cycle_id IS NOT NULL",
            name="ck_eligibility_rules_track_requires_cycle",
        ),
        CheckConstraint(
            "programme_id IS NULL OR institution_id IS NOT NULL",
            name="ck_eligibility_rules_programme_requires_institution",
        ),
        Index(
            "ix_eligibility_rules_graph_scope",
            "opportunity_id",
            "cycle_id",
            "track_id",
            "institution_id",
            "programme_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_cycles.id", ondelete="CASCADE"), index=True
    )
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_tracks.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_programmes.id", ondelete="CASCADE"), index=True
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
    value_keys: Mapped[list["EligibilityRuleValue"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )
    source: Mapped["Source | None"] = relationship()
    source_excerpt: Mapped["SourceExcerpt | None"] = relationship()


class EligibilityRuleValue(Base):
    __tablename__ = "eligibility_rule_values"
    __table_args__ = (
        UniqueConstraint("rule_id", "value_key", name="uq_eligibility_rule_value_key"),
        Index("ix_eligibility_rule_values_value_key", "value_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eligibility_rules.id", ondelete="CASCADE"), index=True
    )
    value_key: Mapped[str] = mapped_column(String(120))

    rule: Mapped[EligibilityRule] = relationship(back_populates="value_keys")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("url = trim(url)", name="ck_sources_url_trimmed"),
        UniqueConstraint("opportunity_id", "url", name="uq_sources_opportunity_url"),
        UniqueConstraint(
            "opportunity_id",
            "normalized_url",
            name="uq_sources_opportunity_normalized_url",
        ),
        Index(
            "ix_sources_review_status_freshness",
            "verification_status",
            "last_verified_at",
            "opportunity_id",
        ),
        Index(
            "ix_sources_monitor_claim",
            "monitor_next_check_at",
            "monitor_claimed_until",
            "verification_status",
        ),
        Index("ix_sources_owner", "source_owner_type", "source_owner_id"),
        Index("ix_sources_officiality_active", "officiality_status", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str | None] = mapped_column(String(2048), index=True)
    normalized_url: Mapped[str | None] = mapped_column(String(2048), index=True)
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    source_owner_type: Mapped[SourceOwnerType] = mapped_column(
        Enum(
            SourceOwnerType,
            name="source_owner_type",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=SourceOwnerType.UNKNOWN,
        server_default=SourceOwnerType.UNKNOWN.value,
        index=True,
    )
    source_owner_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    officiality_status: Mapped[OfficialityStatus] = mapped_column(
        Enum(
            OfficialityStatus,
            name="officiality_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=OfficialityStatus.UNRESOLVED,
        server_default=OfficialityStatus.UNRESOLVED.value,
        index=True,
    )
    officiality_reason: Mapped[str | None] = mapped_column(Text)
    robots_status: Mapped[str | None] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(255))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", index=True
    )
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
    monitor_next_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    monitor_claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    monitor_failure_count: Mapped[int] = mapped_column(default=0)
    hash_algorithm: Mapped[str] = mapped_column(
        String(16), default="sha256", server_default="sha256"
    )
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
    hash_algorithm: Mapped[str] = mapped_column(
        String(16), default="sha256", server_default="sha256"
    )
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
