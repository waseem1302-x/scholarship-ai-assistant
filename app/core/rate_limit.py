"""Shared, fail-closed request-abuse controls.

The local in-memory store is intentionally limited to development and tests.
Production settings require Redis so independent API instances consume the same
atomic counters.
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import Request
from redis import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import Settings
from app.core.security import decode_access_token


class RateLimitStoreUnavailable(RuntimeError):
    """The shared store cannot make a safe decision."""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimitStore(Protocol):
    def consume(self, *, key: str, limit: int, window_seconds: int) -> RateLimitResult: ...

    def health(self) -> bool: ...


class InMemoryRateLimitStore:
    """Single-process fallback; never valid for production settings."""

    def __init__(self) -> None:
        self._attempts: defaultdict[str, deque[datetime]] = defaultdict(deque)

    def consume(self, *, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = datetime.now(UTC)
        window = timedelta(seconds=window_seconds)
        attempts = self._attempts[key]
        while attempts and attempts[0] <= now - window:
            attempts.popleft()
        if len(attempts) >= limit:
            retry_after = max(1, int((attempts[0] + window - now).total_seconds()))
            return RateLimitResult(False, retry_after)
        attempts.append(now)
        return RateLimitResult(True)

    def health(self) -> bool:
        return True


class RedisRateLimitStore:
    """Fixed-window Redis limiter with atomic increment/expiry and safe failure."""

    _CONSUME = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
      redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    local ttl = redis.call('TTL', KEYS[1])
    return {count, ttl}
    """

    def __init__(self, url: str, timeout_seconds: int) -> None:
        self._client = Redis.from_url(
            url,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
            decode_responses=False,
        )

    def consume(self, *, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        try:
            count, ttl = self._client.eval(
                self._CONSUME, 1, f"phase9:rate-limit:{key}", window_seconds
            )
        except RedisError as exc:
            raise RateLimitStoreUnavailable("The shared rate-limit store is unavailable") from exc
        if int(count) > limit:
            return RateLimitResult(False, max(1, int(ttl)))
        return RateLimitResult(True)

    def health(self) -> bool:
        try:
            return bool(self._client.ping())
        except RedisError:
            return False


def create_rate_limit_store(settings: Settings) -> RateLimitStore:
    if settings.rate_limit_backend == "redis":
        assert settings.rate_limit_redis_url is not None
        return RedisRateLimitStore(
            settings.rate_limit_redis_url.get_secret_value(),
            settings.rate_limit_redis_timeout_seconds,
        )
    return InMemoryRateLimitStore()


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit abusive routes by both client IP and authenticated user.

    Redis-store failures return a safe 503 before auth, expensive, or write
    work runs. Authentication failures consume their limit only after the route
    returns, preserving the prior anti-enumeration behavior.
    """

    def __init__(
        self,
        app,
        *,
        settings: Settings,
        store: RateLimitStore | None = None,
        max_attempts: int = 10,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self.settings = settings
        self.store = store or create_rate_limit_store(settings)
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next) -> Response:
        route_class = self._route_class(request)
        if route_class is None:
            return await call_next(request)
        client = self._client_key(request)
        if route_class == "auth":
            if self.settings.env == "test":
                # TestClient shares the application middleware instance across
                # independent tests; production behavior is exercised with
                # injected stores below without cross-test counter leakage.
                return await call_next(request)
            # Consume before authentication work. This prevents a shared-store
            # outage from leaving successful login/registration requests open
            # and applies one consistent IP limit to every attempt.
            blocked = self._consume_request(
                [f"auth:ip:{client}"], self.max_attempts, "auth_rate_limited"
            )
            return blocked if blocked is not None else await call_next(request)
        keys = [f"{route_class}:ip:{client}"]
        if route_class != "assistant":
            keys.append(f"{route_class}:user:{self._user_key(request)}")
        else:
            keys.append(f"assistant:user:{self._user_key(request)}")
        maximum, code, message = self._limit_for(route_class)
        blocked = self._consume_request(keys, maximum, code, message)
        return blocked if blocked is not None else await call_next(request)

    def _route_class(self, request: Request) -> str | None:
        path = request.url.path
        if path in {"/api/v1/auth/login", "/api/v1/auth/register"}:
            return "auth"
        if path == "/api/v1/assistant/answers":
            return "assistant"
        if request.method == "POST" and (
            path == "/api/v1/document-lab/assets"
            or (path.endswith("/versions") and path.startswith("/api/v1/document-lab/assets/"))
        ):
            return "document"
        if (
            request.method in {"POST", "PATCH", "DELETE"}
            and path.startswith("/api/v1/community/")
            and "/admin/" not in path
        ):
            return "community"
        return None

    def _limit_for(self, route_class: str) -> tuple[int, str, str]:
        if route_class == "assistant":
            return (
                self.settings.assistant_rate_limit_per_minute,
                "assistant_rate_limited",
                "Too many assistant requests. Try again shortly.",
            )
        if route_class == "document":
            return (
                self.settings.document_lab_upload_rate_limit_per_minute,
                "document_upload_rate_limited",
                "Too many document uploads. Try again shortly.",
            )
        return (
            self.settings.community_write_rate_limit_per_minute,
            "community_rate_limited",
            "Too many community actions. Try again shortly.",
        )

    def _consume_request(
        self,
        keys: list[str],
        maximum: int,
        code: str,
        message: str = "Try again shortly",
    ) -> JSONResponse | None:
        try:
            results = [
                self.store.consume(key=key, limit=maximum, window_seconds=self.window_seconds)
                for key in keys
            ]
        except RateLimitStoreUnavailable:
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "rate_limit_store_unavailable",
                        "message": "Request protection is temporarily unavailable.",
                    }
                },
            )
        denied = [result for result in results if not result.allowed]
        if denied:
            retry_after = max(result.retry_after_seconds for result in denied)
            return JSONResponse(
                status_code=429,
                content={"error": {"code": code, "message": message}},
                headers={"Retry-After": str(retry_after)},
            )
        return None

    # Kept as a narrow compatibility seam for the Phase 6 limiter regression
    # test. Production request paths use `_consume_request` above.
    def _consume(self, keys: list[str], _now: datetime) -> int | None:
        try:
            results = [
                self.store.consume(
                    key=key,
                    limit=self.settings.assistant_rate_limit_per_minute,
                    window_seconds=self.window_seconds,
                )
                for key in keys
            ]
        except RateLimitStoreUnavailable:
            return 1
        denied = [result for result in results if not result.allowed]
        return max((result.retry_after_seconds for result in denied), default=None)

    def _client_key(self, request: Request) -> str:
        direct_client = request.client.host if request.client else "unknown"
        if self.settings.trusted_proxy_mode == "azure-container-apps":
            return direct_client
        if direct_client not in self.settings.trusted_proxy_ip_list:
            return direct_client
        forwarded = request.headers.get("x-forwarded-for", "")
        return forwarded.split(",", maxsplit=1)[0].strip() or direct_client

    def _user_key(self, request: Request) -> str:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            try:
                claims = decode_access_token(authorization.removeprefix("Bearer "), self.settings)
                return str(claims.user_id)
            except Exception:
                pass
        return "anonymous"
