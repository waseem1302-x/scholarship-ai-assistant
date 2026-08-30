"""Durable review and materialization state for catalogue ingestion proposals."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import enum_values, utc_now


class CatalogueProposalState(StrEnum):
    """Human review/materialization state, deliberately separate from ingestion and publication state."""

    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"
    MATERIALIZING = "materializing"
    MATERIALIZED = "materialized"
    PUBLICATION_READY = "publication_ready"
    PUBLISHED = "published"


class CatalogueCandidateReview(Base):
    """One durable optimistic-lock record for the current proposal attached to a candidate."""

    __tablename__ = "catalogue_candidate_reviews"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_catalogue_candidate_reviews_candidate"),
        CheckConstraint("review_revision >= 1", name="ck_catalogue_candidate_reviews_revision_positive"),
        CheckConstraint(
            "materialization_attempt_count >= 0",
            name="ck_catalogue_candidate_reviews_materialization_attempt_non_negative",
        ),
        Index("ix_catalogue_candidate_reviews_state_updated", "state", "updated_at"),
        Index("ix_catalogue_candidate_reviews_proposal_hash", "proposal_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[CatalogueProposalState] = mapped_column(
        Enum(
            CatalogueProposalState,
            name="catalogue_proposal_state",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=CatalogueProposalState.DRAFT,
        server_default=CatalogueProposalState.DRAFT.value,
        nullable=False,
        index=True,
    )
    proposal_schema_version: Mapped[str | None] = mapped_column(String(100))
    proposal_hash: Mapped[str | None] = mapped_column(String(64))
    approved_proposal_hash: Mapped[str | None] = mapped_column(String(64))
    review_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(Text)
    materialization_revision: Mapped[str | None] = mapped_column(String(100), index=True)
    materialization_attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    materialization_failure_code: Mapped[str | None] = mapped_column(String(100))
    materialization_failure_reason: Mapped[str | None] = mapped_column(Text)
    materialized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publication_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )


__all__ = ["CatalogueCandidateReview", "CatalogueProposalState"]
