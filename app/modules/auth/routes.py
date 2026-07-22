from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.modules.auth.service import AuthService, IssuedTokens

router = APIRouter(prefix="/auth", tags=["authentication"])

VALIDATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "The request body failed validation.",
}
AUTHENTICATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "Credentials or tokens are missing, invalid, expired, or revoked.",
}
CONFLICT_RESPONSE = {
    "model": ErrorResponse,
    "description": "The normalized email address is already registered.",
}


def get_auth_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(session, settings)


def to_token_response(result: IssuedTokens) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=result.expires_in,
        user=UserResponse.model_validate(result.user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: CONFLICT_RESPONSE, 422: VALIDATION_RESPONSE},
)
def register(payload: RegisterRequest, service: Annotated[AuthService, Depends(get_auth_service)]):
    return to_token_response(service.register(str(payload.email), payload.password))


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={401: AUTHENTICATION_RESPONSE, 422: VALIDATION_RESPONSE},
)
def login(payload: LoginRequest, service: Annotated[AuthService, Depends(get_auth_service)]):
    return to_token_response(service.login(str(payload.email), payload.password))


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={401: AUTHENTICATION_RESPONSE, 422: VALIDATION_RESPONSE},
)
def refresh(payload: RefreshRequest, service: Annotated[AuthService, Depends(get_auth_service)]):
    return to_token_response(service.refresh(payload.refresh_token))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={422: VALIDATION_RESPONSE},
)
def logout(
    payload: LogoutRequest, service: Annotated[AuthService, Depends(get_auth_service)]
) -> Response:
    service.logout(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: AUTHENTICATION_RESPONSE},
)
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
