import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.main import app
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import RefreshToken, User, UserRole

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


def test_registration_validates_password_and_duplicate_email(client: TestClient) -> None:
    weak = client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": "alllettersnone"},
    )
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "validation_error"

    register(client)
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


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_root_redirects_to_api_documentation(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


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
