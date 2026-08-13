from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.feature_gates import FeatureGateMiddleware
from app.core.observability import (
    ObservabilityMiddleware,
    OperationalMetrics,
    configure_observability,
)
from app.core.proxy_headers import AzureContainerAppsProxyHeadersMiddleware
from app.core.rate_limit import AuthRateLimitMiddleware
from app.db.session import get_db
from app.modules.applications.models import ReminderWorkerHealth
from app.modules.operations.models import OperationalJobHealth

FRONTEND_DIRECTORY = Path("app/web/frontend-dist")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Schema changes are deliberately handled by Alembic, never create_all().
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.name,
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )
    configure_observability(settings)
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
    application.state.settings = settings
    application.state.metrics = OperationalMetrics()
    application.add_middleware(FeatureGateMiddleware, settings=settings)
    application.add_middleware(AuthRateLimitMiddleware, settings=settings)
    application.add_middleware(
        ObservabilityMiddleware, settings=settings, metrics=application.state.metrics
    )

    @application.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
            "img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if settings.env == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    if settings.trusted_proxy_mode == "azure-container-apps":
        application.add_middleware(AzureContainerAppsProxyHeadersMiddleware)
    elif settings.trusted_proxy_ip_list:
        # Add last so it is the ASGI outer edge: all inner rate-limit,
        # observability, and application middleware see forwarded values only
        # when they came from the configured TLS proxy.
        application.add_middleware(
            ProxyHeadersMiddleware,
            trusted_hosts=settings.trusted_proxy_ip_list,
        )

    install_error_handlers(application)
    application.include_router(api_router, prefix="/api/v1")
    application.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIRECTORY / "assets", check_dir=False),
        name="frontend-assets",
    )

    @application.get("/app", include_in_schema=False)
    @application.get("/app/{path:path}", include_in_schema=False)
    def redirect_legacy_frontend(request: Request, path: str = "") -> RedirectResponse:
        target = f"/{path}"
        if request.url.query:
            target = f"{target}?{request.url.query}"
        return RedirectResponse(target, status_code=308)

    def frontend_response() -> Response:
        index = FRONTEND_DIRECTORY / "index.html"
        if not index.is_file():
            return PlainTextResponse(
                "The frontend has not been built. Run `pnpm --dir frontend build` first.",
                status_code=503,
            )
        return FileResponse(index)

    @application.get("/health/live", tags=["operations"])
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready", tags=["operations"])
    def readiness(
        session: Annotated[Session, Depends(get_db)],
    ) -> dict[str, str]:
        session.execute(text("SELECT 1"))
        return {"status": "ready"}

    @application.get("/health/reminders", tags=["operations"])
    def reminder_worker_readiness(
        session: Annotated[Session, Depends(get_db)],
    ) -> dict[str, str]:
        health = session.get(ReminderWorkerHealth, "default")
        completed = health.last_completed_at if health else None
        completed_utc = (
            completed.replace(tzinfo=UTC) if completed and completed.tzinfo is None else completed
        )
        is_current = bool(
            completed_utc and completed_utc >= datetime.now(UTC) - timedelta(minutes=5)
        )
        if settings.reminder_worker_required and not is_current:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Reminder worker is not healthy",
            )
        return {"status": "ready" if is_current else "not_running"}

    @application.get("/health/operations", tags=["operations"])
    def operational_health(
        request: Request,
        session: Annotated[Session, Depends(get_db)],
    ) -> dict[str, object]:
        # The middleware instance is not a public FastAPI API. Store health is
        # available from the configured factory without emitting its URL.
        from app.core.email import get_account_email_sender
        from app.core.rate_limit import create_rate_limit_store

        rate_limit_store_healthy = create_rate_limit_store(settings).health()
        # This probe authenticates but never sends mail or exposes the SMTP
        # endpoint/credentials. It lets alerting distinguish a degraded
        # account-recovery path from a full API outage.
        account_email_healthy = get_account_email_sender(settings).health()
        now = datetime.now(UTC)
        jobs = {}
        for job in session.scalars(select(OperationalJobHealth)).all():
            completed = job.last_completed_at
            completed_utc = (
                completed.replace(tzinfo=UTC)
                if completed and completed.tzinfo is None
                else completed
            )
            jobs[job.job_name] = {
                "status": (
                    "fresh"
                    if completed_utc
                    and completed_utc
                    >= now - timedelta(minutes=settings.operational_job_stale_minutes)
                    else "stale"
                ),
                "last_completed_at": completed_utc.isoformat() if completed_utc else None,
                "processed_count": job.processed_count,
                "failed_count": job.failed_count,
                "last_error_code": job.last_error_code,
            }
        return {
            "release_version": settings.release_version,
            "rate_limit_store_healthy": rate_limit_store_healthy,
            "account_email_healthy": account_email_healthy,
            "metrics": request.app.state.metrics.snapshot(),
            "jobs": jobs,
        }

    @application.get("/", include_in_schema=False)
    def frontend() -> Response:
        return frontend_response()

    @application.get("/{path:path}", include_in_schema=False)
    def frontend_route(path: str) -> Response:
        return frontend_response()

    return application


app = create_app()
