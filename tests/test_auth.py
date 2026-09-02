import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, AuthenticationError
from app.core.security import hash_password
from app.main import app
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import RefreshToken, User, UserRole, WebAuthnCredential
from app.modules.auth.webauthn_service import WebAuthnService

EMAIL = "student@example.com"
PASSWORD = "correct-horse-42"


def register(client: TestClient, *, email: str = EMAIL, password: str = PASSWORD) -> dict:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201
    return response.json()


def test_register_creates_student_and_protected_me_works(
    client: TestClient, db_session: Session
) -> None:
    payload = register(client, email="  STUDENT@example.com ")

    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 900
    assert payload["user"]["email"] == EMAIL
    assert payload["user"]["role"] == "student"

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL

    user = db_session.scalar(select(User).where(User.email == EMAIL))
    refresh = db_session.scalar(select(RefreshToken))
    assert user is not None and user.password_hash != PASSWORD
    assert user.role is UserRole.STUDENT
    assert refresh is not None and refresh.token_hash != payload["refresh_token"]
    assert len(refresh.token_hash) == 64


def test_registration_accepts_passphrases_and_rejects_short_passwords(client: TestClient) -> None:
    short = client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": "short"},
    )
    assert short.status_code == 422
    assert short.json()["error"]["code"] == "validation_error"

    passphrase = client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": "alllettersnone"},
    )
    assert passphrase.status_code == 201
    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL.upper(), "password": PASSWORD},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_already_registered"


def test_login_uses_generic_errors_and_returns_tokens(client: TestClient) -> None:
    register(client)

    bad_password = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "not-the-password"}
    )
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": "not-the-password"},
    )
    assert bad_password.status_code == unknown_email.status_code == 401
    assert bad_password.json() == unknown_email.json()

    success = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert success.status_code == 200
    assert success.json()["access_token"]
    assert success.json()["refresh_token"]


def test_protected_route_rejects_missing_and_invalid_access_tokens(client: TestClient) -> None:
    missing = client.get("/api/v1/auth/me")
    invalid = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer definitely-not-a-jwt"}
    )

    assert missing.status_code == invalid.status_code == 401
    assert missing.json()["error"]["code"] == "authentication_failed"
    assert invalid.headers["www-authenticate"] == "Bearer"


def test_refresh_rotation_detects_reuse_and_revokes_token_family(client: TestClient) -> None:
    initial = register(client)
    old_refresh = initial["refresh_token"]

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh_token"]
    assert new_refresh != old_refresh

    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reused.status_code == 401

    family_revoked = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert family_revoked.status_code == 401


def test_logout_is_idempotent_and_revokes_refresh_family(client: TestClient) -> None:
    tokens = register(client)
    request = {"refresh_token": tokens["refresh_token"]}

    first = client.post("/api/v1/auth/logout", json=request)
    second = client.post("/api/v1/auth/logout", json=request)
    after_logout = client.post("/api/v1/auth/refresh", json=request)

    assert first.status_code == second.status_code == 204
    assert after_logout.status_code == 401


def test_inactive_user_cannot_use_access_or_refresh_tokens(
    client: TestClient, db_session: Session
) -> None:
    tokens = register(client)
    user = db_session.scalar(select(User).where(User.email == EMAIL))
    assert user is not None
    user.is_active = False
    db_session.commit()

    access_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    refresh_response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert access_response.status_code == refresh_response.status_code == 401


def test_email_verification_uses_single_use_hashed_tokens(client: TestClient) -> None:
    tokens = register(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    issued = client.post("/api/v1/auth/email-verifications", headers=headers)
    assert issued.status_code == 200
    debug_token = issued.json()["debug_token"]
    assert debug_token

    confirmed = client.post("/api/v1/auth/email-verifications/confirm", json={"token": debug_token})
    assert confirmed.status_code == 200
    assert confirmed.json()["email_verified_at"] is not None
    assert (
        client.post(
            "/api/v1/auth/email-verifications/confirm", json={"token": debug_token}
        ).status_code
        == 401
    )


def test_password_reset_revokes_refresh_sessions_and_accepts_new_password(
    client: TestClient,
) -> None:
    tokens = register(client)
    issued = client.post("/api/v1/auth/password-resets", json={"email": EMAIL})
    debug_token = issued.json()["debug_token"]
    assert debug_token

    completed = client.post(
        "/api/v1/auth/password-resets/confirm",
        json={"token": debug_token, "new_password": "updated-password-42"},
    )
    assert completed.status_code == 204
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": "updated-password-42"},
        ).status_code
        == 200
    )


def test_student_account_export_and_closure_are_owner_scoped(
    client: TestClient, db_session: Session
) -> None:
    tokens = register(client, email="close-account@example.com")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    profile = client.put(
        "/api/v1/profiles/me",
        json={"nationality": "Malaysia", "target_degree_level": "masters"},
        headers=headers,
    )
    assert profile.status_code == 200

    exported = client.get("/api/v1/auth/account/export", headers=headers)
    assert exported.status_code == 200, exported.text
    assert exported.json()["account"]["email"] == "close-account@example.com"
    assert exported.json()["profile"]["nationality"] == "Malaysia"
    assert exported.json()["matching"] == {"evaluations": []}
    assert exported.json()["applications"]["legacy_saved_opportunities"] == []

    closed = client.request(
        "DELETE",
        "/api/v1/auth/account",
        json={"password": PASSWORD},
        headers=headers,
    )
    assert closed.status_code == 204
    assert db_session.scalar(select(User).where(User.email == "close-account@example.com")) is None
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "close-account@example.com", "password": PASSWORD},
        ).status_code
        == 401
    )


