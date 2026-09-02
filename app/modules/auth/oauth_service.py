"""OAuth2 Social Authentication Service (Google, Facebook, etc.)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.modules.auth.models import OAuthAccount, User, UserRole
from app.modules.auth.service import AuthService, IssuedTokens
from app.modules.profiles.models import StudentProfile, TargetDegreeLevel


class OAuthService:
    """Handles OAuth token verification, user linking, and social auto-registration."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.auth_service = AuthService(session, settings)

    def verify_google_id_token(self, id_token: str) -> dict[str, Any]:
        """Verify Google ID token via Google TokenInfo endpoint or test stub."""
        token_str = id_token.strip()
        # Support test bypass strictly for automated unit tests
        if self.settings.env == "test" and token_str.startswith("test_google_"):
            parts = token_str.split("_", 3)
            sub = parts[2] if len(parts) > 2 else "google-user"
            email = parts[3] if len(parts) > 3 else "student@gmail.com"
            return {
                "provider_user_id": sub,
                "email": email.lower(),
                "name": "Google Student",
                "picture": None,
                "email_verified": True,
            }

        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(token_str)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ScholarshipAI-OAuth"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise AuthenticationError("Invalid or expired Google ID token") from exc

        if "error" in data or "error_description" in data:
            raise AuthenticationError(data.get("error_description", "Invalid Google ID token"))

        email = data.get("email")
        sub = data.get("sub")
        if not email or not sub:
            raise AuthenticationError("Incomplete Google user profile")

        # Validate audience when client ID is configured
        if self.settings.google_client_id and data.get("aud") != self.settings.google_client_id:
            raise AuthenticationError("Google token audience mismatch")
        if str(data.get("email_verified", "")).lower() not in {"true", "1"}:
            raise AuthenticationError("Google email is not verified")

        return {
            "provider_user_id": str(sub),
            "email": str(email).strip().lower(),
            "name": data.get("name") or "Google User",
            "picture": data.get("picture"),
            "email_verified": True,
        }

    def verify_facebook_token(self, access_token: str) -> dict[str, Any]:
        """Verify Facebook user access token via Graph API or test stub."""
        token_str = access_token.strip()
        # Support test bypass strictly for automated unit tests
        if self.settings.env == "test" and token_str.startswith("test_fb_"):
            parts = token_str.split("_", 3)
            fb_id = parts[2] if len(parts) > 2 else "987654321"
            email = parts[3] if len(parts) > 3 else "student@facebook.com"
            return {
                "provider_user_id": fb_id,
                "email": email.lower(),
                "name": "Facebook Student",
                "picture": None,
                "email_verified": True,
            }

        url = f"https://graph.facebook.com/me?fields=id,name,email,picture&access_token={urllib.parse.quote(token_str)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ScholarshipAI-OAuth"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise AuthenticationError("Invalid or expired Facebook access token") from exc

        if "error" in data:
            raise AuthenticationError("Invalid Facebook access token")

        fb_id = data.get("id")
        email = data.get("email")
        if not fb_id or not email:
            raise AuthenticationError(
                "Incomplete Facebook user profile or email permission not granted"
            )

        return {
            "provider_user_id": str(fb_id),
            "email": str(email).strip().lower(),
            "name": data.get("name") or "Facebook User",
            "picture": data.get("picture", {}).get("data", {}).get("url"),
            "email_verified": True,
        }

    def authenticate_or_register_social_user(
        self,
        *,
        provider: str,
        provider_user_id: str,
        email: str,
    ) -> IssuedTokens:
        """Authenticate existing social user or register new student account in 1 transaction."""
        norm_email = email.strip().lower()
        now = datetime.now(UTC)

        # 1. Check if OAuth account already linked
        oauth_account = self.session.scalar(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == provider_user_id,
            )
        )

        if oauth_account is not None:
            user = oauth_account.user
            if not user.is_active:
                raise AuthenticationError("Account is inactive or disabled")
            # Update verification if needed
            if user.email_verified_at is None:
                user.email_verified_at = now
        else:
            # 2. Check if user with this email exists
            user = self.session.scalar(select(User).where(User.email == norm_email))
            if user is not None:
                if not user.is_active:
                    raise AuthenticationError("Account is inactive or disabled")
                if user.role == UserRole.ADMIN:
                    raise AuthenticationError(
                        "Administrative accounts cannot be linked via unauthenticated social login"
                    )
                if user.email_verified_at is None:
                    user.email_verified_at = now
                new_link = OAuthAccount(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    provider_email=norm_email,
                )
                self.session.add(new_link)
            else:
                # 3. Create brand new User + OAuthAccount + StudentProfile
                user = User(
                    id=uuid.uuid4(),
                    email=norm_email,
                    password_hash=None,  # No password for purely social login
                    role=UserRole.STUDENT,
                    is_active=True,
                    email_verified_at=now,
                )
                self.session.add(user)
                self.session.flush()

                new_link = OAuthAccount(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    provider_email=norm_email,
                )
                self.session.add(new_link)

                # Initialize student profile automatically
                profile = StudentProfile(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    target_degree_level=TargetDegreeLevel.MASTERS,
                )
                self.session.add(profile)

        # Record audit log
        self.auth_service._audit(user.id, f"oauth_login_{provider}", "user", str(user.id))

        tokens = self.auth_service._issue_token_pair(user=user)
        self.session.commit()
        self.session.refresh(user)
        return tokens
