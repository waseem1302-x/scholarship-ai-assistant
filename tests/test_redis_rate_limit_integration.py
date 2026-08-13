import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import AuthRateLimitMiddleware, RedisRateLimitStore

pytestmark = pytest.mark.redis


def test_production_login_limiting_uses_disposable_redis() -> None:
    redis_url = os.environ.get("TEST_REDIS_URL")
    if redis_url is None:
        pytest.skip("TEST_REDIS_URL is required for the disposable Redis integration test")
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://api:secret@example.test/scholarship",
        migration_database_url="postgresql+psycopg://migrator:secret@example.test/scholarship",
        jwt_secret="production-test-secret-that-is-at-least-32-characters",
        cors_origins="https://beta.example.test",
        trusted_proxy_ips="10.0.0.1",
        rate_limit_backend="redis",
        rate_limit_redis_url=redis_url,
        email_provider="smtp",
        email_from="Scholarship AI <support@example.test>",
        email_smtp_host="smtp.example.test",
        email_smtp_username="api-user",
        email_smtp_password="smtp-password",
        password_breach_check_enabled=True,
        operations_health_token="production-operations-token",
        metrics_backend="external",
        auth_login_rate_limit_per_minute=1,
        auth_login_global_rate_limit_per_minute=10,
    )
    store = RedisRateLimitStore(redis_url, timeout_seconds=2)
    redis_key = "phase9:rate-limit:auth_login:ip:testclient"
    store._client.delete(redis_key)
    application = FastAPI()
    application.add_middleware(AuthRateLimitMiddleware, settings=settings, store=store)

    @application.post("/api/v1/auth/login")
    def login() -> dict[str, bool]:
        return {"reached": True}

    client = TestClient(application)
    payload = {"email": "student@example.test"}
    try:
        assert client.post("/api/v1/auth/login", json=payload).status_code == 200
        response = client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "auth_login_rate_limited"
    finally:
        store._client.delete(redis_key, "phase9:rate-limit:auth_login:global")
