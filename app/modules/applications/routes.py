import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.applications.models import ApplicationStatus
from app.modules.applications.schemas import (
    SavedOpportunityCreate,
    SavedOpportunityResponse,
    SavedOpportunityUpdate,
)
from app.modules.applications.service import SavedOpportunityService
from app.modules.auth.dependencies import require_roles, require_verified_student
from app.modules.auth.models import User, UserRole

router = APIRouter(prefix="/saved-opportunities", tags=["saved opportunities"])
LEGACY_SUNSET = "Mon, 01 Feb 2027 00:00:00 GMT"

AUTHENTICATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "Authentication is required.",
}
FORBIDDEN_RESPONSE = {
    "model": ErrorResponse,
    "description": "Only student users can manage saved opportunities.",
}
NOT_FOUND_RESPONSE = {
    "model": ErrorResponse,
    "description": "The saved opportunity or public opportunity was not found.",
}
CONFLICT_RESPONSE = {
    "model": ErrorResponse,
    "description": "This opportunity is already saved by the current user.",
}
VALIDATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "The request parameters or body failed validation.",
}


StudentUser = Annotated[User, Depends(require_roles(UserRole.STUDENT))]
VerifiedStudentUser = Annotated[User, Depends(require_verified_student)]


def get_saved_opportunity_service(
    session: Annotated[Session, Depends(get_db)],
) -> SavedOpportunityService:
    return SavedOpportunityService(session)


def mark_legacy_tracker_response(response: Response) -> None:
    """Expose an explicit, machine-readable compatibility window to old clients."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = LEGACY_SUNSET
    response.headers["Link"] = '</api/v1/applications>; rel="successor-version"'
    response.headers["Warning"] = '299 - "Saved opportunities are deprecated; use Applications"'


@router.post(
    "",
    response_model=SavedOpportunityResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        409: CONFLICT_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def save_opportunity(
    payload: SavedOpportunityCreate,
    response: Response,
    user: VerifiedStudentUser,
    service: Annotated[SavedOpportunityService, Depends(get_saved_opportunity_service)],
) -> SavedOpportunityResponse:
    mark_legacy_tracker_response(response)
    return service.create(payload, user=user)


@router.get(
    "",
    response_model=list[SavedOpportunityResponse],
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE},
)
def list_saved_opportunities(
    response: Response,
    user: StudentUser,
    service: Annotated[SavedOpportunityService, Depends(get_saved_opportunity_service)],
    status_filter: ApplicationStatus | None = None,
) -> list[SavedOpportunityResponse]:
    mark_legacy_tracker_response(response)
    return service.list_for_user(user, status_filter=status_filter)


@router.get(
    "/{saved_opportunity_id}",
    response_model=SavedOpportunityResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
    },
)
def get_saved_opportunity(
    saved_opportunity_id: uuid.UUID,
    response: Response,
    user: StudentUser,
    service: Annotated[SavedOpportunityService, Depends(get_saved_opportunity_service)],
) -> SavedOpportunityResponse:
    mark_legacy_tracker_response(response)
    return service.get(saved_opportunity_id, user=user)


@router.patch(
    "/{saved_opportunity_id}",
    response_model=SavedOpportunityResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def update_saved_opportunity(
    saved_opportunity_id: uuid.UUID,
    payload: SavedOpportunityUpdate,
    response: Response,
    user: VerifiedStudentUser,
    service: Annotated[SavedOpportunityService, Depends(get_saved_opportunity_service)],
) -> SavedOpportunityResponse:
    mark_legacy_tracker_response(response)
    return service.update(saved_opportunity_id, payload, user=user)


@router.delete(
    "/{saved_opportunity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
    },
)
def delete_saved_opportunity(
    saved_opportunity_id: uuid.UUID,
    user: StudentUser,
    service: Annotated[SavedOpportunityService, Depends(get_saved_opportunity_service)],
) -> Response:
    service.delete(saved_opportunity_id, user=user)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    mark_legacy_tracker_response(response)
    return response
