import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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


class ApplicationLifecycle(StrEnum):
    SAVED = "saved"
    PREPARING = "preparing"
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTED = "submitted"
    DECISION_RECEIVED = "decision_received"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


class TaskCategory(StrEnum):
    DOCUMENT = "document"
    TEST = "test"
    RECOMMENDATION = "recommendation"
    FUNDING = "funding"
    OFFICIAL_VERIFICATION = "official_verification"
    PERSONAL = "personal"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ReminderStatus(StrEnum):
    SCHEDULED = "scheduled"
    DELIVERED = "delivered"
    READ = "read"
    SNOOZED = "snoozed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class DeadlineState(StrEnum):
    KNOWN = "known"
    CHANGED = "changed"
    UNCERTAIN = "uncertain"


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


class Application(Base):
    """Private, normalized application workspace. Events are append-only."""

    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_applications_user_opportunity"),
        UniqueConstraint("saved_opportunity_id", name="uq_applications_saved_opportunity"),
        Index("ix_applications_user_lifecycle", "user_id", "lifecycle"),
        Index("ix_applications_official_deadline", "official_deadline"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    saved_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("saved_opportunities.id", ondelete="SET NULL"), nullable=True
    )
    lifecycle: Mapped[ApplicationLifecycle] = mapped_column(
        Enum(
            ApplicationLifecycle,
            name="application_lifecycle",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=ApplicationLifecycle.SAVED,
    )
    official_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    official_deadline_timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    official_deadline_state: Mapped[DeadlineState] = mapped_column(
        Enum(
            DeadlineState,
            name="application_deadline_state",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=DeadlineState.UNCERTAIN,
    )
    official_deadline_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    official_deadline_excerpt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_excerpts.id", ondelete="SET NULL")
    )
    official_deadline_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    personal_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    personal_deadline_timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    notes: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    user: Mapped[User] = relationship()
    opportunity: Mapped[Opportunity] = relationship()
    tasks: Mapped[list["ApplicationTask"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    reminders: Mapped[list["ApplicationReminder"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    documents: Mapped[list["ApplicationDocument"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class ApplicationTask(Base):
    __tablename__ = "application_tasks"
    __table_args__ = (
        UniqueConstraint(
            "application_id",
            "category",
            "title",
            name="uq_application_tasks_application_category_title",
        ),
        Index("ix_application_tasks_application_status_due", "application_id", "status", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[TaskCategory] = mapped_column(
        Enum(
            TaskCategory,
            name="application_task_category",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        )
    )
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="application_task_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=TaskStatus.TODO,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(
            TaskPriority,
            name="application_task_priority",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=TaskPriority.NORMAL,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    source_excerpt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_excerpts.id", ondelete="SET NULL")
    )
    is_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    completion_evidence: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    application: Mapped[Application] = relationship(back_populates="tasks")


class ApplicationReminder(Base):
    __tablename__ = "application_reminders"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_application_reminders_idempotency"),
        Index("ix_application_reminders_status_scheduled", "status", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_tasks.id", ondelete="CASCADE")
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    message: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(
            ReminderStatus,
            name="application_reminder_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=ReminderStatus.SCHEDULED,
    )
    idempotency_key: Mapped[str] = mapped_column(String(100))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    application: Mapped[Application] = relationship(back_populates="reminders")


class ApplicationNotificationPreference(Base):
    __tablename__ = "application_notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    user: Mapped[User] = relationship()


class ReminderWorkerHealth(Base):
    __tablename__ = "reminder_worker_health"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default="default")
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    __table_args__ = (
        Index("ix_application_events_application_created", "application_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(100))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class ApplicationDocument(Base):
    __tablename__ = "application_documents"
    __table_args__ = (Index("ix_application_documents_application", "application_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_tasks.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255))
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    file_name: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    version_label: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    application: Mapped[Application] = relationship(back_populates="documents")
