from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.rate_limit import AuthRateLimitMiddleware
from app.db.session import get_db
from app.modules.applications.models import ReminderWorkerHealth

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
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Admin-Step-Up", "X-CSRF-Token"],
    )
    application.add_middleware(AuthRateLimitMiddleware)

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
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

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
    def readiness(session: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
        session.execute(text("SELECT 1"))
        return {"status": "ready"}

    @application.get("/health/reminders", tags=["operations"])
    def reminder_worker_readiness(session: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
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
                status.HTTP_503_SERVICE_UNAVAILABLE, "Reminder worker is not healthy"
            )
        return {"status": "ready" if is_current else "not_running"}

    @application.get("/", include_in_schema=False)
    def frontend() -> Response:
        return frontend_response()

    @application.get("/{path:path}", include_in_schema=False)
    def frontend_route(path: str) -> Response:
        return frontend_response()

    return application


app = create_app()
