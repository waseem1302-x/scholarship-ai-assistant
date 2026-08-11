import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.modules.auth.models import (
    AdminStepUpToken,
    AuditLog,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
    UserRole,
)
from app.modules.auth.repository import AuthRepository


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    user: User


@dataclass(frozen=True)
class IssuedAccountToken:
    raw_token: str
    expires_at: datetime


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = AuthRepository(session)

    def register(self, email: str, password: str) -> IssuedTokens:
        if self.repository.get_user_by_email(email) is not None:
            raise ConflictError("email_already_registered", "An account already uses this email")

        user = User(
            id=uuid.uuid4(),
            email=email,
            password_hash=hash_password(password),
            role=UserRole.STUDENT,
            is_active=True,
        )
        self.repository.add_user(user)
        try:
            self.session.flush()
            result = self._issue_token_pair(user=user)
            self.session.commit()
            self.session.refresh(user)
            return result
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "email_already_registered", "An account already uses this email"
            ) from exc

    def login(self, email: str, password: str) -> IssuedTokens:
        user = self.repository.get_user_by_email(email)
        if user is None or not verify_password(password, user.password_hash) or not user.is_active:
            raise AuthenticationError("Invalid email or password")

        result = self._issue_token_pair(user=user)
        self.session.commit()
        return result

    def refresh(self, raw_token: str) -> IssuedTokens:
        token = self.repository.get_refresh_token(hash_refresh_token(raw_token))
        if token is None:
            raise AuthenticationError("Invalid refresh token")

        now = datetime.now(UTC)
        if token.revoked_at is not None:
            if token.replaced_by_token_id is not None:
                self.repository.revoke_family(token.family_id, now)
                self.session.commit()
            raise AuthenticationError("Invalid refresh token")

        if self._as_utc(token.expires_at) <= now:
            token.revoked_at = now
            self.session.commit()
            raise AuthenticationError("Refresh token has expired")

        user = token.user
        if not user.is_active:
            self.repository.revoke_family(token.family_id, now)
            self.session.commit()
            raise AuthenticationError("Invalid refresh token")

        replacement = self._new_refresh_token(user.id, token.family_id, now)
        self.repository.add_refresh_token(replacement[0])
        self.session.flush()
        token.revoked_at = now
        token.replaced_by_token_id = replacement[0].id
        access_token, expires_in = create_access_token(
            user_id=user.id, role=user.role.value, settings=self.settings, now=now
        )
        self.session.commit()
        return IssuedTokens(access_token, replacement[1], expires_in, user)

    def logout(self, raw_token: str) -> None:
        token = self.repository.get_refresh_token(hash_refresh_token(raw_token))
        if token is not None:
            self.repository.revoke_family(token.family_id)
            self.session.commit()

    def issue_email_verification(self, user: User) -> IssuedAccountToken:
        issued = self._new_account_token(
            EmailVerificationToken, user.id, self.settings.email_verification_ttl_minutes
        )
        self.repository.add(issued[0])
        self._audit(user.id, "email_verification_requested", "user", str(user.id))
        self.session.commit()
        return IssuedAccountToken(issued[1], issued[0].expires_at)

    def confirm_email_verification(self, raw_token: str) -> User:
        token = self.repository.get_email_verification_token(hash_refresh_token(raw_token))
        user = self._consume_account_token(token, "email_verification_confirmed")
        user.email_verified_at = datetime.now(UTC)
        self.session.commit()
        return user

    def request_password_reset(self, email: str) -> IssuedAccountToken | None:
        user = self.repository.get_user_by_email(email)
        if user is None or not user.is_active:
            return None
        issued = self._new_account_token(
            PasswordResetToken, user.id, self.settings.password_reset_ttl_minutes
        )
        self.repository.add(issued[0])
        self._audit(user.id, "password_reset_requested", "user", str(user.id))
        self.session.commit()
        return IssuedAccountToken(issued[1], issued[0].expires_at)

    def confirm_password_reset(self, raw_token: str, new_password: str) -> None:
        token = self.repository.get_password_reset_token(hash_refresh_token(raw_token))
        user = self._consume_account_token(token, "password_reset_completed")
        user.password_hash = hash_password(new_password)
        self.repository.revoke_family_for_user(user.id)
        self.session.commit()

    def step_up_admin(self, user: User, password: str) -> IssuedAccountToken:
        if user.role is not UserRole.ADMIN or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid administrator credentials")
        if self.settings.env == "production" and user.email_verified_at is None:
            raise AuthenticationError("Administrator email verification is required")
        issued = self._new_account_token(
            AdminStepUpToken, user.id, self.settings.admin_step_up_ttl_minutes
        )
        self.repository.add(issued[0])
        self._audit(user.id, "admin_step_up_completed", "user", str(user.id))
        self.session.commit()
        return IssuedAccountToken(issued[1], issued[0].expires_at)

    def _issue_token_pair(self, user: User) -> IssuedTokens:
        now = datetime.now(UTC)
        access_token, expires_in = create_access_token(
            user_id=user.id, role=user.role.value, settings=self.settings, now=now
        )
        refresh_record, raw_refresh_token = self._new_refresh_token(user.id, uuid.uuid4(), now)
        self.repository.add_refresh_token(refresh_record)
        return IssuedTokens(access_token, raw_refresh_token, expires_in, user)

    def _new_refresh_token(
        self, user_id: uuid.UUID, family_id: uuid.UUID, now: datetime
    ) -> tuple[RefreshToken, str]:
        raw_token = generate_refresh_token()
        record = RefreshToken(
            id=uuid.uuid4(),
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=now + timedelta(days=self.settings.refresh_token_ttl_days),
        )
        return record, raw_token

    def _new_account_token(self, token_type, user_id: uuid.UUID, ttl_minutes: int):
        now = datetime.now(UTC)
        raw_token = generate_refresh_token()
        record = token_type(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=now + timedelta(minutes=ttl_minutes),
        )
        return record, raw_token

    def _consume_account_token(self, token, action: str) -> User:
        now = datetime.now(UTC)
        if token is None or token.consumed_at is not None or self._as_utc(token.expires_at) <= now:
            raise AuthenticationError("Invalid or expired token")
        if not token.user.is_active:
            raise AuthenticationError("Invalid or expired token")
        token.consumed_at = now
        self._audit(token.user_id, action, "user", str(token.user_id))
        return token.user

    def _audit(
        self, actor_user_id: uuid.UUID | None, action: str, entity_type: str, entity_id: str
    ) -> None:
        self.repository.add(
            AuditLog(
                actor_user_id=actor_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
