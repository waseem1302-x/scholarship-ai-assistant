from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.db.session import get_db


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
        allow_headers=["Authorization", "Content-Type"],
    )
    install_error_handlers(application)
    application.include_router(api_router, prefix="/api/v1")

    @application.get("/", include_in_schema=False)
    def documentation_redirect() -> RedirectResponse:
        return RedirectResponse(url="/docs", status_code=307)

    @application.get("/health/live", tags=["operations"])
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready", tags=["operations"])
    def readiness(session: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
        session.execute(text("SELECT 1"))
        return {"status": "ready"}

    return application


app = create_app()
