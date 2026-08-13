from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.health import register_health_routes
from app.core.middleware import configure_http_middleware

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
    application.state.settings = settings
    configure_http_middleware(application, settings)

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

    register_health_routes(application, settings)

    @application.get("/", include_in_schema=False)
    def frontend() -> Response:
        return frontend_response()

    @application.get("/{path:path}", include_in_schema=False)
    def frontend_route(path: str) -> Response:
        return frontend_response()

    return application


app = create_app()
