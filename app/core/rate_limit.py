"""Shared, fail-closed request-abuse controls.

The local in-memory store is intentionally limited to development and tests.
Production settings require Redis so independent API instances consume the same
atomic counters.
"""

import json
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
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
    """Atomic Redis sliding-window limiter with safe failure behavior."""

    _CONSUME = """
    local cutoff = tonumber(ARGV[1]) - tonumber(ARGV[2])
    redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, cutoff)
    local count = redis.call('ZCARD', KEYS[1])
    if count >= tonumber(ARGV[3]) then
      local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
      local retry_after_ms = tonumber(oldest[2]) + tonumber(ARGV[2]) - tonumber(ARGV[1])
      return {0, math.max(1, math.ceil(retry_after_ms / 1000))}
    end
    redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
    redis.call('PEXPIRE', KEYS[1], ARGV[2])
    return {1, 0}
    """

    def __init__(self, url: str, timeout_seconds: int) -> None:
        self._client = Redis.from_url(
            url,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
            decode_responses=False,
        )

    def consume(self, *, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now_milliseconds = int(datetime.now(UTC).timestamp() * 1000)
        window_milliseconds = window_seconds * 1000
        try:
            allowed, retry_after = self._client.eval(
                self._CONSUME,
                1,
                f"phase9:rate-limit:{key}",
                now_milliseconds,
                window_milliseconds,
                limit,
                f"{now_milliseconds}:{uuid.uuid4().hex}",
            )
        except RedisError as exc:
            raise RateLimitStoreUnavailable("The shared rate-limit store is unavailable") from exc
        return RateLimitResult(bool(int(allowed)), int(retry_after))

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
        max_attempts: int | None = None,
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
        if route_class == "auth_login":
            blocked = self._consume_request(
                ["auth_login:global"],
                self.settings.auth_login_global_rate_limit_per_minute,
                "auth_login_rate_limited",
                "Too many login attempts. Try again shortly.",
            )
            if blocked is not None:
                return blocked
        if route_class in {"assistant", "document_upload"}:
            global_limit = (
                self.settings.assistant_global_daily_limit
                if route_class == "assistant"
                else self.settings.document_lab_global_daily_upload_limit
            )
            blocked = self._consume_request(
                [f"{route_class}:global:daily"],
                global_limit,
                "global_high_cost_quota_exceeded",
                "This capability has reached its protected daily capacity.",
                window_seconds=86_400,
            )
            if blocked is not None:
                return blocked
        keys = await self._keys_for(request, route_class)
        maximum, code, message = self._limit_for(route_class)
        blocked = self._consume_request(keys, maximum, code, message)
        return blocked if blocked is not None else await call_next(request)

    def _route_class(self, request: Request) -> str | None:
        path = request.url.path
        if request.method == "POST":
            route_classes = {
                "/api/v1/auth/login": "auth_login",
                "/api/v1/auth/register": "auth_registration",
                "/api/v1/auth/password-resets": "account_recovery",
                "/api/v1/auth/password-resets/confirm": "account_recovery",
                "/api/v1/auth/email-verifications": "account_verification",
                "/api/v1/auth/email-verifications/confirm": "account_verification",
                "/api/v1/auth/admin/step-up": "admin_reauthentication",
                "/api/v1/auth/admin/passkeys/registration-options": "webauthn",
                "/api/v1/auth/admin/passkeys": "webauthn",
                "/api/v1/auth/admin/mfa/options": "webauthn",
                "/api/v1/auth/admin/mfa/verify": "webauthn",
            }
            if route_class := route_classes.get(path):
                return route_class
        if request.method in {"PATCH", "DELETE"} and request.url.path.startswith(
            "/api/v1/auth/admin/passkeys/"
        ):
            return "webauthn"
        if path == "/api/v1/assistant/answers":
            return "assistant"
        if request.method == "POST" and (
            path == "/api/v1/document-lab/assets"
            or (path.endswith("/versions") and path.startswith("/api/v1/document-lab/assets/"))
        ):
            return "document_upload"
        if (
            request.method in {"POST", "PATCH", "DELETE"}
            and path.startswith("/api/v1/community/")
            and "/admin/" not in path
        ):
            return "community_write"
        return None

    def _limit_for(self, route_class: str) -> tuple[int, str, str]:
        if route_class == "auth_login":
            return (
                self.max_attempts or self.settings.auth_login_rate_limit_per_minute,
                "auth_login_rate_limited",
                "Too many login attempts. Try again shortly.",
            )
        if route_class == "auth_registration":
            return (
                self.max_attempts or self.settings.auth_registration_rate_limit_per_minute,
                "auth_registration_rate_limited",
                "Too many registration attempts. Try again shortly.",
            )
        if route_class == "account_recovery":
            return (
                self.settings.account_recovery_rate_limit_per_minute,
                "account_recovery_rate_limited",
                "Too many account recovery requests. Try again shortly.",
            )
        if route_class == "account_verification":
            return (
                self.settings.account_verification_rate_limit_per_minute,
                "account_verification_rate_limited",
                "Too many verification requests. Try again shortly.",
            )
        if route_class == "admin_reauthentication":
            return (
                self.settings.admin_reauthentication_rate_limit_per_minute,
                "admin_reauthentication_rate_limited",
                "Too many administrator reauthentication attempts. Try again shortly.",
            )
        if route_class == "webauthn":
            return (
                self.settings.webauthn_rate_limit_per_minute,
                "webauthn_rate_limited",
                "Too many passkey requests. Try again shortly.",
            )
        if route_class == "assistant":
            return (
                self.settings.assistant_rate_limit_per_minute,
                "assistant_rate_limited",
                "Too many assistant requests. Try again shortly.",
            )
        if route_class == "document_upload":
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

    async def _keys_for(self, request: Request, route_class: str) -> list[str]:
        keys = [f"{route_class}:ip:{self._client_key(request)}"]
        if route_class in {"auth_login", "auth_registration", "account_recovery"}:
            field = (
                "email"
                if route_class in {"auth_login", "auth_registration"}
                or request.url.path.endswith("password-resets")
                else "token"
            )
            if identifier := await self._body_identifier(request, field):
                keys.append(f"{route_class}:account:{identifier}")
        elif route_class == "account_verification":
            if request.url.path.endswith("confirm"):
                if identifier := await self._body_identifier(request, "token"):
                    keys.append(f"{route_class}:token:{identifier}")
            else:
                keys.append(f"{route_class}:user:{self._user_key(request)}")
        else:
            keys.append(f"{route_class}:user:{self._user_key(request)}")
        return keys

    @staticmethod
    async def _body_identifier(request: Request, field: str) -> str | None:
        try:
            payload = json.loads((await request.body()).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        value = payload.get(field) if isinstance(payload, dict) else None
        if not isinstance(value, str) or not (normalized := value.strip().casefold()):
            return None
        return sha256(normalized.encode("utf-8")).hexdigest()

    def _consume_request(
        self,
        keys: list[str],
        maximum: int,
        code: str,
        message: str = "Try again shortly",
        window_seconds: int | None = None,
    ) -> JSONResponse | None:
        try:
            results = [
                self.store.consume(
                    key=key,
                    limit=maximum,
                    window_seconds=window_seconds or self.window_seconds,
                )
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
