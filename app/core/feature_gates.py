"""Server-side Phase 9 capability gates and immediate kill switches."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import Settings


class FeatureGateMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:
        if self.settings.env == "test":
            return await call_next(request)
        path = request.url.path
        code: str | None = None
        message: str | None = None
        if path == "/api/v1/assistant/answers" and not self.settings.assistant_enabled:
            code, message = "assistant_unavailable", "The assistant is temporarily unavailable."
        elif path.startswith("/api/v1/document-lab/") and not self.settings.document_lab_enabled:
            # Preserve the policy endpoint so the client can show an accurate,
            # non-sensitive unavailable state. Privacy export/deletion remains
            # available after a kill switch is activated.
            if path not in {
                "/api/v1/document-lab/policy",
                "/api/v1/document-lab/export",
                "/api/v1/document-lab/data",
            }:
                code = "document_lab_unavailable"
                message = "Document Lab is temporarily unavailable."
        elif path.startswith("/api/v1/community/") and not self.settings.community_enabled:
            # A kill switch cannot remove export or erasure rights. Those
            # routes do not expose other members' content and remain owner
            # scoped by the service layer.
            if path not in {"/api/v1/community/export", "/api/v1/community/data"}:
                code, message = "community_unavailable", "Community is temporarily unavailable."
        elif (
            self.settings.catalogue_maintenance_mode
            and request.method in {"POST", "PATCH", "PUT", "DELETE"}
            and (
                path.startswith("/api/v1/admin/")
                or path.startswith("/api/v1/applications/")
                or path.startswith("/api/v1/profiles/")
                or path.startswith("/api/v1/matches/")
            )
        ):
            code, message = "maintenance_mode", "This workspace is temporarily read-only."
        if code:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": code, "message": message}},
            )
        return await call_next(request)
