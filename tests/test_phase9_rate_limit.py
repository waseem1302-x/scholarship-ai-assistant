from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import (
    AuthRateLimitMiddleware,
    RateLimitStoreUnavailable,
    RedisRateLimitStore,
)


class UnavailableStore:
    def consume(self, *, key: str, limit: int, window_seconds: int):
        del key, limit, window_seconds
        raise RateLimitStoreUnavailable("test outage")

    def health(self) -> bool:
        return False


class ScriptRecordingRedisClient:
    def __init__(self, response: tuple[int, int]) -> None:
        self.response = response
        self.calls: list[tuple[object, ...]] = []

    def eval(self, *args: object) -> tuple[int, int]:
        self.calls.append(args)
        return self.response


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


def test_redis_limiter_uses_an_atomic_sliding_window_script() -> None:
    client = ScriptRecordingRedisClient((1, 0))
    limiter = RedisRateLimitStore.__new__(RedisRateLimitStore)
    limiter._client = client

    result = limiter.consume(key="auth_login:global", limit=10, window_seconds=60)

    script, num_keys, key, _now, window, limit, member = client.calls[0]
    assert result.allowed is True
    assert "ZREMRANGEBYSCORE" in script
    assert "ZRANGE" in script
    assert "ZADD" in script
    assert "PEXPIRE" in script
    assert num_keys == 1
    assert key == "phase9:rate-limit:auth_login:global"
    assert window == 60_000
    assert limit == 10
    assert isinstance(member, str)


def test_redis_sliding_window_returns_atomic_retry_after() -> None:
    client = ScriptRecordingRedisClient((0, 17))
    limiter = RedisRateLimitStore.__new__(RedisRateLimitStore)
    limiter._client = client

    result = limiter.consume(key="account_recovery:ip:test", limit=5, window_seconds=60)

    assert result.allowed is False
    assert result.retry_after_seconds == 17
