import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import require_admin_step_up
from app.modules.auth.models import User
from app.modules.opportunities.models import (
    DegreeLevel,
    FundingType,
    OpportunityStatus,
    VerificationStatus,
)
from app.modules.opportunities.schemas import (
    AdminOpportunityResponse,
    AdminOpportunitySearchResponse,
    DataQualityIssueSearchResponse,
    OpportunityCreate,
    OpportunityDetailResponse,
    OpportunityImportRequest,
    OpportunityImportResponse,
    OpportunitySearchResponse,
    ReviewActionRequest,
    ReviewQueueResponse,
    SourceCheckRequest,
    SourceCheckResponse,
    VerificationUpdate,
)
from app.modules.opportunities.service import OpportunityService

router = APIRouter(tags=["opportunities"])

VALIDATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "The request parameters or body failed validation.",
}
AUTHENTICATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "Authentication is required.",
}
FORBIDDEN_RESPONSE = {
    "model": ErrorResponse,
    "description": "The authenticated user does not have administrator access.",
}
NOT_FOUND_RESPONSE = {"model": ErrorResponse, "description": "The opportunity was not found."}
CONFLICT_RESPONSE = {
    "model": ErrorResponse,
    "description": "A duplicate opportunity already exists.",
}


def get_opportunity_service(session: Annotated[Session, Depends(get_db)]) -> OpportunityService:
    return OpportunityService(session)


AdminUser = Annotated[User, Depends(require_admin_step_up)]


@router.post(
    "/admin/opportunities",
    response_model=AdminOpportunityResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        409: CONFLICT_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def create_opportunity(
    payload: OpportunityCreate,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> AdminOpportunityResponse:
    return service.create_opportunity(payload, created_by=admin)


@router.get(
    "/admin/opportunities",
    response_model=AdminOpportunitySearchResponse,
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE},
)
def list_admin_opportunities(
    _admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
    country: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    degree_level: DegreeLevel | None = None,
    status: OpportunityStatus | None = None,
    verification_status: VerificationStatus | None = None,
    needs_review: bool | None = None,
    provider_query: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    search_query: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    deadline_after: datetime | None = None,
    deadline_before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminOpportunitySearchResponse:
    return service.list_admin_opportunities(
        country=country,
        degree_level=degree_level,
        status=status,
        verification_status=verification_status,
        needs_review=needs_review,
        provider_query=provider_query,
        search_query=search_query,
        deadline_after=deadline_after,
        deadline_before=deadline_before,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/review-queue",
    response_model=ReviewQueueResponse,
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE},
)
def list_review_queue(
    _admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewQueueResponse:
    return service.list_review_queue(limit=limit, offset=offset)


@router.get(
    "/admin/data-quality-issues",
    response_model=DataQualityIssueSearchResponse,
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE},
)
def list_data_quality_issues(
    _admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DataQualityIssueSearchResponse:
    return service.list_data_quality_issues(limit=limit, offset=offset)


@router.post(
    "/admin/opportunities/import",
    response_model=OpportunityImportResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def import_opportunities(
    payload: OpportunityImportRequest,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> OpportunityImportResponse:
    return service.import_opportunities(payload, created_by=admin)


@router.post(
    "/admin/opportunities/{opportunity_id}/review-actions",
    response_model=AdminOpportunityResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def apply_review_action(
    opportunity_id: uuid.UUID,
    payload: ReviewActionRequest,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> AdminOpportunityResponse:
    return service.apply_review_action(opportunity_id, payload, reviewed_by=admin)


@router.post(
    "/admin/sources/{source_id}/checks",
    response_model=SourceCheckResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def record_source_check(
    source_id: uuid.UUID,
    payload: SourceCheckRequest,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> SourceCheckResponse:
    return service.record_source_check(source_id, payload, checked_by=admin)


@router.patch(
    "/admin/opportunities/{opportunity_id}/verification",
    response_model=AdminOpportunityResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def update_verification(
    opportunity_id: uuid.UUID,
    payload: VerificationUpdate,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> AdminOpportunityResponse:
    return service.verify_source(opportunity_id, payload, checked_by=admin)


@router.get(
    "/opportunities",
    response_model=OpportunitySearchResponse,
    responses={422: VALIDATION_RESPONSE},
)
def search_opportunities(
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
    country: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    degree_level: DegreeLevel | None = None,
    funding_type: FundingType | None = None,
    field: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    nationality: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    intake_year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    deadline_after: datetime | None = None,
    deadline_before: datetime | None = None,
    funding_coverage: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    application_fee: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    english_requirement: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    verified_after: datetime | None = None,
    open_now: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OpportunitySearchResponse:
    return service.list_public_opportunities(
        country=country,
        degree_level=degree_level,
        funding_type=funding_type,
        field=field,
        nationality=nationality,
        intake_year=intake_year,
        deadline_after=deadline_after,
        deadline_before=deadline_before,
        funding_coverage=funding_coverage,
        application_fee=application_fee,
        english_requirement=english_requirement,
        verified_after=verified_after,
        open_now=open_now,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityDetailResponse,
    responses={404: NOT_FOUND_RESPONSE},
)
def get_opportunity(
    opportunity_id: uuid.UUID,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> OpportunityDetailResponse:
    return service.get_public_opportunity(opportunity_id)
