"""Operational entities for materializing rich catalogue claim graphs without identity loss."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import utc_now


class ScholarshipProgramme(Base):
    """Scholarship-scoped award offering, distinct from institution-owned programmes."""

    __tablename__ = "scholarship_programmes"
    __table_args__ = (
        UniqueConstraint("identity_key", name="uq_scholarship_programmes_identity"),
        Index("ix_scholarship_programmes_scope", "scholarship_id", "cycle_id", "programme_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_cycles.id", ondelete="CASCADE"), index=True
    )
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_tracks.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    identity_key: Mapped[str] = mapped_column(String(64), index=True)
    programme_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(255))
    programme_type: Mapped[str | None] = mapped_column(String(100), index=True)
    degree_levels: Mapped[list[str]] = mapped_column(JSON, default=list)
    fields_of_study: Mapped[list[str]] = mapped_column(JSON, default=list)
    duration: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    application_route_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class ScholarshipEligibilityRule(Base):
    """Eligibility, award-condition, quota, obligation, and continuation rule."""

    __tablename__ = "scholarship_eligibility_rules"
    __table_args__ = (
        UniqueConstraint("identity_key", name="uq_scholarship_eligibility_rules_identity"),
        Index(
            "ix_scholarship_eligibility_rules_scope",
            "scholarship_id",
            "cycle_id",
            "rule_type",
        ),
        Index(
            "ix_scholarship_eligibility_rules_critical",
            "scholarship_id",
            "critical",
            "rule_type",
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
        ForeignKey("application_tracks.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scholarship_programmes.id", ondelete="CASCADE"), index=True
    )
    identity_key: Mapped[str] = mapped_column(String(64), index=True)
    rule_key: Mapped[str] = mapped_column(String(120), index=True)
    rule_type: Mapped[str] = mapped_column(String(100), index=True)
    operator: Mapped[str] = mapped_column(String(32), index=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    unit: Mapped[str | None] = mapped_column(String(64))
    required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    condition: Mapped[str | None] = mapped_column(Text)
    is_exclusion: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    critical: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    original_text: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class OpportunityEvent(Base):
    """Application, nomination, interview, examination, selection, and result lifecycle events."""

    __tablename__ = "opportunity_events"
    __table_args__ = (
        UniqueConstraint("identity_key", name="uq_opportunity_events_identity"),
        Index("ix_opportunity_events_scope", "scholarship_id", "cycle_id", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scholarship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_cycles.id", ondelete="CASCADE"), index=True
    )
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_tracks.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scholarship_programmes.id", ondelete="CASCADE"), index=True
    )
    identity_key: Mapped[str] = mapped_column(String(64), index=True)
    event_key: Mapped[str] = mapped_column(String(120), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_text: Mapped[str | None] = mapped_column(String(500))
    precision: Mapped[str | None] = mapped_column(String(32))
    timezone: Mapped[str | None] = mapped_column(String(64))
    label: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class OpportunityResource(Base):
    """Official forms, portals, links, and structured official contact resources."""

    __tablename__ = "opportunity_resources"
    __table_args__ = (
        UniqueConstraint("identity_key", name="uq_opportunity_resources_identity"),
        Index("ix_opportunity_resources_scope", "scholarship_id", "cycle_id", "resource_type"),
        Index("ix_opportunity_resources_contact_type", "contact_type"),
        CheckConstraint(
            "url IS NOT NULL OR email IS NOT NULL OR phone IS NOT NULL OR address IS NOT NULL",
            name="ck_opportunity_resources_locator_present",
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
        ForeignKey("application_tracks.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scholarship_programmes.id", ondelete="CASCADE"), index=True
    )
    identity_key: Mapped[str] = mapped_column(String(64), index=True)
    resource_key: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(255))
    resource_type: Mapped[str] = mapped_column(String(100), index=True)
    url: Mapped[str | None] = mapped_column(String(2048))
    contact_type: Mapped[str | None] = mapped_column(String(100))
    organization: Mapped[str | None] = mapped_column(String(255))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(Text)
    original_text: Mapped[str | None] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class CatalogueMaterializedClaimLink(Base):
    """Immutable bridge from a proposal claim to its row and canonical field evidence."""

    __tablename__ = "catalogue_materialized_claim_links"
    __table_args__ = (
        UniqueConstraint(
            "proposal_hash",
            "claim_id",
            "entity_id",
            "field_path",
            name="uq_catalogue_materialized_claim_link_identity",
        ),
        Index("ix_catalogue_materialized_claim_links_candidate", "candidate_id", "proposal_hash"),
        Index("ix_catalogue_materialized_claim_links_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidate_reviews.id", ondelete="CASCADE"), index=True
    )
    proposal_hash: Mapped[str] = mapped_column(String(64), index=True)
    claim_id: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    field_path: Mapped[str] = mapped_column(String(255))
    field_evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("field_evidence.id", ondelete="RESTRICT"), index=True
    )
    trust_domain: Mapped[str | None] = mapped_column(String(64), index=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


@event.listens_for(CatalogueMaterializedClaimLink, "before_update", propagate=True)
def _prevent_materialized_claim_link_update(*_: object) -> None:
    raise RuntimeError("catalogue materialized claim links are immutable")


@event.listens_for(CatalogueMaterializedClaimLink, "before_delete", propagate=True)
def _prevent_materialized_claim_link_delete(*_: object) -> None:
    raise RuntimeError("catalogue materialized claim links cannot be deleted")


__all__ = [
    "CatalogueMaterializedClaimLink",
    "OpportunityEvent",
    "OpportunityResource",
    "ScholarshipEligibilityRule",
    "ScholarshipProgramme",
]
