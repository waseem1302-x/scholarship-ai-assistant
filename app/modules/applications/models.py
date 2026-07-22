import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.auth.models import User, enum_values, utc_now
from app.modules.opportunities.models import Opportunity


class ApplicationStatus(StrEnum):
    INTERESTED = "interested"
    RESEARCHING = "researching"
    PREPARING_DOCUMENTS = "preparing_documents"
    WAITING_FOR_RECOMMENDATION = "waiting_for_recommendation"
    READY_TO_APPLY = "ready_to_apply"
    SUBMITTED = "submitted"
    INTERVIEW_STAGE = "interview_stage"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class SavedOpportunity(Base):
    __tablename__ = "saved_opportunities"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "opportunity_id", name="uq_saved_opportunities_user_opportunity"
        ),
        Index("ix_saved_opportunities_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(
            ApplicationStatus,
            name="application_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=ApplicationStatus.INTERESTED,
        index=True,
    )
    personal_notes: Mapped[str | None] = mapped_column(Text)
    personal_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    document_checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    recommendation_letters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    test_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    user: Mapped[User] = relationship()
    opportunity: Mapped[Opportunity] = relationship()
