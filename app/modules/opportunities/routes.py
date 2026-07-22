import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import User, UserRole
from app.modules.opportunities.models import DegreeLevel, FundingType
from app.modules.opportunities.schemas import (
    AdminOpportunityResponse,
    OpportunityCreate,
    OpportunityDetailResponse,
    OpportunitySummaryResponse,
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


AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


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
    response_model=list[AdminOpportunityResponse],
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE},
)
def list_admin_opportunities(
    _admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> list[AdminOpportunityResponse]:
    return service.list_admin_opportunities()


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
    response_model=list[OpportunitySummaryResponse],
    responses={422: VALIDATION_RESPONSE},
)
def search_opportunities(
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
    country: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    degree_level: DegreeLevel | None = None,
    funding_type: FundingType | None = None,
    deadline_before: datetime | None = None,
) -> list[OpportunitySummaryResponse]:
    return service.list_public_opportunities(
        country=country,
        degree_level=degree_level,
        funding_type=funding_type,
        deadline_before=deadline_before,
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
