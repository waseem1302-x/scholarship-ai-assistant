from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, AuthenticationError
from app.core.security import decode_access_token
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
