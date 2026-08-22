"""Evidence and scoped-fact models for the Scholarship Intelligence Graph.

PR2 keeps publication behavior unchanged. These models provide immutable source
snapshots, field-level provenance, and scoped facts beneath the canonical
``opportunities`` scholarship identity introduced in PR1. Official-source
metadata is attached to the existing ``sources`` table rather than introducing
a second source identity.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import enum_values, utc_now


class EvidenceIntegrityError(RuntimeError):
    """Raised when immutable evidence or evidence boundaries are violated."""


class SourceOwnerType(StrEnum):
    PROVIDER = "provider"
    GOVERNMENT = "government"
    INSTITUTION = "institution"
    PROGRAMME = "programme"
    UNKNOWN = "unknown"


class OfficialityStatus(StrEnum):
    OFFICIAL = "official"
    SUPPORTING_OFFICIAL = "supporting_official"
    THIRD_PARTY = "third_party"
    UNRESOLVED = "unresolved"


class EvidenceSupportType(StrEnum):
    EXPLICIT = "explicit"
    PARTIAL = "partial"
    CONTRADICTS = "contradicts"
    UNKNOWN = "unknown"


class EvidenceValidatorStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    __table_args__ = (
        UniqueConstraint("source_id", "content_hash", name="uq_source_snapshots_source_hash"),
        CheckConstraint(
            "http_status >= 100 AND http_status <= 599",
            name="ck_snapshot_http_status",
        ),
        CheckConstraint("byte_count >= 0", name="ck_snapshot_byte_count_non_negative"),
        CheckConstraint(
            "character_count >= 0",
            name="ck_snapshot_character_count_non_negative",
        ),
        Index("ix_source_snapshots_source_fetched", "source_id", "fetched_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    http_status: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(128))
    normalized_text: Mapped[str] = mapped_column(Text)
    storage_reference: Mapped[str | None] = mapped_column(String(2048))
    extraction_method: Mapped[str] = mapped_column(String(64))
    language_code: Mapped[str | None] = mapped_column(String(16))
    byte_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    character_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fetch_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


@event.listens_for(SourceSnapshot, "before_update", propagate=True)
def _prevent_source_snapshot_update(*_: object) -> None:
    raise EvidenceIntegrityError("source snapshots are immutable; create a new snapshot")


@event.listens_for(SourceSnapshot, "before_delete", propagate=True)
def _prevent_source_snapshot_delete(*_: object) -> None:
    raise EvidenceIntegrityError("source snapshots cannot be deleted; supersede them")


class FieldEvidence(Base):
    __tablename__ = "field_evidence"
    __table_args__ = (
        CheckConstraint("excerpt_start >= 0", name="ck_field_evidence_start_non_negative"),
        CheckConstraint("excerpt_end >= excerpt_start", name="ck_field_evidence_end_after_start"),
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "field_path",
            "source_snapshot_id",
            "excerpt_start",
            "excerpt_end",
            "support_type",
            name="uq_field_evidence_claim_span",
        ),
        Index("ix_field_evidence_entity_field", "entity_type", "entity_id", "field_path"),
        Index(
            "ix_field_evidence_validation",
            "support_type",
            "validator_status",
            "source_snapshot_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    field_path: Mapped[str] = mapped_column(String(255))
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="RESTRICT"), index=True
    )
    excerpt: Mapped[str] = mapped_column(Text)
    excerpt_start: Mapped[int] = mapped_column(Integer)
    excerpt_end: Mapped[int] = mapped_column(Integer)
    support_type: Mapped[EvidenceSupportType] = mapped_column(
        Enum(
            EvidenceSupportType,
            name="evidence_support_type",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        index=True,
    )
    validator_status: Mapped[EvidenceValidatorStatus] = mapped_column(
        Enum(
            EvidenceValidatorStatus,
            name="evidence_validator_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=EvidenceValidatorStatus.PENDING,
        server_default=EvidenceValidatorStatus.PENDING.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


def _scope_constraints(table_name: str) -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(
            "track_id IS NULL OR cycle_id IS NOT NULL",
            name=f"ck_{table_name}_track_requires_cycle",
        ),
        CheckConstraint(
            "programme_id IS NULL OR institution_id IS NOT NULL",
            name=f"ck_{table_name}_programme_requires_institution",
        ),
    )


def _scope_index(table_name: str) -> Index:
    return Index(
        f"ix_{table_name}_scope",
        "scholarship_id",
        "cycle_id",
        "track_id",
        "institution_id",
        "programme_id",
    )


class ScopedDeadline(Base):
    __tablename__ = "scoped_deadlines"
    __table_args__ = (*_scope_constraints("scoped_deadlines"), _scope_index("scoped_deadlines"))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
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
    deadline_type: Mapped[str] = mapped_column(String(64), index=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    local_date: Mapped[date | None] = mapped_column(Date)
    deadline_precision: Mapped[str] = mapped_column(
        String(16), default="datetime", server_default="datetime"
    )
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    label: Mapped[str | None] = mapped_column(String(255))
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


class FundingComponent(Base):
    __tablename__ = "funding_components"
    __table_args__ = (*_scope_constraints("funding_components"), _scope_index("funding_components"))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
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
    component_type: Mapped[str] = mapped_column(String(64), index=True)
    coverage_status: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    frequency: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
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


class RequiredDocument(Base):
    __tablename__ = "required_documents"
    __table_args__ = (*_scope_constraints("required_documents"), _scope_index("required_documents"))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
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
    document_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(255))
    required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text)
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


class ApplicationStep(Base):
    __tablename__ = "application_steps"
    __table_args__ = (*_scope_constraints("application_steps"), _scope_index("application_steps"))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
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
    step_code: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    application_url: Mapped[str | None] = mapped_column(String(2048))
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
