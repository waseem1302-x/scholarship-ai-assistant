import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import require_roles, require_verified_student
from app.modules.auth.models import User, UserRole
from app.modules.document_lab.models import DocumentKind
from app.modules.document_lab.schemas import (
    AnalysisCreateRequest,
    ApplicationDocumentLinkRequest,
    ApplicationDocumentLinkResponse,
    DocumentAnalysisResponse,
    DocumentAssetResponse,
    DocumentExportResponse,
    DocumentLabPolicyResponse,
    DocumentVersionResponse,
)
from app.modules.document_lab.service import DocumentLabService, document_intake_readiness

router = APIRouter(prefix="/document-lab", tags=["private document lab"])
StudentUser = Annotated[User, Depends(require_roles(UserRole.STUDENT))]
VerifiedStudentUser = Annotated[User, Depends(require_verified_student)]
Errors = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


def get_document_lab_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentLabService:
    return DocumentLabService(session, settings)


DocumentService = Annotated[DocumentLabService, Depends(get_document_lab_service)]


@router.get(
    "/policy",
    response_model=DocumentLabPolicyResponse,
    responses={401: {"model": ErrorResponse}},
)
def policy(
    _: StudentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db)],
) -> DocumentLabPolicyResponse:
    scanner_ready, worker_ready, accepting_uploads = document_intake_readiness(session, settings)
    return DocumentLabPolicyResponse(
        enabled=accepting_uploads,
        feature_enabled=settings.document_lab_enabled,
        accepting_uploads=accepting_uploads,
        scanner_ready=scanner_ready,
        worker_ready=worker_ready,
        analysis_provider_ready=settings.document_lab_provider != "unavailable",
        supported_types=[item.value for item in DocumentKind],
        max_upload_bytes=settings.document_lab_max_upload_bytes,
        max_pages=settings.document_lab_max_pages,
        max_extracted_characters=settings.document_lab_max_extracted_characters,
        retention_days=settings.document_lab_retention_days,
        notice_version=settings.document_lab_notice_version,
        data_use_notice=(
            "Your file remains private. Before each analysis, you must explicitly agree "
            "to send extracted text to the configured AI provider. Feedback is editorial "
            "guidance, not an eligibility, admission, funding, visa, plagiarism, "
            "or authorship decision."
        ),
    )


@router.post(
    "/assets",
    response_model=DocumentAssetResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=Errors,
)
async def upload_asset(
    request: Request,
    document_kind: Annotated[DocumentKind, Query()],
    user: VerifiedStudentUser,
    service: DocumentService,
    filename: Annotated[str, Header(alias="X-Document-Filename")],
    declared_content_type: Annotated[str, Header(alias="Content-Type")],
) -> DocumentAssetResponse:
    return service.create_asset(
        user=user,
        document_kind=document_kind,
        filename=filename,
        declared_content_type=declared_content_type,
        content=await _read_upload(request, service.settings.document_lab_max_upload_bytes),
    )


@router.post(
    "/assets/{asset_id}/versions",
    response_model=DocumentAssetResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=Errors,
)
async def upload_version(
    asset_id: uuid.UUID,
    request: Request,
    user: VerifiedStudentUser,
    service: DocumentService,
    filename: Annotated[str, Header(alias="X-Document-Filename")],
    declared_content_type: Annotated[str, Header(alias="Content-Type")],
) -> DocumentAssetResponse:
    return service.add_version(
        asset_id=asset_id,
        user=user,
        filename=filename,
        declared_content_type=declared_content_type,
        content=await _read_upload(request, service.settings.document_lab_max_upload_bytes),
    )


@router.get("/assets", response_model=list[DocumentAssetResponse], responses=Errors)
def list_assets(user: StudentUser, service: DocumentService) -> list[DocumentAssetResponse]:
    return service.list_assets(user.id)


@router.get(
    "/assets/{asset_id}",
    response_model=DocumentAssetResponse,
    responses=Errors,
)
def get_asset(
    asset_id: uuid.UUID, user: StudentUser, service: DocumentService
) -> DocumentAssetResponse:
    return service.get_asset(asset_id, user.id)


@router.get("/versions/{version_id}/download", responses=Errors)
def download_version(
    version_id: uuid.UUID, user: StudentUser, service: DocumentService
) -> Response:
    content, content_type = service.download_version(version_id, user.id)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": "attachment; filename=private-document"},
    )


@router.post(
    "/versions/{version_id}/retry",
    response_model=DocumentVersionResponse,
    responses=Errors,
)
def retry_version(
    version_id: uuid.UUID, user: VerifiedStudentUser, service: DocumentService
) -> DocumentVersionResponse:
    return service.retry_preparation(version_id, user.id)


@router.delete(
    "/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=Errors,
)
def delete_asset(asset_id: uuid.UUID, user: StudentUser, service: DocumentService) -> Response:
    service.delete_asset(asset_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/versions/{version_id}/analyses",
    response_model=DocumentAnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=Errors,
)
def create_analysis(
    version_id: uuid.UUID,
    payload: AnalysisCreateRequest,
    user: VerifiedStudentUser,
    service: DocumentService,
) -> DocumentAnalysisResponse:
    return service.request_analysis(
        version_id=version_id,
        user=user,
        analysis_type=payload.analysis_type,
        consent=payload.consent,
        notice_version=payload.notice_version,
    )


@router.get(
    "/analyses/{analysis_id}",
    response_model=DocumentAnalysisResponse,
    responses=Errors,
)
def get_analysis(
    analysis_id: uuid.UUID, user: StudentUser, service: DocumentService
) -> DocumentAnalysisResponse:
    return service.get_analysis(analysis_id, user.id)


@router.get(
    "/versions/{version_id}/analyses",
    response_model=list[DocumentAnalysisResponse],
    responses=Errors,
)
def list_version_analyses(
    version_id: uuid.UUID, user: StudentUser, service: DocumentService
) -> list[DocumentAnalysisResponse]:
    return service.list_version_analyses(version_id, user.id)


@router.get("/export", response_model=DocumentExportResponse, responses=Errors)
def export_data(user: StudentUser, service: DocumentService) -> DocumentExportResponse:
    return service.export_data(user.id)


@router.delete("/data", status_code=status.HTTP_204_NO_CONTENT, responses=Errors)
def delete_data(user: StudentUser, service: DocumentService) -> Response:
    service.delete_all_data(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/application-documents/{application_document_id}/link",
    response_model=ApplicationDocumentLinkResponse,
    responses=Errors,
)
def link_application_document(
    application_document_id: uuid.UUID,
    payload: ApplicationDocumentLinkRequest,
    user: VerifiedStudentUser,
    service: DocumentService,
) -> ApplicationDocumentLinkResponse:
    return service.link_application_document(
        application_document_id=application_document_id,
        version_id=payload.version_id,
        user_id=user.id,
        confirmed=payload.confirmed,
    )


async def _read_upload(request: Request, maximum: int) -> bytes:
    declared_size = request.headers.get("content-length")
    if declared_size and declared_size.isdigit() and int(declared_size) > maximum:
        raise AppError("file_too_large", "The uploaded file cannot be accepted.", 422)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > maximum:
            raise AppError("file_too_large", "The uploaded file cannot be accepted.", 422)
    return bytes(content)
