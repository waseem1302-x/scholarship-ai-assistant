import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.schemas import (
    AccountTokenDeliveryResponse,
    AdminStepUpRequest,
    AdminStepUpResponse,
    LoginRequest,
    LogoutRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenConfirmRequest,
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


def to_token_response(result: IssuedTokens, *, include_refresh_token: bool = True) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token if include_refresh_token else None,
        expires_in=result.expires_in,
        user=UserResponse.model_validate(result.user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: CONFLICT_RESPONSE, 422: VALIDATION_RESPONSE},
)
def register(
    payload: RegisterRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    result = service.register(str(payload.email), payload.password)
    _set_refresh_cookies(response, result.refresh_token, settings)
    return to_token_response(result, include_refresh_token=settings.env != "production")


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={401: AUTHENTICATION_RESPONSE, 422: VALIDATION_RESPONSE},
)
def login(
    payload: LoginRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    result = service.login(str(payload.email), payload.password)
    _set_refresh_cookies(response, result.refresh_token, settings)
    return to_token_response(result, include_refresh_token=settings.env != "production")


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={401: AUTHENTICATION_RESPONSE, 422: VALIDATION_RESPONSE},
)
def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    raw_token = _request_refresh_token(payload, request, settings)
    result = service.refresh(raw_token)
    _set_refresh_cookies(response, result.refresh_token, settings)
    return to_token_response(result, include_refresh_token=settings.env != "production")


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={422: VALIDATION_RESPONSE},
)
def logout(
    payload: LogoutRequest,
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    service.logout(_request_refresh_token(payload, request, settings))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    response.delete_cookie("csrf_token", path="/")
    return response


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: AUTHENTICATION_RESPONSE},
)
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post(
    "/email-verifications",
    response_model=AccountTokenDeliveryResponse,
    responses={401: AUTHENTICATION_RESPONSE},
)
def request_email_verification(
    user: CurrentUser,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccountTokenDeliveryResponse:
    issued = service.issue_email_verification(user)
    return AccountTokenDeliveryResponse(
        expires_at=issued.expires_at,
        debug_token=issued.raw_token if settings.env != "production" else None,
    )


@router.post("/email-verifications/confirm", response_model=UserResponse)
def confirm_email_verification(
    payload: TokenConfirmRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    return UserResponse.model_validate(service.confirm_email_verification(payload.token))


@router.post("/password-resets", response_model=AccountTokenDeliveryResponse)
def request_password_reset(
    payload: PasswordResetRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccountTokenDeliveryResponse:
    issued = service.request_password_reset(str(payload.email))
    # Do not reveal whether an account exists. A provider adapter sends the token in production.
    return AccountTokenDeliveryResponse(
        expires_at=issued.expires_at if issued else None,
        debug_token=issued.raw_token if issued and settings.env != "production" else None,
    )


@router.post("/password-resets/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    service.confirm_password_reset(payload.token, payload.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/step-up",
    response_model=AdminStepUpResponse,
    responses={401: AUTHENTICATION_RESPONSE},
)
def step_up_administrator(
    payload: AdminStepUpRequest,
    user: CurrentUser,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AdminStepUpResponse:
    issued = service.step_up_admin(user, payload.password)
    return AdminStepUpResponse(step_up_token=issued.raw_token, expires_at=issued.expires_at)


def _set_refresh_cookies(response: Response, refresh_token: str, settings: Settings) -> None:
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
        path="/api/v1/auth",
    )
    response.set_cookie(
        "csrf_token",
        secrets.token_urlsafe(32),
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        httponly=False,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
        path="/",
    )


def _request_refresh_token(payload: RefreshRequest, request: Request, settings: Settings) -> str:
    if payload.refresh_token:
        return payload.refresh_token
    cookie_token = request.cookies.get("refresh_token")
    if cookie_token:
        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("X-CSRF-Token")
        if settings.env == "production" and (
            not csrf_cookie
            or not csrf_header
            or not secrets.compare_digest(csrf_cookie, csrf_header)
        ):
            from app.core.errors import AuthenticationError

            raise AuthenticationError("CSRF validation failed")
        return cookie_token
    from app.core.errors import AuthenticationError

    raise AuthenticationError("Invalid refresh token")