def test_admin_step_up_requires_an_administrator(client: TestClient, db_session: Session) -> None:
    admin = User(
        id=uuid.uuid4(),
        email="step-up-admin@example.com",
        password_hash=hash_password(PASSWORD),
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login", json={"email": admin.email, "password": PASSWORD}
    ).json()

    response = client.post(
        "/api/v1/auth/admin/step-up",
        json={"password": PASSWORD},
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["step_up_token"]


def test_admin_passkey_options_require_password_and_record_a_single_use_challenge(
    db_session: Session,
) -> None:
    administrator = User(
        id=uuid.uuid4(),
        email="passkey-admin@example.com",
        password_hash=hash_password(PASSWORD),
        role=UserRole.ADMIN,
    )
    db_session.add(administrator)
    db_session.commit()
    service = WebAuthnService(
        db_session,
        Settings(
            env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret="passkey-test-secret-that-is-at-least-32-characters",
            webauthn_rp_id="localhost",
            webauthn_origins="http://localhost",
        ),
    )

    options = service.registration_options(administrator, PASSWORD)
    assert options["rp"]["id"] == "localhost"
    with pytest.raises(AuthenticationError):
        service.registration_options(administrator, "wrong-password")
    with pytest.raises(AppError) as no_passkey:
        service.step_up_options(administrator, PASSWORD)
    assert no_passkey.value.code == "admin_passkey_required"


def test_administrator_can_manage_passkey_lifecycle(
    client: TestClient, db_session: Session
) -> None:
    administrator = User(
        id=uuid.uuid4(),
        email="passkey-lifecycle-admin@example.com",
        password_hash=hash_password(PASSWORD),
        role=UserRole.ADMIN,
    )
    first = WebAuthnCredential(
        user_id=administrator.id,
        credential_id="first-passkey",
        display_name="Laptop",
        public_key=b"first-public-key",
        sign_count=0,
    )
    second = WebAuthnCredential(
        user_id=administrator.id,
        credential_id="second-passkey",
        display_name="Phone",
        public_key=b"second-public-key",
        sign_count=0,
    )
    db_session.add_all((administrator, first, second))
    db_session.commit()
    access_token = client.post(
        "/api/v1/auth/login", json={"email": administrator.email, "password": PASSWORD}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    listed = client.get("/api/v1/auth/admin/passkeys", headers=headers)
    assert listed.status_code == 200
    assert {item["display_name"] for item in listed.json()} == {"Laptop", "Phone"}

    renamed = client.patch(
        f"/api/v1/auth/admin/passkeys/{first.id}",
        json={"display_name": "Work laptop"},
        headers=headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["display_name"] == "Work laptop"

    removed = client.request(
        "DELETE",
        f"/api/v1/auth/admin/passkeys/{first.id}",
        json={"password": PASSWORD},
        headers=headers,
    )
    assert removed.status_code == 204
    assert [
        item["display_name"]
        for item in client.get("/api/v1/auth/admin/passkeys", headers=headers).json()
    ] == ["Phone"]

    final_removal = client.request(
        "DELETE",
        f"/api/v1/auth/admin/passkeys/{second.id}",
        json={"password": PASSWORD},
        headers=headers,
    )
    assert final_removal.status_code == 409
    assert final_removal.json()["error"]["code"] == "final_passkey_removal_blocked"


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_root_serves_frontend(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "The Next Scholar" in response.text
    assert '<div id="root"></div>' in response.text


def test_frontend_bundle_is_served(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "/assets/" in response.text


def test_role_dependency_denies_student_and_allows_admin() -> None:
    admin_only = require_roles(UserRole.ADMIN)
    student = User(
        id=uuid.uuid4(),
        email="student@example.com",
        password_hash="unused",
        role=UserRole.STUDENT,
    )
    admin = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        password_hash="unused",
        role=UserRole.ADMIN,
    )

    with pytest.raises(AppError) as error:
        admin_only(student)
    assert error.value.status_code == 403
    assert admin_only(admin) is admin


def test_database_rejects_unsupported_role_and_non_normalized_email(
    db_session: Session,
) -> None:
    statement = text(
        "INSERT INTO users (id, email, password_hash, role, is_active) "
        "VALUES (:id, :email, :password_hash, :role, :is_active)"
    )
    with pytest.raises(IntegrityError):
        db_session.execute(
            statement,
            {
                "id": uuid.uuid4().hex,
                "email": "student@example.com",
                "password_hash": "unused",
                "role": "superadmin",
                "is_active": True,
            },
        )
        db_session.commit()
    db_session.rollback()

    with pytest.raises(IntegrityError):
        db_session.execute(
            statement,
            {
                "id": uuid.uuid4().hex,
                "email": "Student@Example.com",
                "password_hash": "unused",
                "role": "student",
                "is_active": True,
            },
        )
        db_session.commit()


def test_openapi_documents_actual_authentication_error_contracts() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    assert set(paths["/api/v1/auth/register"]["post"]["responses"]) >= {"201", "409", "422"}
    assert set(paths["/api/v1/auth/login"]["post"]["responses"]) >= {"200", "401", "422"}
    assert set(paths["/api/v1/auth/refresh"]["post"]["responses"]) >= {"200", "401", "422"}
    assert set(paths["/api/v1/auth/logout"]["post"]["responses"]) >= {"204", "422"}
    assert set(paths["/api/v1/auth/me"]["get"]["responses"]) >= {"200", "401"}

    validation_schema = paths["/api/v1/auth/register"]["post"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]
    assert validation_schema == {"$ref": "#/components/schemas/ErrorResponse"}
