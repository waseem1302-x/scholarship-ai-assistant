"""Small in-process limiter for single-instance deployments.

Deployments that scale horizontally must replace this with a shared-store
implementation before relying on it for abuse protection.
"""

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import Settings
from app.core.security import decode_access_token


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """In-process abuse controls for authentication and assistant requests.

    Assistant requests count before dispatch, irrespective of response status.
    Limits apply independently to an authenticated user and to their client IP.
    A production multi-instance deployment must provide a shared limiter.
    """

    def __init__(
        self,
        app,
        *,
        settings: Settings,
        max_attempts: int = 10,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_seconds)
        self.attempts: defaultdict[str, deque[datetime]] = defaultdict(deque)
        self.assistant_max_requests = settings.assistant_rate_limit_per_minute
        self.assistant_attempts: defaultdict[str, deque[datetime]] = defaultdict(deque)
        self.document_max_requests = settings.document_lab_upload_rate_limit_per_minute
        self.document_attempts: defaultdict[str, deque[datetime]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        auth_limited = request.url.path in {"/api/v1/auth/login", "/api/v1/auth/register"}
        assistant_limited = request.url.path == "/api/v1/assistant/answers"
        document_limited = request.method == "POST" and (
            request.url.path == "/api/v1/document-lab/assets"
            or (
                request.url.path.endswith("/versions")
                and request.url.path.startswith("/api/v1/document-lab/assets/")
            )
        )
        if not auth_limited and not assistant_limited and not document_limited:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        if assistant_limited:
            return await self._limit_assistant_request(request, call_next, client)
        if document_limited:
            return await self._limit_document_request(request, call_next, client)
        now = datetime.now(UTC)
        attempts = self.attempts[client]
        while attempts and attempts[0] <= now - self.window:
            attempts.popleft()
        if len(attempts) >= self.max_attempts:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Try again shortly"}},
                headers={"Retry-After": str(int(self.window.total_seconds()))},
            )
        response = await call_next(request)
        if response.status_code >= 400:
            attempts.append(now)
        return response

    async def _limit_assistant_request(self, request: Request, call_next, client: str) -> Response:
        now = datetime.now(UTC)
        keys = [f"assistant:ip:{client}"]
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            try:
                claims = decode_access_token(
                    authorization.removeprefix("Bearer "), request.app.state.settings
                )
                keys.append(f"assistant:user:{claims.user_id}")
            except Exception:  # Authentication remains the endpoint's responsibility.
                keys.append("assistant:user:anonymous")
        else:
            keys.append("assistant:user:anonymous")
        retry_after = self._consume(keys, now)
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "assistant_rate_limited",
                        "message": "Too many assistant requests. Try again shortly.",
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    def _consume(self, keys: list[str], now: datetime) -> int | None:
        retry_after = 0
        for key in keys:
            attempts = self.assistant_attempts[key]
            while attempts and attempts[0] <= now - self.window:
                attempts.popleft()
            if len(attempts) >= self.assistant_max_requests:
                retry_after = max(
                    retry_after,
                    max(1, int((attempts[0] + self.window - now).total_seconds())),
                )
        if retry_after:
            return retry_after
        for key in keys:
            self.assistant_attempts[key].append(now)
        return None

    async def _limit_document_request(self, request: Request, call_next, client: str) -> Response:
        now = datetime.now(UTC)
        keys = [f"document:ip:{client}", f"document:user:{self._user_key(request)}"]
        retry_after = self._consume_document(keys, now)
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "document_upload_rate_limited",
                        "message": "Too many document uploads. Try again shortly.",
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    def _user_key(self, request: Request) -> str:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            try:
                claims = decode_access_token(
                    authorization.removeprefix("Bearer "), request.app.state.settings
                )
                return str(claims.user_id)
            except Exception:
                pass
        return "anonymous"

    def _consume_document(self, keys: list[str], now: datetime) -> int | None:
        retry_after = 0
        for key in keys:
            attempts = self.document_attempts[key]
            while attempts and attempts[0] <= now - self.window:
                attempts.popleft()
            if len(attempts) >= self.document_max_requests:
                retry_after = max(
                    retry_after,
                    max(1, int((attempts[0] + self.window - now).total_seconds())),
                )
        if retry_after:
            return retry_after
        for key in keys:
            self.document_attempts[key].append(now)
        return None
