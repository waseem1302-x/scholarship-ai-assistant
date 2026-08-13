import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, AuthenticationError
from app.core.password_security import PasswordBreachCheckUnavailable, PwnedPasswordsChecker
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
)
from app.db.base import Base
from app.modules.auth.models import (
    AdminStepUpToken,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
    UserRole,
    WebAuthnChallenge,
)
from app.modules.auth.service import AuthService


def settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "env": "test",
        "database_url": "sqlite+pysqlite:///:memory:",
        "jwt_secret": "session-security-test-secret-at-least-32-characters",
    }
    values.update(changes)
    return Settings(**values)


def user() -> User:
    return User(
        id=uuid.uuid4(),
        email="student@example.test",
        password_hash=hash_password("Secure passphrase 2026!"),
        role=UserRole.STUDENT,
    )


def test_refresh_rotation_claim_is_single_use(db_session) -> None:
    account = user()
    service = AuthService(db_session, settings())
    db_session.add(account)
    initial = service._issue_token_pair(account)
    db_session.commit()

    first = service.refresh(initial.refresh_token)

    with pytest.raises(AuthenticationError):
        service.refresh(initial.refresh_token)
    assert first.refresh_token
    assert db_session.scalar(select(RefreshToken).where(RefreshToken.user_id == account.id))


def test_lost_refresh_rotation_race_revokes_the_whole_family(tmp_path) -> None:
    """A request with a stale read must contain the family after losing its claim."""
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'refresh-race.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with SessionLocal() as setup_session:
            account = user()
            setup = AuthService(setup_session, settings())
            setup_session.add(account)
            initial = setup._issue_token_pair(account)
            setup_session.commit()

        with SessionLocal() as losing_session, SessionLocal() as winning_session:
            losing_service = AuthService(losing_session, settings())
            # Simulate the first request reading the record before its peer commits.
            assert losing_service.repository.get_refresh_token(
                hash_refresh_token(initial.refresh_token)
            )
            winning_service = AuthService(winning_session, settings())
            winning_service.refresh(initial.refresh_token)

            with pytest.raises(AuthenticationError):
                losing_service.refresh(initial.refresh_token)

        with SessionLocal() as verification_session:
            tokens = verification_session.scalars(select(RefreshToken)).all()
            refreshed_user = verification_session.scalar(select(User).where(User.id == account.id))
            assert len(tokens) == 2
            assert all(token.revoked_at is not None for token in tokens)
            assert refreshed_user is not None and refreshed_user.token_version == 1
    finally:
        engine.dispose()


def test_logout_immediately_invalidates_existing_access_token(client, db_session) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "logout-version@example.com", "password": "secure-password-42"},
    )
    token = response.json()["access_token"]
    refresh = response.json()["refresh_token"]

    assert client.post("/api/v1/auth/logout", json={"refresh_token": refresh}).status_code == 204
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_password_reset_immediately_invalidates_existing_access_token(client) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "reset-version@example.com", "password": "secure-password-42"},
    )
    access_token = response.json()["access_token"]
    issued = client.post(
        "/api/v1/auth/password-resets", json={"email": "reset-version@example.com"}
    )
    assert issued.status_code == 200
    assert (
        client.post(
            "/api/v1/auth/password-resets/confirm",
            json={"token": issued.json()["debug_token"], "new_password": "new-secure-password-42"},
        ).status_code
        == 204
    )
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
        ).status_code
        == 401
    )


def test_security_event_immediately_invalidates_existing_access_token(client, db_session) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "security-event@example.com", "password": "secure-password-42"},
    )
    account = db_session.scalar(select(User).where(User.email == "security-event@example.com"))
    assert account is not None

    AuthService(db_session, settings()).invalidate_user_sessions(
        account, reason="administrator_action"
    )

    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        ).status_code
        == 401
    )


