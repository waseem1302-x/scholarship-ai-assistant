"""Composition root for HTTP middleware and its ordering contract."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import Settings
from app.core.feature_gates import FeatureGateMiddleware
from app.core.http_security import SecurityHeadersMiddleware
from app.core.observability import (
    ObservabilityMiddleware,
    OperationalMetrics,
    configure_observability,
)
from app.core.proxy_headers import AzureContainerAppsProxyHeadersMiddleware
from app.core.rate_limit import AuthRateLimitMiddleware


def configure_http_middleware(application: FastAPI, settings: Settings) -> None:
    """Register middleware in a deliberate outer-to-inner execution order.

    ``add_middleware`` prepends each entry, so the trusted proxy adapter must
    be added last. This ensures every inner layer sees only trusted forwarded
    client and scheme values. Security headers wrap telemetry, limits, gates,
    and CORS so error responses receive the same browser protections.
    """
    configure_observability(settings)
    application.state.metrics = OperationalMetrics()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Admin-Step-Up",
            "X-CSRF-Token",
            "X-Document-Filename",
        ],
    )
    application.add_middleware(FeatureGateMiddleware, settings=settings)
    application.add_middleware(AuthRateLimitMiddleware, settings=settings)
    application.add_middleware(
        ObservabilityMiddleware, settings=settings, metrics=application.state.metrics
    )
    application.add_middleware(SecurityHeadersMiddleware, settings=settings)

    if settings.trusted_proxy_mode == "azure-container-apps":
        application.add_middleware(AzureContainerAppsProxyHeadersMiddleware)
    elif settings.trusted_proxy_ip_list:
        application.add_middleware(
            ProxyHeadersMiddleware,
            trusted_hosts=settings.trusted_proxy_ip_list,
        )
