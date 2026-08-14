import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    event,
    func,
    select,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.db.base import Base


class UserRole(StrEnum):
    STUDENT = "student"
    ADMIN = "admin"


class WebAuthnChallengePurpose(StrEnum):
    REGISTRATION = "registration"
    STEP_UP = "step_up"


ADMIN_STEP_UP_SCOPE = "admin_sensitive_operations"
# One transaction-scoped PostgreSQL advisory lock serializes audit-chain appends
# across API replicas/workers without introducing a mutable coordination row.
AUDIT_CHAIN_ADVISORY_LOCK_ID = 1_904_281_117


def enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(trim(email))", name="ck_users_email_normalized"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=UserRole.STUDENT,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(server_default="0")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_family_id", "family_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_token_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    user: Mapped[User] = relationship()


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    user: Mapped[User] = relationship()


class AdminStepUpToken(Base):
    __tablename__ = "admin_step_up_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(64), server_default=ADMIN_STEP_UP_SCOPE)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    user: Mapped[User] = relationship()


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[str] = mapped_column(String(1024), unique=True)
    display_name: Mapped[str] = mapped_column(String(100), server_default="New passkey")
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class WebAuthnChallenge(Base):
    __tablename__ = "webauthn_challenges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[WebAuthnChallengePurpose] = mapped_column(
        Enum(
            WebAuthnChallengePurpose,
            name="webauthn_challenge_purpose",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        )
    )
    challenge: Mapped[str] = mapped_column(String(512), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    user: Mapped[User] = relationship()


class AuditLog(Base):
    """Append-only security history.

    ``actor_user_id`` is intentionally an immutable UUID snapshot rather than a
    foreign key. Deleting an account must never rewrite old security history.
    PostgreSQL additionally blocks UPDATE/DELETE at the database layer.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    previous_integrity_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    integrity_hash: Mapped[str] = mapped_column(String(64), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


def audit_integrity_hash(
    *,
    previous_hash: str | None,
    audit_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    metadata_json: dict[str, object],
    created_at: datetime,
) -> str:
    payload = {
        "previous_hash": previous_hash,
        "id": str(audit_id),
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "metadata_json": metadata_json,
        "created_at": created_at.isoformat(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def verify_audit_integrity_chain(session: Session) -> tuple[bool, uuid.UUID | None]:
    """Recalculate the complete ordered chain and return the first bad row."""

    previous_hash: str | None = None
    rows = session.scalars(
        select(AuditLog).order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    ).all()
    for row in rows:
        expected = audit_integrity_hash(
            previous_hash=previous_hash,
            audit_id=row.id,
            actor_user_id=row.actor_user_id,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            metadata_json=row.metadata_json or {},
            created_at=row.created_at,
        )
        if row.previous_integrity_hash != previous_hash or row.integrity_hash != expected:
            return False, row.id
        previous_hash = row.integrity_hash
    return True, None


@event.listens_for(AuditLog, "before_insert")
def set_audit_integrity_hash(_mapper, connection: Connection, target: AuditLog) -> None:
    # Concurrent Container Apps replicas must not create two children of the
    # same previous hash. The xact lock releases automatically on commit/rollback.
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql(
            "SELECT pg_advisory_xact_lock(%s)",
            (AUDIT_CHAIN_ADVISORY_LOCK_ID,),
        )
    if target.id is None:
        target.id = uuid.uuid4()
    if target.created_at is None:
        target.created_at = utc_now()
    previous_hash = connection.execute(
        select(AuditLog.integrity_hash)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    target.previous_integrity_hash = previous_hash
    target.integrity_hash = audit_integrity_hash(
        previous_hash=previous_hash,
        audit_id=target.id,
        actor_user_id=target.actor_user_id,
        action=target.action,
        entity_type=target.entity_type,
        entity_id=target.entity_id,
        metadata_json=target.metadata_json or {},
        created_at=target.created_at,
    )


@event.listens_for(AuditLog, "before_update")
@event.listens_for(AuditLog, "before_delete")
def reject_audit_log_mutation(_mapper, _connection: Connection, _target: AuditLog) -> None:
    raise RuntimeError("Audit logs are append-only")
