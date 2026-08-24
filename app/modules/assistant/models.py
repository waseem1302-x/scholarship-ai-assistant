import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.auth.models import User, enum_values, utc_now


class AssistantMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AssistantAnswerStatus(StrEnum):
    COMPLETED = "completed"
    ABSTAINED = "abstained"
    BLOCKED = "blocked"
    FAILED = "failed"


class AssistantQuotaWindow(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"


class AssistantQuotaReservationStatus(StrEnum):
    RESERVED = "reserved"
    CONSUMED = "consumed"
    REFUNDED = "refunded"


class AssistantFeedbackType(StrEnum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    INCORRECT = "incorrect"
    OUTDATED = "outdated"
    MISSING_CITATION = "missing_citation"


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"
    __table_args__ = (Index("ix_assistant_conversations_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(255))
    history_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    user: Mapped[User] = relationship()
    messages: Mapped[list["AssistantMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    answers: Mapped[list["AssistantAnswer"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        Index(
            "ix_assistant_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[AssistantMessageRole] = mapped_column(
        Enum(
            AssistantMessageRole,
            name="assistant_message_role",
            native_enum=False,
            values_callable=enum_values,
        )
    )
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    conversation: Mapped[AssistantConversation] = relationship(back_populates="messages")


class AssistantEvidencePacket(Base):
    __tablename__ = "assistant_evidence_packets"
    __table_args__ = (
        Index(
            "ix_assistant_evidence_packets_user_created",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    query_interpretation: Mapped[dict] = mapped_column(JSON, default=dict)
    scholarship_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_snapshots: Mapped[list[dict]] = mapped_column(JSON, default=list)
    freshness_status: Mapped[dict] = mapped_column(JSON, default=dict)
    conflicts: Mapped[list[str]] = mapped_column(JSON, default=list)
    retrieval_version: Mapped[str] = mapped_column(String(100))
    rule_version: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    user: Mapped[User] = relationship()


class AssistantAnswer(Base):
    __tablename__ = "assistant_answers"
    __table_args__ = (
        Index("ix_assistant_answers_user_created", "user_id", "created_at"),
        Index("ix_assistant_answers_conversation", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        index=True,
    )
    evidence_packet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_evidence_packets.id", ondelete="RESTRICT")
    )
    status: Mapped[AssistantAnswerStatus] = mapped_column(
        Enum(
            AssistantAnswerStatus,
            name="assistant_answer_status",
            native_enum=False,
            values_callable=enum_values,
        ),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(255))
    prompt_template_version: Mapped[str] = mapped_column(String(100))
    retrieval_version: Mapped[str] = mapped_column(String(100))
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    saved_to_workspace: Mapped[bool] = mapped_column(Boolean, default=False)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    user: Mapped[User] = relationship()
    conversation: Mapped[AssistantConversation] = relationship(back_populates="answers")
    evidence_packet: Mapped[AssistantEvidencePacket] = relationship()
    citations: Mapped[list["AssistantCitation"]] = relationship(
        back_populates="answer", cascade="all, delete-orphan"
    )


class AssistantQuotaCounter(Base):
    """One atomic capacity counter per user and UTC quota window."""

    __tablename__ = "assistant_quota_counters"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    window: Mapped[AssistantQuotaWindow] = mapped_column(
        Enum(
            AssistantQuotaWindow,
            name="assistant_quota_window",
            native_enum=False,
            values_callable=enum_values,
        ),
        primary_key=True,
    )
    window_start: Mapped[date] = mapped_column(Date, primary_key=True)
    used_slots: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    user: Mapped[User] = relationship()


class AssistantQuotaReservation(Base):
    """Durable quota admission record, retained even if later answer work fails."""

    __tablename__ = "assistant_quota_reservations"
    __table_args__ = (
        Index("ix_assistant_quota_reservations_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    daily_window_start: Mapped[date] = mapped_column(Date)
    monthly_window_start: Mapped[date] = mapped_column(Date)
    status: Mapped[AssistantQuotaReservationStatus] = mapped_column(
        Enum(
            AssistantQuotaReservationStatus,
            name="assistant_quota_reservation_status",
            native_enum=False,
            values_callable=enum_values,
        ),
        default=AssistantQuotaReservationStatus.RESERVED,
        index=True,
    )
    answer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assistant_answers.id", ondelete="SET NULL"), unique=True
    )
    terminal_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
    answer: Mapped["AssistantAnswer | None"] = relationship()


class AssistantCitation(Base):
    __tablename__ = "assistant_citations"
    __table_args__ = (Index("ix_assistant_citations_answer", "answer_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    answer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_answers.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"))
    source_excerpt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_excerpts.id", ondelete="SET NULL")
    )
    claim: Mapped[str] = mapped_column(String(500))
    claim_key: Mapped[str] = mapped_column(String(100), default="source_record")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    answer: Mapped[AssistantAnswer] = relationship(back_populates="citations")


class AssistantFeedback(Base):
    __tablename__ = "assistant_feedback"
    __table_args__ = (Index("ix_assistant_feedback_answer_user", "answer_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    answer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_answers.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    feedback_type: Mapped[AssistantFeedbackType] = mapped_column(
        Enum(
            AssistantFeedbackType,
            name="assistant_feedback_type",
            native_enum=False,
            values_callable=enum_values,
        )
    )
    comment: Mapped[str | None] = mapped_column(String(1000))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class AssistantPrivacyPreference(Base):
    """A user-owned consent and retention preference; no profile data is copied here."""

    __tablename__ = "assistant_privacy_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    history_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    user: Mapped[User] = relationship()


class AssistantEvaluationRun(Base):
    __tablename__ = "assistant_evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(255))
    retrieval_version: Mapped[str] = mapped_column(String(100))
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
