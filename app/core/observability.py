"""Privacy-safe request correlation and cross-replica operational telemetry."""

import json
import logging
import os
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import Settings

LOGGER = logging.getLogger("scholarship.operations")
TRACE_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_AZURE_MONITOR_CONFIGURED = False


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
    """Configure structured logs and the production OpenTelemetry exporter.

    In-memory counters remain available for local/test diagnostics only. A
    production deployment uses Azure Monitor OpenTelemetry so metrics from all
    Container Apps replicas are aggregated in the same backend.
    """

    if not any(isinstance(handler.formatter, SafeJsonFormatter) for handler in LOGGER.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(SafeJsonFormatter())
        LOGGER.addHandler(handler)
        LOGGER.setLevel(logging.INFO)
        LOGGER.propagate = False

    if settings.metrics_backend == "external":
        _configure_azure_monitor(settings)

    LOGGER.info(
        "observability_configured",
        extra={"event": "observability_configured", "release_version": settings.release_version},
    )


def _configure_azure_monitor(settings: Settings) -> None:
    global _AZURE_MONITOR_CONFIGURED
    if _AZURE_MONITOR_CONFIGURED:
        return
    if not os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip():
        raise RuntimeError(
            "APPLICATIONINSIGHTS_CONNECTION_STRING is required when APP_METRICS_BACKEND=external"
        )
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError as exc:  # fail closed rather than silently falling back per replica
        raise RuntimeError("Azure Monitor OpenTelemetry dependency is unavailable") from exc

    configure_azure_monitor(
        logger_name=LOGGER.name,
        enable_trace_based_sampling_for_logs=True,
    )
    _AZURE_MONITOR_CONFIGURED = True


@dataclass
class OperationalMetrics:
    """Bounded local diagnostics plus low-cardinality OpenTelemetry metrics."""

    external_enabled: bool = False
    LATENCY_BUCKETS_MS = (50, 100, 250, 500, 1000, 2500, 5000)

    _lock: Lock = field(default_factory=Lock)
    requests: Counter[str] = field(default_factory=Counter)
    errors: Counter[str] = field(default_factory=Counter)
    latency_total_ms: Counter[str] = field(default_factory=Counter)
    latency_buckets: Counter[tuple[str, str]] = field(default_factory=Counter)
    _request_counter: Any = field(init=False, default=None, repr=False)
    _error_counter: Any = field(init=False, default=None, repr=False)
    _latency_histogram: Any = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.external_enabled:
            return
        try:
            from opentelemetry import metrics
        except ImportError as exc:
            raise RuntimeError("OpenTelemetry metrics API is unavailable") from exc
        meter = metrics.get_meter("scholarship.platform.http", "1.0")
        self._request_counter = meter.create_counter(
            "scholarship.http.requests",
            unit="{request}",
            description="HTTP requests handled by the scholarship platform",
        )
        self._error_counter = meter.create_counter(
            "scholarship.http.server_errors",
            unit="{error}",
            description="HTTP 5xx responses handled by the scholarship platform",
        )
        self._latency_histogram = meter.create_histogram(
            "scholarship.http.server_latency",
            unit="ms",
            description="Server-side request latency in milliseconds",
        )

    def record(self, route_class: str, status_code: int, latency_ms: int) -> None:
        with self._lock:
            self.requests[route_class] += 1
            self.latency_total_ms[route_class] += latency_ms
            bucket = self._latency_bucket(latency_ms)
            self.latency_buckets[(route_class, bucket)] += 1
            if status_code >= 500:
                self.errors[route_class] += 1

        if self.external_enabled:
            attributes = {
                "route.class": route_class,
                "http.status_family": f"{status_code // 100}xx",
            }
            self._request_counter.add(1, attributes)
            self._latency_histogram.record(latency_ms, attributes)
            if status_code >= 500:
                self._error_counter.add(1, attributes)

    def snapshot(self) -> dict[str, dict[str, int | dict[str, int]]]:
        """Return local per-process diagnostics; never use this as fleet totals."""

        with self._lock:
            return {
                route: {
                    "requests": self.requests[route],
                    "server_errors": self.errors[route],
                    "latency_total_ms": self.latency_total_ms[route],
                    "latency_buckets_ms": {
                        bucket: self.latency_buckets[(route, bucket)]
                        for bucket in self._bucket_labels()
                    },
                }
                for route in sorted(self.requests)
            }

    @classmethod
    def _latency_bucket(cls, latency_ms: int) -> str:
        for bucket in cls.LATENCY_BUCKETS_MS:
            if latency_ms <= bucket:
                return f"le_{bucket}"
        return "gt_5000"

    @classmethod
    def _bucket_labels(cls) -> list[str]:
        return [f"le_{bucket}" for bucket in cls.LATENCY_BUCKETS_MS] + ["gt_5000"]


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
