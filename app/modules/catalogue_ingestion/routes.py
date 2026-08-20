"""Minimal administrator visibility and handoff actions for staged catalogue candidates."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.modules.auth.dependencies import require_admin_step_up, require_roles
from app.modules.auth.models import User, UserRole
from app.modules.catalogue_ingestion.models import CandidateStatus
from app.modules.catalogue_ingestion.schemas import (
    CandidateListResponse,
    CandidateResponse,
    CandidateRetryRequest,
    CandidateSubmitRequest,
    IngestionRunListResponse,
)
from app.modules.catalogue_ingestion.service import CatalogueIngestionService

router = APIRouter(prefix="/admin/catalogue-ingestion", tags=["catalogue-ingestion"])
AdminReader = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
AdminUser = Annotated[User, Depends(require_admin_step_up)]


def get_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CatalogueIngestionService:
    return CatalogueIngestionService(session, settings)


@router.get("/runs", response_model=IngestionRunListResponse)
def list_runs(
    _admin: AdminReader,
    service: Annotated[CatalogueIngestionService, Depends(get_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IngestionRunListResponse:
    return service.list_runs(limit=limit, offset=offset)


@router.get("/candidates", response_model=CandidateListResponse)
def list_candidates(
    _admin: AdminReader,
    service: Annotated[CatalogueIngestionService, Depends(get_service)],
    status: CandidateStatus | None = None,
    run_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CandidateListResponse:
    return service.list_candidates(status=status, run_id=run_id, limit=limit, offset=offset)


@router.get("/candidates/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: uuid.UUID,
    _admin: AdminReader,
    service: Annotated[CatalogueIngestionService, Depends(get_service)],
) -> CandidateResponse:
    return service.candidate(candidate_id)


@router.post("/candidates/{candidate_id}/retry", response_model=CandidateResponse)
def retry_candidate(
    candidate_id: uuid.UUID,
    payload: CandidateRetryRequest,
    admin: AdminUser,
    service: Annotated[CatalogueIngestionService, Depends(get_service)],
) -> CandidateResponse:
    return service.retry_candidate(candidate_id, reason=payload.reason, actor=admin)


@router.post("/candidates/{candidate_id}/submit-for-review", response_model=CandidateResponse)
def submit_candidate(
    candidate_id: uuid.UUID,
    payload: CandidateSubmitRequest,
    admin: AdminUser,
    service: Annotated[CatalogueIngestionService, Depends(get_service)],
) -> CandidateResponse:
    return service.submit_candidate(candidate_id, notes=payload.notes, actor=admin)
