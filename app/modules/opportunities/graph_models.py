"""Normalized Scholarship Intelligence Graph entities introduced in PR1.

These tables extend the canonical ``opportunities`` catalogue. They do not
create a second scholarship identity or a publication path.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import enum_values, utc_now
from app.modules.opportunities.models import DegreeLevel


class RelationshipKind(StrEnum):
    SAME_SCHOLARSHIP = "same_scholarship"
    SAME_SCHEME_TRACK = "same_scheme_track"
    PARTICIPATING_INSTITUTION = "participating_institution"
    ELIGIBLE_PROGRAMME = "eligible_programme"
    INSTITUTION_SPECIFIC_REQUIREMENT = "institution_specific_requirement"
    INSTITUTION_SPECIFIC_DEADLINE = "institution_specific_deadline"
    INDEPENDENT_UNIVERSITY_SCHOLARSHIP = "independent_university_scholarship"
    INDEPENDENT_GOVERNMENT_SCHOLARSHIP = "independent_government_scholarship"
    INDEPENDENT_FOUNDATION_SCHOLARSHIP = "independent_foundation_scholarship"
    CO_FUNDED_AWARD = "co_funded_award"
    SUCCESSOR = "successor"
    PREDECESSOR = "predecessor"
    DUPLICATE = "duplicate"
    UNRESOLVED = "unresolved"


class ScholarshipAlias(Base):
    __tablename__ = "scholarship_aliases"
    __table_args__ = (
        UniqueConstraint(
            "scholarship_id",
            "normalized_alias",
            name="uq_scholarship_alias_normalized",
        ),
        Index("ix_scholarship_aliases_normalized", "normalized_alias"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(255))
    normalized_alias: Mapped[str] = mapped_column(String(255))
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


class ScholarshipRelationship(Base):
    """A reviewed or proposed relationship between two canonical scholarships."""

    __tablename__ = "scholarship_relationships"
    __table_args__ = (
        CheckConstraint(
            "scholarship_id != related_scholarship_id",
            name="ck_scholarship_relationships_not_self",
        ),
        UniqueConstraint(
            "scholarship_id",
            "related_scholarship_id",
            "relationship_kind",
            name="uq_scholarship_relationship_kind",
        ),
        Index("ix_scholarship_relationships_related", "related_scholarship_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    related_scholarship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE")
    )
    relationship_kind: Mapped[RelationshipKind] = mapped_column(
        Enum(
            RelationshipKind,
            name="scholarship_relationship_kind",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
            length=64,
        ),
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)
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


class Institution(Base):
    __tablename__ = "institutions"
    __table_args__ = (UniqueConstraint("slug", name="uq_institutions_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255))
    institution_type: Mapped[str] = mapped_column(String(64))
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    official_domain: Mapped[str | None] = mapped_column(String(255))
    official_website: Mapped[str | None] = mapped_column(String(2048))
    identity_status: Mapped[str | None] = mapped_column(String(64), index=True)
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


class InstitutionAlias(Base):
    __tablename__ = "institution_aliases"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "normalized_alias",
            name="uq_institution_alias_normalized",
        ),
        Index("ix_institution_aliases_normalized", "normalized_alias"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(255))
    normalized_alias: Mapped[str] = mapped_column(String(255))
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


class ApplicationTrack(Base):
    __tablename__ = "application_tracks"
    __table_args__ = (
        UniqueConstraint("cycle_id", "code", name="uq_application_tracks_cycle_code"),
        Index("ix_application_tracks_scholarship_cycle", "scholarship_id", "cycle_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_cycles.id", ondelete="CASCADE"), index=True
    )
    parent_track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_tracks.id", ondelete="SET NULL")
    )
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(255))
    track_type: Mapped[str] = mapped_column(String(64), index=True)
    application_method: Mapped[str | None] = mapped_column(Text)
    application_url: Mapped[str | None] = mapped_column(String(2048))
    decision_authority_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL")
    )
    status: Mapped[str | None] = mapped_column(String(64), index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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


class InstitutionParticipation(Base):
    __tablename__ = "institution_participations"
    __table_args__ = (
        UniqueConstraint(
            "cycle_id",
            "track_id",
            "institution_id",
            "role",
            name="uq_institution_participation_scope_role",
        ),
        Index(
            "ix_institution_participations_scholarship_institution",
            "scholarship_id",
            "institution_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_cycles.id", ondelete="CASCADE"), index=True
    )
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_tracks.id", ondelete="CASCADE"), index=True, nullable=True
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(64))
    participation_status: Mapped[str | None] = mapped_column(String(64), index=True)
    application_url: Mapped[str | None] = mapped_column(String(2048))
    notes: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class AcademicProgramme(Base):
    __tablename__ = "academic_programmes"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "slug",
            name="uq_academic_programmes_institution_slug",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    canonical_name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255))
    degree_level: Mapped[DegreeLevel | None] = mapped_column(String(32), index=True)
    field_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    programme_url: Mapped[str | None] = mapped_column(String(2048))
    active_status: Mapped[str | None] = mapped_column(String(64), index=True)
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


class TrackProgramme(Base):
    __tablename__ = "track_programmes"
    __table_args__ = (
        UniqueConstraint(
            "cycle_id",
            "track_id",
            "institution_id",
            "programme_id",
            name="uq_track_programmes_scope_programme",
        ),
        Index("ix_track_programmes_scholarship_cycle", "scholarship_id", "cycle_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_cycles.id", ondelete="CASCADE"), index=True
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application_tracks.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_programmes.id", ondelete="CASCADE"), index=True
    )
    eligibility_status: Mapped[str | None] = mapped_column(String(64), index=True)
    funding_status: Mapped[str | None] = mapped_column(String(64), index=True)
    application_url: Mapped[str | None] = mapped_column(String(2048))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
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
