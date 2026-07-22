import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.auth.models import RefreshToken, User


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

    def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        return self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )

    def revoke_family(self, family_id: uuid.UUID, revoked_at: datetime | None = None) -> None:
        timestamp = revoked_at or datetime.now(UTC)
        self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=timestamp)
        )
