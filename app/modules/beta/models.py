import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.auth.models import enum_values


class BetaInvitationStatus(StrEnum):
    PENDING = "pending"
    REDEEMED = "redeemed"
    REVOKED = "revoked"
    EXPIRED = "expired"


class BetaInvitation(Base):
    __tablename__ = "beta_invitations"
    __table_args__ = (Index("ix_beta_invitations_email_status", "email", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[BetaInvitationStatus] = mapped_column(
        Enum(
            BetaInvitationStatus,
            name="beta_invitation_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=BetaInvitationStatus.PENDING,
    )
    max_redemptions: Mapped[int] = mapped_column(default=1)
    redemption_count: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    redeemed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    reserved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    creator = relationship("User", foreign_keys=[created_by_user_id])
    redeemed_by = relationship("User", foreign_keys=[redeemed_by_user_id])
    reserved_by = relationship("User", foreign_keys=[reserved_by_user_id])


class BetaLegalAcceptance(Base):
    __tablename__ = "beta_legal_acceptances"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "terms_version",
            "privacy_notice_version",
            name="uq_beta_legal_acceptance_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    terms_version: Mapped[str] = mapped_column(String(100))
    privacy_notice_version: Mapped[str] = mapped_column(String(100))
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )

    user = relationship("User")
