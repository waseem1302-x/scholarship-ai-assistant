"""Automated unit test suite for OAuth2 Social Authentication (Google & Facebook)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import AuthenticationError
from app.modules.auth.models import OAuthAccount, User, UserRole
from app.modules.auth.oauth_service import OAuthService
from app.modules.profiles.models import StudentProfile


def test_google_social_registration_and_login(db_session) -> None:
    settings = get_settings()
    oauth_svc = OAuthService(db_session, settings)

    # 1. Simulate Google 1-click registration for a new user
    token_str = "test_google_googlesub123_newstudent@gmail.com"
    profile_data = oauth_svc.verify_google_id_token(token_str)

    assert profile_data["email"] == "newstudent@gmail.com"
    assert profile_data["provider_user_id"] == "googlesub123"
    assert profile_data["email_verified"] is True

    tokens = oauth_svc.authenticate_or_register_social_user(
        provider="google",
        provider_user_id=profile_data["provider_user_id"],
        email=profile_data["email"],
        full_name=profile_data["name"],
    )

    assert tokens.access_token is not None
    assert tokens.refresh_token is not None
    assert tokens.user.email == "newstudent@gmail.com"
    assert tokens.user.role == UserRole.STUDENT
    assert tokens.user.email_verified_at is not None

    # Verify user in database
    db_user = db_session.scalar(select(User).where(User.email == "newstudent@gmail.com"))
    assert db_user is not None
    assert db_user.password_hash is None  # Social accounts don't need passwords
    assert db_user.is_active is True

    # Verify OAuthAccount entry
    oauth_entry = db_session.scalar(
        select(OAuthAccount).where(OAuthAccount.provider_user_id == "googlesub123")
    )
    assert oauth_entry is not None
    assert oauth_entry.user_id == db_user.id
    assert oauth_entry.provider == "google"

    # Verify StudentProfile was auto-initialized
    profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == db_user.id))
    assert profile is not None


def test_google_social_login_existing_user_linking(db_session) -> None:
    settings = get_settings()
    oauth_svc = OAuthService(db_session, settings)

    # 1. Create existing user with standard password
    user_id = uuid.uuid4()
    existing_user = User(
        id=user_id,
        email="existing_candidate@gmail.com",
        password_hash="mocked_password_hash",
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(existing_user)
    db_session.commit()

    # 2. Existing user logs in via Google with the same email
    token_str = "test_google_googlesub456_existing_candidate@gmail.com"
    profile_data = oauth_svc.verify_google_id_token(token_str)

    tokens = oauth_svc.authenticate_or_register_social_user(
        provider="google",
        provider_user_id=profile_data["provider_user_id"],
        email=profile_data["email"],
    )

    assert tokens.user.id == existing_user.id
    assert tokens.user.email_verified_at is not None

    # Check OAuth account was linked to the SAME user id
    oauth_entry = db_session.scalar(
        select(OAuthAccount).where(OAuthAccount.provider_user_id == "googlesub456")
    )
    assert oauth_entry is not None
    assert oauth_entry.user_id == existing_user.id


def test_facebook_social_registration_and_login(db_session) -> None:
    settings = get_settings()
    oauth_svc = OAuthService(db_session, settings)

    token_str = "test_fb_fbuser999_meta_student@facebook.com"
    profile_data = oauth_svc.verify_facebook_token(token_str)

    assert profile_data["email"] == "meta_student@facebook.com"
    assert profile_data["provider_user_id"] == "fbuser999"

    tokens = oauth_svc.authenticate_or_register_social_user(
        provider="facebook",
        provider_user_id=profile_data["provider_user_id"],
        email=profile_data["email"],
        full_name=profile_data["name"],
    )

    assert tokens.access_token is not None
    assert tokens.user.email == "meta_student@facebook.com"

    # Verify OAuth entry
    oauth_entry = db_session.scalar(
        select(OAuthAccount).where(OAuthAccount.provider_user_id == "fbuser999")
    )
    assert oauth_entry is not None
    assert oauth_entry.provider == "facebook"


def test_oauth_inactive_user_blocked(db_session) -> None:
    settings = get_settings()
    oauth_svc = OAuthService(db_session, settings)

    # Inactive user
    inactive_user = User(
        id=uuid.uuid4(),
        email="inactive@example.com",
        is_active=False,
    )
    db_session.add(inactive_user)
    db_session.commit()

    with pytest.raises(AuthenticationError, match="Account is inactive"):
        oauth_svc.authenticate_or_register_social_user(
            provider="google",
            provider_user_id="google_inactive_123",
            email="inactive@example.com",
        )
