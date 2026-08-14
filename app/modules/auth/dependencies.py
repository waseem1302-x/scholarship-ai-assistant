from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, AuthenticationError
from app.core.security import decode_access_token, hash_refresh_token
from app.db.session import bind_tenant_context, get_db
from app.modules.auth.models import ADMIN_STEP_UP_SCOPE, User, UserRole
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
    if (
        user is None
        or not user.is_active
        or user.role.value != claims.role
        or user.token_version != claims.token_version
    ):
        raise AuthenticationError()
    bind_tenant_context(session, user.id)
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


def require_verified_student(
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Gate production personal-content creation on completed email verification."""
    if user.role is not UserRole.STUDENT:
        raise AppError(
            "forbidden",
            "Only student users can perform this action",
            status.HTTP_403_FORBIDDEN,
        )
    if settings.env == "production" and user.email_verified_at is None:
        raise AppError(
            "email_verification_required",
            "Verify your email before creating or changing private student content.",
            status.HTTP_403_FORBIDDEN,
        )
    return user


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
        or token.scope != ADMIN_STEP_UP_SCOPE
        or token.consumed_at is not None
        or _as_utc(token.expires_at) <= now
    ):
        raise AppError(
            "admin_step_up_required",
            "Administrator step-up token is invalid or expired",
            status.HTTP_403_FORBIDDEN,
        )
    # This is a short-lived, scoped step-up session. Dependencies run before
    # request-body and service validation, so consuming it here would burn MFA
    # on a failed protected action.
    return user


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
