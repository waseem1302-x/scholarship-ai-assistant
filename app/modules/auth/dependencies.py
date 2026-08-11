from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, AuthenticationError
from app.core.security import decode_access_token, hash_refresh_token
from app.db.session import get_db
from app.modules.auth.models import User, UserRole
from app.modules.auth.repository import AuthRepository

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()
    claims = decode_access_token(credentials.credentials, settings)
    user = AuthRepository(session).get_user(claims.user_id)
    if user is None or not user.is_active or user.role.value != claims.role:
        raise AuthenticationError()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[CurrentUser], User]:
    def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise AppError(
                "forbidden",
                "You do not have permission to perform this action",
                status.HTTP_403_FORBIDDEN,
            )
        return user

    return dependency


def require_admin_step_up(
    user: CurrentUser,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    step_up_token: Annotated[str | None, Header(alias="X-Admin-Step-Up")] = None,
) -> User:
    if user.role is not UserRole.ADMIN:
        raise AppError(
            "forbidden",
            "You do not have permission to perform this action",
            status.HTTP_403_FORBIDDEN,
        )
    if settings.env != "production":
        return user
    if user.email_verified_at is None:
        raise AppError(
            "admin_email_verification_required",
            "Administrator email verification is required",
            status.HTTP_403_FORBIDDEN,
        )
    if not step_up_token:
        raise AppError(
            "admin_step_up_required",
            "Re-authenticate as an administrator before this action",
            status.HTTP_403_FORBIDDEN,
        )
    token = AuthRepository(session).get_admin_step_up_token(hash_refresh_token(step_up_token))
    now = datetime.now(UTC)
    if (
        token is None
        or token.user_id != user.id
        or token.consumed_at is not None
        or token.expires_at <= now
    ):
        raise AppError(
            "admin_step_up_required",
            "Administrator step-up token is invalid or expired",
            status.HTTP_403_FORBIDDEN,
        )
    token.consumed_at = now
    session.commit()
    return user
