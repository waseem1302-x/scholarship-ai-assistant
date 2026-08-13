"""Privacy-safe request correlation and in-process operational metrics."""

import json
import logging
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from threading import Lock

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import Settings

LOGGER = logging.getLogger("scholarship.operations")
TRACE_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


class SafeJsonFormatter(logging.Formatter):
    """Format only allowlisted fields; never serialize request/response bodies."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "level": record.levelname,
            "message": record.getMessage(),
            "event": getattr(record, "event", "application_log"),
            "release_version": getattr(record, "release_version", "unknown"),
            "request_id": getattr(record, "request_id", None),
            "route_class": getattr(record, "route_class", None),
            "status_code": getattr(record, "status_code", None),
            "latency_ms": getattr(record, "latency_ms", None),
            "error_code": getattr(record, "error_code", None),
        }
        return json.dumps({key: value for key, value in data.items() if value is not None})


def configure_observability(settings: Settings) -> None:
    if any(isinstance(handler.formatter, SafeJsonFormatter) for handler in LOGGER.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    LOGGER.info(
        "observability_configured",
        extra={"event": "observability_configured", "release_version": settings.release_version},
    )


@dataclass
class OperationalMetrics:
    _lock: Lock = field(default_factory=Lock)
    requests: Counter[str] = field(default_factory=Counter)
    errors: Counter[str] = field(default_factory=Counter)
    latency_total_ms: Counter[str] = field(default_factory=Counter)

    def record(self, route_class: str, status_code: int, latency_ms: int) -> None:
        with self._lock:
            self.requests[route_class] += 1
            self.latency_total_ms[route_class] += latency_ms
            if status_code >= 500:
                self.errors[route_class] += 1

    def snapshot(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {
                route: {
                    "requests": self.requests[route],
                    "server_errors": self.errors[route],
                    "latency_total_ms": self.latency_total_ms[route],
                }
                for route in sorted(self.requests)
            }


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, settings: Settings, metrics: OperationalMetrics) -> None:
        super().__init__(app)
        self.settings = settings
        self.metrics = metrics

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", "")
        if not TRACE_ID.fullmatch(request_id):
            request_id = uuid.uuid4().hex
        route_class = self._route_class(request.url.path)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            latency_ms = int((time.perf_counter() - started) * 1000)
            self.metrics.record(route_class, 500, latency_ms)
            LOGGER.exception(
                "request_failed",
                extra={
                    "event": "request_failed",
                    "release_version": self.settings.release_version,
                    "request_id": request_id,
                    "route_class": route_class,
                    "status_code": 500,
                    "latency_ms": latency_ms,
                    "error_code": "unhandled_exception",
                },
            )
            raise
        latency_ms = int((time.perf_counter() - started) * 1000)
        self.metrics.record(route_class, response.status_code, latency_ms)
        response.headers["X-Request-ID"] = request_id
        LOGGER.info(
            "request_completed",
            extra={
                "event": "request_completed",
                "release_version": self.settings.release_version,
                "request_id": request_id,
                "route_class": route_class,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "error_code": self._safe_error_code(response.status_code),
            },
        )
        return response

    @staticmethod
    def _route_class(path: str) -> str:
        if path.startswith("/api/v1/auth"):
            return "auth"
        if path.startswith("/api/v1/document-lab"):
            return "document_lab"
        if path.startswith("/api/v1/community"):
            return "community"
        if path.startswith("/api/v1/assistant"):
            return "assistant"
        if path.startswith("/api/v1/applications"):
            return "applications"
        if path.startswith("/api/v1"):
            return "api"
        if path.startswith("/health"):
            return "health"
        return "frontend"

    @staticmethod
    def _safe_error_code(status_code: int) -> str | None:
        if status_code >= 500:
            return "server_error"
        if status_code >= 400:
            return "client_error"
        return None