def test_jwt_key_rotation_uses_kid_and_accepts_staged_verification_key() -> None:
    current = "current-session-security-secret-at-least-32"
    previous = "previous-session-security-secret-at-least-32"
    rollover_settings = settings(
        jwt_secret=current,
        jwt_active_kid="2026-08",
        jwt_verification_keys='{"2026-07":"previous-session-security-secret-at-least-32"}',
    )
    user_id = uuid.uuid4()
    issued, _ = create_access_token(
        user_id=user_id,
        role="student",
        token_version=2,
        settings=rollover_settings,
    )
    assert jwt.get_unverified_header(issued)["kid"] == "2026-08"
    assert decode_access_token(issued, rollover_settings).token_version == 2

    now = datetime.now(UTC)
    legacy = jwt.encode(
        {
            "sub": str(user_id),
            "role": "student",
            "ver": 2,
            "iss": rollover_settings.jwt_issuer,
            "aud": rollover_settings.jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=5),
            "jti": str(uuid.uuid4()),
            "type": "access",
        },
        previous,
        algorithm="HS256",
        headers={"kid": "2026-07"},
    )
    assert decode_access_token(legacy, rollover_settings).user_id == user_id


def test_new_reset_and_verification_tokens_supersede_existing_ones(db_session) -> None:
    account = user()
    service = AuthService(db_session, settings())
    db_session.add(account)
    db_session.commit()

    first_reset = service.request_password_reset(account.email)
    second_reset = service.request_password_reset(account.email)
    first_verification = service.issue_email_verification(account)
    second_verification = service.issue_email_verification(account)

    with pytest.raises(AuthenticationError):
        service.confirm_password_reset(first_reset.raw_token, "another-secure-password-42")
    with pytest.raises(AuthenticationError):
        service.confirm_email_verification(first_verification.raw_token)
    assert second_reset.raw_token
    assert second_verification.raw_token


def test_auth_retention_purges_old_actionable_artifacts(db_session) -> None:
    account = user()
    old = datetime.now(UTC) - timedelta(days=31)
    db_session.add(account)
    db_session.add_all(
        [
            RefreshToken(user_id=account.id, token_hash="a" * 64, expires_at=old),
            PasswordResetToken(user_id=account.id, token_hash="b" * 64, expires_at=old),
            EmailVerificationToken(user_id=account.id, token_hash="c" * 64, expires_at=old),
            AdminStepUpToken(user_id=account.id, token_hash="d" * 64, expires_at=old),
            WebAuthnChallenge(
                user_id=account.id,
                purpose="registration",
                challenge="challenge",
                expires_at=old,
            ),
        ]
    )
    db_session.commit()

    assert (
        AuthService(db_session, settings(auth_token_retention_days=30)).purge_expired_auth_tokens()
        == 5
    )


class CompromisedChecker:
    def is_compromised(self, password: str) -> bool:
        return password == "known-compromised"


class UnavailableChecker:
    def is_compromised(self, password: str) -> bool:
        raise PasswordBreachCheckUnavailable()


def test_compromised_passwords_are_rejected_before_registration(db_session) -> None:
    service = AuthService(
        db_session,
        settings(password_breach_check_enabled=True),
        password_breach_checker=CompromisedChecker(),
    )

    with pytest.raises(AppError, match="known data breaches"):
        service.register("breached@example.test", "known-compromised")


def test_password_security_check_fails_closed_when_configured(db_session) -> None:
    service = AuthService(
        db_session,
        settings(password_breach_check_enabled=True),
        password_breach_checker=UnavailableChecker(),
    )

    with pytest.raises(AppError) as error:
        service.register("unavailable@example.test", "secure-passphrase-42")
    assert error.value.code == "password_security_check_unavailable"


def test_breach_checker_uses_k_anonymity_prefix_only(monkeypatch) -> None:
    requests: list[object] = []

    class Response:
        def read(self) -> bytes:
            return b"37D0679CA88DB6464EAC60DA96345513964:1\n"

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    def fake_urlopen(request, timeout: int):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr("app.core.password_security.urlopen", fake_urlopen)

    assert PwnedPasswordsChecker(
        endpoint="https://breach.example/range", timeout_seconds=2
    ).is_compromised("12345")
    request, timeout = requests[0]
    assert request.full_url == "https://breach.example/range/8CB22"
    assert timeout == 2


def test_login_opportunistically_upgrades_an_outdated_password_hash(
    db_session, monkeypatch
) -> None:
    account = user()
    db_session.add(account)
    db_session.commit()
    replacement_hash = hash_password("Secure passphrase 2026!")
    monkeypatch.setattr(
        "app.modules.auth.service.verify_password_and_update",
        lambda _password, _hash: (True, replacement_hash),
    )

    AuthService(db_session, settings()).login(account.email, "Secure passphrase 2026!")

    assert account.password_hash == replacement_hash
