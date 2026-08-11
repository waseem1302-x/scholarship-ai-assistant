"""Small in-process limiter for single-instance deployments.

Deployments that scale horizontally must replace this with a shared-store
implementation before relying on it for abuse protection.
"""

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_attempts: int = 10, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_seconds)
        self.attempts: defaultdict[str, deque[datetime]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path not in {"/api/v1/auth/login", "/api/v1/auth/register"}:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
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
