"""Structured scholarship information that does not fit legacy catalogue projections."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import utc_now


def _scope_constraints(table_name: str) -> tuple[CheckConstraint, ...]:
    return (
        CheckConstraint(
            "track_id IS NULL OR cycle_id IS NOT NULL",
            name=f"ck_{table_name}_track_requires_cycle",
        ),
        CheckConstraint(
            "programme_id IS NULL OR cycle_id IS NOT NULL",
            name=f"ck_{table_name}_programme_requires_cycle",
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


class _ScopedInformationMixin:
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
    original_text: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class ScholarshipAwardQuota(_ScopedInformationMixin, Base):
    __tablename__ = "scholarship_award_quotas"
    __table_args__ = (
        *_scope_constraints("scholarship_award_quotas"),
        UniqueConstraint("identity_key", name="uq_scholarship_award_quotas_identity"),
        _scope_index("scholarship_award_quotas"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quota_key: Mapped[str] = mapped_column(String(120), index=True)
    quota_type: Mapped[str] = mapped_column(String(100), index=True)
    count_value: Mapped[int | None] = mapped_column(Integer)
    count_text: Mapped[str | None] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(64))
    condition: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class ScholarshipObligation(_ScopedInformationMixin, Base):
    __tablename__ = "scholarship_obligations"
    __table_args__ = (
        *_scope_constraints("scholarship_obligations"),
        UniqueConstraint("identity_key", name="uq_scholarship_obligations_identity"),
        _scope_index("scholarship_obligations"),
        Index("ix_scholarship_obligations_critical", "scholarship_id", "critical"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    obligation_key: Mapped[str] = mapped_column(String(120), index=True)
    obligation_type: Mapped[str] = mapped_column(String(100), index=True)
    required: Mapped[bool | None] = mapped_column(Boolean)
    duration_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    duration_unit: Mapped[str | None] = mapped_column(String(64))
    condition: Mapped[str | None] = mapped_column(Text)
    consequence: Mapped[str | None] = mapped_column(Text)
    critical: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text)


class OpportunityContact(_ScopedInformationMixin, Base):
    __tablename__ = "opportunity_contacts"
    __table_args__ = (
        *_scope_constraints("opportunity_contacts"),
        UniqueConstraint("identity_key", name="uq_opportunity_contacts_identity"),
        _scope_index("opportunity_contacts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    contact_key: Mapped[str] = mapped_column(String(120), index=True)
    contact_type: Mapped[str] = mapped_column(String(100), index=True)
    organization: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column(String(2048))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class ScholarshipFee(_ScopedInformationMixin, Base):
    __tablename__ = "scholarship_fees"
    __table_args__ = (
        *_scope_constraints("scholarship_fees"),
        UniqueConstraint("identity_key", name="uq_scholarship_fees_identity"),
        _scope_index("scholarship_fees"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fee_key: Mapped[str] = mapped_column(String(120), index=True)
    fee_type: Mapped[str] = mapped_column(String(100), index=True)
    required: Mapped[bool | None] = mapped_column(Boolean)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    amount_text: Mapped[str | None] = mapped_column(String(255))
    waiver_available: Mapped[bool | None] = mapped_column(Boolean)
    waiver_condition: Mapped[str | None] = mapped_column(Text)
    refundable: Mapped[bool | None] = mapped_column(Boolean)
    payment_stage: Mapped[str | None] = mapped_column(String(100), index=True)
    notes: Mapped[str | None] = mapped_column(Text)


class ScholarshipContinuationRule(_ScopedInformationMixin, Base):
    __tablename__ = "scholarship_continuation_rules"
    __table_args__ = (
        *_scope_constraints("scholarship_continuation_rules"),
        UniqueConstraint("identity_key", name="uq_scholarship_continuation_rules_identity"),
        _scope_index("scholarship_continuation_rules"),
        Index("ix_scholarship_continuation_rules_critical", "scholarship_id", "critical"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule_key: Mapped[str] = mapped_column(String(120), index=True)
    rule_type: Mapped[str] = mapped_column(String(100), index=True)
    operator: Mapped[str | None] = mapped_column(String(32))
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(64))
    frequency: Mapped[str | None] = mapped_column(String(64))
    condition: Mapped[str | None] = mapped_column(Text)
    consequence: Mapped[str | None] = mapped_column(Text)
    critical: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text)


class ScholarshipAwardTerm(_ScopedInformationMixin, Base):
    __tablename__ = "scholarship_award_terms"
    __table_args__ = (
        *_scope_constraints("scholarship_award_terms"),
        UniqueConstraint("identity_key", name="uq_scholarship_award_terms_identity"),
        _scope_index("scholarship_award_terms"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    term_key: Mapped[str] = mapped_column(String(120), index=True)
    term_type: Mapped[str] = mapped_column(String(100), index=True)
    duration_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    duration_unit: Mapped[str | None] = mapped_column(String(64))
    duration_text: Mapped[str | None] = mapped_column(String(255))
    condition: Mapped[str | None] = mapped_column(Text)
    renewal_required: Mapped[bool | None] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)


__all__ = [
    "OpportunityContact",
    "ScholarshipAwardQuota",
    "ScholarshipAwardTerm",
    "ScholarshipContinuationRule",
    "ScholarshipFee",
    "ScholarshipObligation",
]
