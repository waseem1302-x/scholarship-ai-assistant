from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import (
    AuthRateLimitMiddleware,
    RateLimitStoreUnavailable,
)


class UnavailableStore:
    def consume(self, *, key: str, limit: int, window_seconds: int):
        del key, limit, window_seconds
        raise RateLimitStoreUnavailable("test outage")

    def health(self) -> bool:
        return False


def test_shared_store_outage_fails_closed_before_high_cost_work() -> None:
    settings = Settings(
        env="development",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="phase-nine-rate-limit-test-secret-at-least-32",
    )
    limiter = AuthRateLimitMiddleware(
        lambda scope, receive, send: None,
        settings=settings,
        store=UnavailableStore(),
    )

    result = limiter._consume_request(
        ["assistant:user:test"],
        settings.assistant_rate_limit_per_minute,
        "assistant_rate_limited",
    )
    assert result is not None
    assert result.status_code == 503


def test_shared_store_outage_fails_closed_before_authentication_work() -> None:
    settings = Settings(
        env="development",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="phase-nine-rate-limit-test-secret-at-least-32",
    )
    application = FastAPI()
    application.add_middleware(
        AuthRateLimitMiddleware,
        settings=settings,
        store=UnavailableStore(),
    )

    @application.post("/api/v1/auth/login")
    def login() -> dict[str, bool]:
        return {"should_not_run": True}

    response = TestClient(application).post("/api/v1/auth/login")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "rate_limit_store_unavailable"


def test_in_memory_limiter_preserves_existing_assistant_contract() -> None:
    settings = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="phase-nine-rate-limit-test-secret-at-least-32",
        assistant_rate_limit_per_minute=1,
    )
    limiter = AuthRateLimitMiddleware(lambda scope, receive, send: None, settings=settings)

    assert limiter._consume(["assistant:user:test"], datetime.now(UTC)) is None
    assert limiter._consume(["assistant:user:test"], datetime.now(UTC)) is not None
