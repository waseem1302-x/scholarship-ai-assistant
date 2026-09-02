import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.email import get_account_email_sender
from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentUser, require_admin_step_up, require_roles
from app.modules.auth.models import User, UserRole
from app.modules.auth.oauth_service import OAuthService
from app.modules.auth.schemas import (
    AccountClosureRequest,
    AccountTokenDeliveryResponse,
    AdminStepUpRequest,
    AdminStepUpResponse,
    FacebookAuthRequest,
    GoogleAuthRequest,
    LoginRequest,
    LogoutRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenConfirmRequest,
    TokenResponse,
    UserResponse,
    WebAuthnCredentialRemovalRequest,
    WebAuthnCredentialRenameRequest,
    WebAuthnCredentialRequest,
    WebAuthnCredentialResponse,
    WebAuthnOptionsResponse,
    WebAuthnRegistrationResponse,
    WebAuthnStartRequest,
    WebAuthnStepUpResponse,
)
from app.modules.auth.service import AuthService, IssuedTokens
from app.modules.auth.webauthn_service import WebAuthnService

router = APIRouter(prefix="/auth", tags=["authentication"])
StudentUser = Annotated[User, Depends(require_roles(UserRole.STUDENT))]
AdminStepUpUser = Annotated[User, Depends(require_admin_step_up)]

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
    result = service.register(
        str(payload.email),
        payload.password,
        payload.invitation_code,
        payload.accept_beta_terms,
    )
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


# ==============================================================================
# OAUTH2 SOCIAL AUTHENTICATION: GOOGLE & FACEBOOK
# ==============================================================================


@router.post(
    "/oauth/google",
    response_model=TokenResponse,
    responses={401: AUTHENTICATION_RESPONSE, 422: VALIDATION_RESPONSE},
    summary="Login or register 1-click student account via Google ID Token",
)
def oauth_google(
    payload: GoogleAuthRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    oauth_svc = OAuthService(session, settings)
    profile_data = oauth_svc.verify_google_id_token(payload.id_token)
    result = oauth_svc.authenticate_or_register_social_user(
        provider="google",
        provider_user_id=profile_data["provider_user_id"],
        email=profile_data["email"],
    )
    _set_refresh_cookies(response, result.refresh_token, settings)
    return to_token_response(result, include_refresh_token=settings.env != "production")


@router.post(
    "/oauth/facebook",
    response_model=TokenResponse,
    responses={401: AUTHENTICATION_RESPONSE, 422: VALIDATION_RESPONSE},
    summary="Login or register 1-click student account via Meta / Facebook Access Token",
)
def oauth_facebook(
    payload: FacebookAuthRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    oauth_svc = OAuthService(session, settings)
    profile_data = oauth_svc.verify_facebook_token(payload.access_token)
    result = oauth_svc.authenticate_or_register_social_user(
        provider="facebook",
        provider_user_id=profile_data["provider_user_id"],
        email=profile_data["email"],
    )
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


@router.get("/account/export", responses={401: AUTHENTICATION_RESPONSE})
def export_student_account(
    user: StudentUser,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, object]:
    """Owner-only export; intentionally excludes operational/security logs."""
    return service.export_student_account(user)


@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTHENTICATION_RESPONSE},
)
def close_student_account(
    payload: AccountClosureRequest,
    user: StudentUser,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    service.close_student_account(user, payload.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    if settings.env == "production":
        get_account_email_sender(settings).send_verification(
            recipient=user.email, token=issued.raw_token
        )
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
    if issued and settings.env == "production":
        get_account_email_sender(settings).send_password_reset(
            recipient=str(payload.email), token=issued.raw_token
        )
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
    if service.settings.env == "production":
        from app.core.errors import AppError

        raise AppError(
            "admin_mfa_required",
            "Complete passkey verification for an administrator step-up.",
            status.HTTP_403_FORBIDDEN,
        )
    issued = service.step_up_admin(user, payload.password)
    return AdminStepUpResponse(step_up_token=issued.raw_token, expires_at=issued.expires_at)


@router.post("/admin/passkeys/registration-options", response_model=WebAuthnOptionsResponse)
def passkey_registration_options(
    payload: WebAuthnStartRequest,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebAuthnOptionsResponse:
    return WebAuthnOptionsResponse(
        options=WebAuthnService(session, settings).registration_options(user, payload.password)
    )


@router.post("/admin/passkeys", response_model=WebAuthnRegistrationResponse)
def register_passkey(
    payload: WebAuthnCredentialRequest,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebAuthnRegistrationResponse:
    credential_id = WebAuthnService(session, settings).complete_registration(
        user, payload.credential
    )
    return WebAuthnRegistrationResponse(credential_id=credential_id)


@router.get("/admin/passkeys", response_model=list[WebAuthnCredentialResponse])
def list_passkeys(
    user: AdminStepUpUser,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[WebAuthnCredentialResponse]:
    return [
        WebAuthnCredentialResponse.model_validate(credential)
        for credential in WebAuthnService(session, settings).list_credentials(user)
    ]


@router.patch("/admin/passkeys/{credential_id}", response_model=WebAuthnCredentialResponse)
def rename_passkey(
    credential_id: uuid.UUID,
    payload: WebAuthnCredentialRenameRequest,
    user: AdminStepUpUser,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebAuthnCredentialResponse:
    credential = WebAuthnService(session, settings).rename_credential(
        user, credential_id, payload.display_name
    )
    return WebAuthnCredentialResponse.model_validate(credential)


@router.delete("/admin/passkeys/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_passkey(
    credential_id: uuid.UUID,
    payload: WebAuthnCredentialRemovalRequest,
    user: AdminStepUpUser,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    WebAuthnService(session, settings).remove_credential(user, credential_id, payload.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/mfa/options", response_model=WebAuthnOptionsResponse)
def mfa_step_up_options(
    payload: WebAuthnStartRequest,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebAuthnOptionsResponse:
    return WebAuthnOptionsResponse(
        options=WebAuthnService(session, settings).step_up_options(user, payload.password)
    )


@router.post("/admin/mfa/verify", response_model=WebAuthnStepUpResponse)
def complete_mfa_step_up(
    payload: WebAuthnCredentialRequest,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebAuthnStepUpResponse:
    token, expires_at = WebAuthnService(session, settings).complete_step_up(
        user, payload.credential
    )
    return WebAuthnStepUpResponse(step_up_token=token, expires_at=expires_at)


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
