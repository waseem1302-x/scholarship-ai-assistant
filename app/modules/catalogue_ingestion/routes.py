"""Administrator visibility, review, and publication actions for catalogue ingestion."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.modules.auth.dependencies import require_admin_step_up, require_roles
from app.modules.auth.models import User, UserRole
from app.modules.catalogue_ingestion.extraction_preflight import (
    build_candidate_extraction_preflight,
)
from app.modules.catalogue_ingestion.models import CandidateStatus
from app.modules.catalogue_ingestion.production_service import ProductionCatalogueIngestionService
from app.modules.catalogue_ingestion.review_schemas import (
    CatalogueCandidateReviewResponse,
    CatalogueProposalReasonRequest,
    CatalogueProposalVersionRequest,
    CataloguePublicationReadinessResponse,
)
from app.modules.catalogue_ingestion.review_workflow import CatalogueReviewWorkflow
from app.modules.catalogue_ingestion.schemas import (
    CandidateExtractionPlanResponse,
    CandidateListResponse,
    CandidateResponse,
    CandidateRetryRequest,
    CandidateSubmitRequest,
    DirectUrlIngestionRequest,
    IngestionRunListResponse,
    IngestionRunResponse,
)
from app.modules.catalogue_ingestion.service import CatalogueIngestionService

router = APIRouter(prefix="/admin/catalogue-ingestion", tags=["catalogue-ingestion"])
AdminReader = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
AdminUser = Annotated[User, Depends(require_admin_step_up)]


def get_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProductionCatalogueIngestionService:
    return ProductionCatalogueIngestionService(session, settings)


def get_review_workflow(
    session: Annotated[Session, Depends(get_db)],
) -> CatalogueReviewWorkflow:
    return CatalogueReviewWorkflow(session)


@router.post("/runs/url", response_model=IngestionRunResponse)
def create_url_run(
    payload: DirectUrlIngestionRequest,
    _admin: AdminUser,
    service: Annotated[CatalogueIngestionService, Depends(get_service)],
) -> IngestionRunResponse:
    run = service.create_run_from_url(
        str(payload.url),
        mode=payload.mode,
        dry_run=payload.dry_run,
        supporting_urls=[str(item) for item in payload.supporting_urls],
        target_name=payload.target_name,
        provider=payload.provider,
        university=payload.university,
        country=payload.country,
    )
    if payload.process_now:
        return service.process_run(run.id, worker_id=f"admin-api:{run.id}", batch_size=1)
    return run


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


@router.get(
    "/candidates/{candidate_id}/extraction-plan",
    response_model=CandidateExtractionPlanResponse,
)
def extraction_plan(
    candidate_id: uuid.UUID,
    _admin: AdminReader,
    service: Annotated[ProductionCatalogueIngestionService, Depends(get_service)],
) -> CandidateExtractionPlanResponse:
    return build_candidate_extraction_preflight(service, candidate_id)


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
    workflow: Annotated[CatalogueReviewWorkflow, Depends(get_review_workflow)],
) -> CandidateResponse:
    # Preserve the existing endpoint/response contract while routing rich and legacy proposals
    # through the durable review state machine instead of the old MEXT compatibility blocker.
    workflow.submit(candidate_id, notes=payload.notes, actor=admin)
    return service.candidate(candidate_id)


@router.get(
    "/candidates/{candidate_id}/review",
    response_model=CatalogueCandidateReviewResponse,
)
def get_candidate_review(
    candidate_id: uuid.UUID,
    _admin: AdminReader,
    workflow: Annotated[CatalogueReviewWorkflow, Depends(get_review_workflow)],
) -> CatalogueCandidateReviewResponse:
    return workflow.review(candidate_id)


@router.post(
    "/candidates/{candidate_id}/review/approve",
    response_model=CatalogueCandidateReviewResponse,
)
def approve_candidate_proposal(
    candidate_id: uuid.UUID,
    payload: CatalogueProposalVersionRequest,
    admin: AdminUser,
    workflow: Annotated[CatalogueReviewWorkflow, Depends(get_review_workflow)],
) -> CatalogueCandidateReviewResponse:
    return workflow.approve(
        candidate_id,
        expected_proposal_hash=payload.expected_proposal_hash,
        notes=payload.notes,
        actor=admin,
    )


@router.post(
    "/candidates/{candidate_id}/review/reject",
    response_model=CatalogueCandidateReviewResponse,
)
def reject_candidate_proposal(
    candidate_id: uuid.UUID,
    payload: CatalogueProposalReasonRequest,
    admin: AdminUser,
    workflow: Annotated[CatalogueReviewWorkflow, Depends(get_review_workflow)],
) -> CatalogueCandidateReviewResponse:
    return workflow.reject(
        candidate_id,
        expected_proposal_hash=payload.expected_proposal_hash,
        reason=payload.reason,
        actor=admin,
    )


@router.post(
    "/candidates/{candidate_id}/review/request-changes",
    response_model=CatalogueCandidateReviewResponse,
)
def request_candidate_proposal_changes(
    candidate_id: uuid.UUID,
    payload: CatalogueProposalReasonRequest,
    admin: AdminUser,
    workflow: Annotated[CatalogueReviewWorkflow, Depends(get_review_workflow)],
) -> CatalogueCandidateReviewResponse:
    return workflow.request_changes(
        candidate_id,
        expected_proposal_hash=payload.expected_proposal_hash,
        reason=payload.reason,
        actor=admin,
    )


@router.post(
    "/candidates/{candidate_id}/review/retry-materialization",
    response_model=CatalogueCandidateReviewResponse,
)
def retry_candidate_materialization(
    candidate_id: uuid.UUID,
    payload: CatalogueProposalVersionRequest,
    admin: AdminUser,
    workflow: Annotated[CatalogueReviewWorkflow, Depends(get_review_workflow)],
) -> CatalogueCandidateReviewResponse:
    return workflow.retry_materialization(
        candidate_id,
        expected_proposal_hash=payload.expected_proposal_hash,
        actor=admin,
    )


@router.get(
    "/candidates/{candidate_id}/review/publication-readiness",
    response_model=CataloguePublicationReadinessResponse,
)
def candidate_publication_readiness(
    candidate_id: uuid.UUID,
    _admin: AdminReader,
    workflow: Annotated[CatalogueReviewWorkflow, Depends(get_review_workflow)],
) -> CataloguePublicationReadinessResponse:
    return workflow.publication_readiness(candidate_id)


@router.post(
    "/candidates/{candidate_id}/review/mark-publication-ready",
    response_model=CatalogueCandidateReviewResponse,
)
def mark_candidate_publication_ready(
    candidate_id: uuid.UUID,
    payload: CatalogueProposalVersionRequest,
    admin: AdminUser,
    workflow: Annotated[CatalogueReviewWorkflow, Depends(get_review_workflow)],
) -> CatalogueCandidateReviewResponse:
    return workflow.mark_publication_ready(
        candidate_id,
        expected_proposal_hash=payload.expected_proposal_hash,
        actor=admin,
    )


@router.post(
    "/candidates/{candidate_id}/review/publish",
    response_model=CatalogueCandidateReviewResponse,
)
def publish_candidate_proposal(
    candidate_id: uuid.UUID,
    payload: CatalogueProposalVersionRequest,
    admin: AdminUser,
    workflow: Annotated[CatalogueReviewWorkflow, Depends(get_review_workflow)],
) -> CatalogueCandidateReviewResponse:
    return workflow.publish(
        candidate_id,
        expected_proposal_hash=payload.expected_proposal_hash,
        notes=payload.notes,
        actor=admin,
    )
