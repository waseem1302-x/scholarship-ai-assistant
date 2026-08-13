import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.modules.auth.models import (
    AdminStepUpToken,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
    WebAuthnChallenge,
)


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email))

    def get_user(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def add_user(self, user: User) -> None:
        self.session.add(user)

    def add_refresh_token(self, token: RefreshToken) -> None:
        self.session.add(token)

    def add(self, model: object) -> None:
        self.session.add(model)

    def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        return self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )

    def claim_refresh_token_rotation(self, token_id: uuid.UUID, now: datetime) -> bool:
        """Atomically claim one active refresh token for rotation."""
        result = self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.id == token_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .values(revoked_at=now)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def get_email_verification_token(self, token_hash: str) -> EmailVerificationToken | None:
        return self.session.scalar(
            select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
        )

    def get_password_reset_token(self, token_hash: str) -> PasswordResetToken | None:
        return self.session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )

    def get_admin_step_up_token(self, token_hash: str) -> AdminStepUpToken | None:
        return self.session.scalar(
            select(AdminStepUpToken).where(AdminStepUpToken.token_hash == token_hash)
        )

    def revoke_family(self, family_id: uuid.UUID, revoked_at: datetime | None = None) -> None:
        timestamp = revoked_at or datetime.now(UTC)
        self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=timestamp)
        )

    def revoke_family_for_user(
        self, user_id: uuid.UUID, revoked_at: datetime | None = None
    ) -> None:
        timestamp = revoked_at or datetime.now(UTC)
        self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=timestamp)
        )

    def invalidate_unconsumed_account_tokens(
        self,
        token_type: type[EmailVerificationToken] | type[PasswordResetToken],
        user_id: uuid.UUID,
    ) -> None:
        self.session.execute(
            update(token_type)
            .where(token_type.user_id == user_id, token_type.consumed_at.is_(None))
            .values(consumed_at=datetime.now(UTC))
        )

    def purge_expired_tokens(self, before: datetime) -> int:
        """Delete non-actionable auth artifacts after the documented retention window."""
        total = 0
        for token_type in (EmailVerificationToken, PasswordResetToken, AdminStepUpToken):
            result = self.session.execute(
                delete(token_type).where(
                    or_(token_type.consumed_at <= before, token_type.expires_at <= before),
                )
            )
            total += result.rowcount or 0
        challenge_result = self.session.execute(
            delete(WebAuthnChallenge).where(
                or_(
                    WebAuthnChallenge.consumed_at <= before,
                    WebAuthnChallenge.expires_at <= before,
                ),
            )
        )
        total += challenge_result.rowcount or 0
        refresh_result = self.session.execute(
            delete(RefreshToken).where(
                or_(RefreshToken.revoked_at <= before, RefreshToken.expires_at <= before),
            )
        )
        return total + (refresh_result.rowcount or 0)
