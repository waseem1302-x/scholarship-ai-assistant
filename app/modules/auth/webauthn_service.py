"""Phishing-resistant administrator passkeys for Phase 9 step-up."""

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
    options_to_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

from app.core.config import Settings
from app.core.errors import AppError, AuthenticationError
from app.core.security import (
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.modules.auth.models import (
    AdminStepUpToken,
    AuditLog,
    User,
    UserRole,
    WebAuthnChallenge,
    WebAuthnChallengePurpose,
    WebAuthnCredential,
)


class WebAuthnService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def registration_options(self, user: User, password: str) -> dict:
        self._verify_admin_password(user, password)
        credentials = self._credentials(user.id)
        options = generate_registration_options(
            rp_id=self._rp_id(),
            rp_name=self.settings.webauthn_rp_name,
            user_name=user.email,
            user_id=user.id.bytes,
            user_display_name="Administrator",
            authenticator_selection=AuthenticatorSelectionCriteria(
                user_verification=UserVerificationRequirement.REQUIRED
            ),
            exclude_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
                for item in credentials
            ],
        )
        self._store_challenge(
            user.id,
            WebAuthnChallengePurpose.REGISTRATION,
            bytes_to_base64url(options.challenge),
        )
        return json.loads(options_to_json(options))

    def complete_registration(self, user: User, credential: dict) -> str:
        challenge = self._active_challenge(user.id, WebAuthnChallengePurpose.REGISTRATION)
        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=base64url_to_bytes(challenge.challenge),
                expected_rp_id=self._rp_id(),
                expected_origin=self._origins(),
                require_user_verification=True,
            )
        except Exception as exc:
            raise AuthenticationError("Passkey registration could not be verified") from exc
        credential_id = bytes_to_base64url(verified.credential_id)
        if self.session.scalar(
            select(WebAuthnCredential).where(WebAuthnCredential.credential_id == credential_id)
        ):
            raise AppError("passkey_already_registered", "This passkey is already registered.", 409)
        self.session.add(
            WebAuthnCredential(
                user_id=user.id,
                credential_id=credential_id,
                public_key=verified.credential_public_key,
                sign_count=verified.sign_count,
            )
        )
        challenge.consumed_at = datetime.now(UTC)
        self._audit(user.id, "admin_passkey_registered", "user", str(user.id))
        self.session.commit()
        return credential_id

    def step_up_options(self, user: User, password: str) -> dict:
        self._verify_admin_password(user, password)
        credentials = self._credentials(user.id)
        if not credentials:
            raise AppError(
                "admin_passkey_required",
                "Register an administrator passkey before production changes.",
                403,
            )
        options = generate_authentication_options(
            rp_id=self._rp_id(),
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
                for item in credentials
            ],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        self._store_challenge(
            user.id,
            WebAuthnChallengePurpose.STEP_UP,
            bytes_to_base64url(options.challenge),
        )
        return json.loads(options_to_json(options))

    def complete_step_up(self, user: User, credential: dict) -> tuple[str, datetime]:
        challenge = self._active_challenge(user.id, WebAuthnChallengePurpose.STEP_UP)
        credential_id = str(credential.get("id", ""))
        stored = self.session.scalar(
            select(WebAuthnCredential).where(
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.credential_id == credential_id,
            )
        )
        if stored is None:
            raise AuthenticationError("Passkey authentication could not be verified")
        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=base64url_to_bytes(challenge.challenge),
                expected_rp_id=self._rp_id(),
                expected_origin=self._origins(),
                credential_public_key=stored.public_key,
                credential_current_sign_count=stored.sign_count,
                require_user_verification=True,
            )
        except Exception as exc:
            raise AuthenticationError("Passkey authentication could not be verified") from exc
        now = datetime.now(UTC)
        stored.sign_count = verified.new_sign_count
        stored.last_used_at = now
        challenge.consumed_at = now
        raw_token = generate_refresh_token()
        expires_at = now + timedelta(minutes=self.settings.admin_step_up_ttl_minutes)
        self.session.add(
            AdminStepUpToken(
                user_id=user.id,
                token_hash=hash_refresh_token(raw_token),
                expires_at=expires_at,
            )
        )
        self._audit(user.id, "admin_mfa_step_up_completed", "user", str(user.id))
        self.session.commit()
        return raw_token, expires_at

    def _verify_admin_password(self, user: User, password: str) -> None:
        if user.role is not UserRole.ADMIN or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid administrator credentials")
        if self.settings.env == "production" and user.email_verified_at is None:
            raise AuthenticationError("Administrator email verification is required")

    def _store_challenge(
        self, user_id: uuid.UUID, purpose: WebAuthnChallengePurpose, challenge: str
    ) -> None:
        now = datetime.now(UTC)
        for active in self.session.scalars(
            select(WebAuthnChallenge).where(
                WebAuthnChallenge.user_id == user_id,
                WebAuthnChallenge.purpose == purpose,
                WebAuthnChallenge.consumed_at.is_(None),
            )
        ):
            active.consumed_at = now
        self.session.add(
            WebAuthnChallenge(
                user_id=user_id,
                purpose=purpose,
                challenge=challenge,
                expires_at=now + timedelta(minutes=self.settings.webauthn_challenge_ttl_minutes),
            )
        )
        self.session.commit()

    def _active_challenge(
        self, user_id: uuid.UUID, purpose: WebAuthnChallengePurpose
    ) -> WebAuthnChallenge:
        challenge = self.session.scalar(
            select(WebAuthnChallenge)
            .where(
                WebAuthnChallenge.user_id == user_id,
                WebAuthnChallenge.purpose == purpose,
                WebAuthnChallenge.consumed_at.is_(None),
            )
            .order_by(WebAuthnChallenge.created_at.desc())
        )
        now = datetime.now(UTC)
        if challenge is None or self._as_utc(challenge.expires_at) <= now:
            raise AuthenticationError("Passkey challenge is invalid or expired")
        return challenge

    def _credentials(self, user_id: uuid.UUID) -> list[WebAuthnCredential]:
        return list(
            self.session.scalars(
                select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
            )
        )

    def _rp_id(self) -> str:
        return self.settings.webauthn_rp_id or "localhost"

    def _origins(self) -> list[str]:
        return self.settings.webauthn_origin_list or ["http://localhost"]

    def _audit(self, actor_id: uuid.UUID, action: str, entity_type: str, entity_id: str) -> None:
        self.session.add(
            AuditLog(
                actor_user_id=actor_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata_json={"phase": "mfa"},
            )
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
