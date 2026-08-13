import uuid
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.auth.models import User, enum_values, utc_now
from app.modules.opportunities.models import Opportunity


class CommunityTopic(StrEnum):
    APPLICATION_PROCESS = "application_process"
    DOCUMENTS = "documents"
    INTERVIEW = "interview"
    OFFICIAL_SOURCE_UPDATE = "official_source_update"
    TIMELINE = "timeline"
    QUESTION = "question"
    GENERAL = "general"


class CommunityContentStatus(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"
    DELETED = "deleted"


class CommunityReportReason(StrEnum):
    HARASSMENT = "harassment"
    HATE_OR_DISCRIMINATION = "hate_or_discrimination"
    MISLEADING = "misleading"
    OFF_TOPIC = "off_topic"
    PRIVACY = "privacy"
    SOLICITATION = "solicitation"
    OTHER = "other"


class CommunityReportStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class CommunityModerationAction(StrEnum):
    HIDE = "hide"
    RESTORE = "restore"
    RESOLVE_REPORT = "resolve_report"
    SUSPEND = "suspend"
    REINSTATE = "reinstate"


class CommunityPreference(Base):
    __tablename__ = "community_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    consented_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    user: Mapped[User] = relationship()


class CommunityPost(Base):
    __tablename__ = "community_posts"
    __table_args__ = (
        Index("ix_community_posts_status_created", "status", "created_at"),
        Index("ix_community_posts_opportunity_status", "opportunity_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), index=True
    )
    topic: Mapped[CommunityTopic] = mapped_column(
        Enum(
            CommunityTopic,
            name="community_topic",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        )
    )
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[CommunityContentStatus] = mapped_column(
        Enum(
            CommunityContentStatus,
            name="community_content_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=CommunityContentStatus.VISIBLE,
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    author: Mapped[User] = relationship()
    opportunity: Mapped[Opportunity | None] = relationship()
    replies: Mapped[list["CommunityReply"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )


class CommunityReply(Base):
    __tablename__ = "community_replies"
    __table_args__ = (
        Index(
            "ix_community_replies_post_status_created",
            "post_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("community_posts.id", ondelete="CASCADE"), index=True
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[CommunityContentStatus] = mapped_column(
        Enum(
            CommunityContentStatus,
            name="community_content_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=False,
            values_callable=enum_values,
        ),
        default=CommunityContentStatus.VISIBLE,
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    post: Mapped[CommunityPost] = relationship(back_populates="replies")
    author: Mapped[User] = relationship()


class CommunityBookmark(Base):
    __tablename__ = "community_bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_community_bookmarks_user_post"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("community_posts.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class CommunityBlock(Base):
    __tablename__ = "community_blocks"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "blocked_user_id",
            name="uq_community_blocks_user_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    blocked_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class CommunityReport(Base):
    __tablename__ = "community_reports"
    __table_args__ = (
        UniqueConstraint(
            "reporter_user_id",
            "post_id",
            "reply_id",
            name="uq_community_reports_reporter_target",
        ),
        Index("ix_community_reports_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reporter_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("community_posts.id", ondelete="CASCADE"), index=True
    )
    reply_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("community_replies.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[CommunityReportReason] = mapped_column(
        Enum(
            CommunityReportReason,
            name="community_report_reason",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        )
    )
    detail: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[CommunityReportStatus] = mapped_column(
        Enum(
            CommunityReportStatus,
            name="community_report_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=CommunityReportStatus.OPEN,
    )
    resolved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class CommunityModerationRecord(Base):
    __tablename__ = "community_moderation_records"
    __table_args__ = (
        Index(
            "ix_community_moderation_records_target_created",
            "target_type",
            "target_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    moderator_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[CommunityModerationAction] = mapped_column(
        Enum(
            CommunityModerationAction,
            name="community_moderation_action",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        )
    )
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
