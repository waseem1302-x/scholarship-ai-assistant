import uuid
from hashlib import sha256

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import AuthRateLimitMiddleware, RateLimitResult
from app.core.security import create_access_token


class RecordingStore:
    def __init__(self) -> None:
        self.keys: list[str] = []
        self.attempts: dict[str, int] = {}

    def consume(self, *, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        del window_seconds
        self.keys.append(key)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        return RateLimitResult(self.attempts[key] <= limit, retry_after_seconds=60)

    def health(self) -> bool:
        return True


def limiter_settings(**changes: object) -> Settings:
    return Settings(
        env="development",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="auth-rate-limit-test-secret-at-least-32-characters",
        **changes,
    )


def protected_client(settings: Settings, store: RecordingStore) -> TestClient:
    application = FastAPI()
    application.add_middleware(AuthRateLimitMiddleware, settings=settings, store=store)

    for path in (
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/password-resets",
        "/api/v1/auth/password-resets/confirm",
        "/api/v1/auth/email-verifications",
        "/api/v1/auth/email-verifications/confirm",
        "/api/v1/auth/admin/step-up",
        "/api/v1/auth/admin/passkeys/registration-options",
        "/api/v1/auth/admin/passkeys",
        "/api/v1/auth/admin/mfa/options",
        "/api/v1/auth/admin/mfa/verify",
    ):

        @application.post(path)
        def protected_route() -> dict[str, bool]:
            return {"reached": True}

    return TestClient(application)


@pytest.mark.parametrize(
    ("path", "payload", "route_class", "identifier_kind", "identifier"),
    [
        (
            "/api/v1/auth/login",
            {"email": "Student@example.test"},
            "auth_login",
            "account",
            "student@example.test",
        ),
        (
            "/api/v1/auth/register",
            {"email": "Student@example.test"},
            "auth_registration",
            "account",
            "student@example.test",
        ),
        (
            "/api/v1/auth/password-resets",
            {"email": "Student@example.test"},
            "account_recovery",
            "account",
            "student@example.test",
        ),
        (
            "/api/v1/auth/password-resets/confirm",
            {"token": "recovery-token"},
            "account_recovery",
            "account",
            "recovery-token",
        ),
        (
            "/api/v1/auth/email-verifications/confirm",
            {"token": "verification-token"},
            "account_verification",
            "token",
            "verification-token",
        ),
    ],
)
def test_unauthenticated_account_routes_use_dedicated_ip_and_hashed_identifier_limits(
    path: str,
    payload: dict[str, str],
    route_class: str,
    identifier_kind: str,
    identifier: str,
) -> None:
    store = RecordingStore()
    client = protected_client(limiter_settings(), store)

    response = client.post(path, json=payload)

    identifier_hash = sha256(identifier.encode("utf-8")).hexdigest()
    assert response.json() == {"reached": True}
    assert f"{route_class}:ip:testclient" in store.keys
    assert f"{route_class}:{identifier_kind}:{identifier_hash}" in store.keys


@pytest.mark.parametrize(
    ("path", "route_class"),
    [
        ("/api/v1/auth/email-verifications", "account_verification"),
        ("/api/v1/auth/admin/step-up", "admin_reauthentication"),
        ("/api/v1/auth/admin/passkeys/registration-options", "webauthn"),
        ("/api/v1/auth/admin/passkeys", "webauthn"),
        ("/api/v1/auth/admin/mfa/options", "webauthn"),
        ("/api/v1/auth/admin/mfa/verify", "webauthn"),
    ],
)
def test_authenticated_sensitive_routes_use_dedicated_ip_and_user_limits(
    path: str,
    route_class: str,
) -> None:
    settings = limiter_settings()
    store = RecordingStore()
    client = protected_client(settings, store)
    user_id = uuid.uuid4()
    access_token, _ = create_access_token(user_id=user_id, role="admin", settings=settings)

    response = client.post(path, json={}, headers={"Authorization": f"Bearer {access_token}"})

    assert response.json() == {"reached": True}
    assert f"{route_class}:ip:testclient" in store.keys
    assert f"{route_class}:user:{user_id}" in store.keys


def test_account_recovery_limit_returns_its_dedicated_error_code() -> None:
    settings = limiter_settings(account_recovery_rate_limit_per_minute=1)
    client = protected_client(settings, RecordingStore())
    payload = {"email": "student@example.test"}

    assert client.post("/api/v1/auth/password-resets", json=payload).status_code == 200
    response = client.post("/api/v1/auth/password-resets", json=payload)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "account_recovery_rate_limited"


def test_login_uses_a_global_defensive_threshold() -> None:
    settings = limiter_settings(
        auth_login_rate_limit_per_minute=10,
        auth_login_global_rate_limit_per_minute=10,
    )
    store = RecordingStore()
    client = protected_client(settings, store)

    response = client.post("/api/v1/auth/login", json={"email": "student@example.test"})

    assert response.status_code == 200
    assert "auth_login:global" in store.keys


def test_global_login_threshold_blocks_before_per_account_limits() -> None:
    settings = limiter_settings(
        auth_login_rate_limit_per_minute=10,
        auth_login_global_rate_limit_per_minute=1,
    )
    client = protected_client(settings, RecordingStore())

    assert (
        client.post("/api/v1/auth/login", json={"email": "first@example.test"}).status_code == 200
    )
    response = client.post("/api/v1/auth/login", json={"email": "second@example.test"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "auth_login_rate_limited"
