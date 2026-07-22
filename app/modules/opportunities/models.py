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


class Provider(Base):
    __tablename__ = "providers"
    __table_args__ = (
        CheckConstraint("name = trim(name)", name="ck_providers_name_trimmed"),
        UniqueConstraint("name", name="uq_providers_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
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
        CheckConstraint("intake_year IS NULL OR intake_year >= 2000", name="ck_intake_year_range"),
        UniqueConstraint(
            "provider_id",
            "name",
            "country",
            "intake_year",
            name="uq_opportunities_provider_name_country_intake",
        ),
        Index("ix_opportunities_country_degree", "country", "degree_level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"), index=True)
    university_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("universities.id"))
    name: Mapped[str] = mapped_column(String(255))
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
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
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


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("url = trim(url)", name="ck_sources_url_trimmed"),
        UniqueConstraint("opportunity_id", "url", name="uq_sources_opportunity_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
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
