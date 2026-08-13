from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentUser, require_verified_student
from app.modules.auth.models import User
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.profiles.schemas import (
    StudentProfilePatch,
    StudentProfileResponse,
    StudentProfileUpsert,
)
from app.modules.profiles.service import StudentProfileService

router = APIRouter(prefix="/profiles", tags=["student profiles"])

VALIDATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "The profile payload failed validation.",
}
AUTHENTICATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "Authentication is required.",
}


def get_profile_service(
    session: Annotated[Session, Depends(get_db)],
) -> StudentProfileService:
    return StudentProfileService(StudentProfileRepository(session))


@router.get(
    "/me",
    response_model=StudentProfileResponse | None,
    responses={401: AUTHENTICATION_RESPONSE},
)
def get_my_profile(
    user: CurrentUser,
    service: Annotated[StudentProfileService, Depends(get_profile_service)],
) -> StudentProfileResponse | Response:
    profile = service.get_my_profile(user)
    if profile is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return profile


@router.put(
    "/me",
    response_model=StudentProfileResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        409: {"model": ErrorResponse},
        422: VALIDATION_RESPONSE,
    },
)
def upsert_my_profile(
    payload: StudentProfileUpsert,
    user: Annotated[User, Depends(require_verified_student)],
    service: Annotated[StudentProfileService, Depends(get_profile_service)],
) -> StudentProfileResponse:
    return service.upsert_my_profile(user, payload)


@router.patch(
    "/me",
    response_model=StudentProfileResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        409: {"model": ErrorResponse},
        422: VALIDATION_RESPONSE,
    },
)
def patch_my_profile(
    payload: StudentProfilePatch,
    user: Annotated[User, Depends(require_verified_student)],
    service: Annotated[StudentProfileService, Depends(get_profile_service)],
) -> StudentProfileResponse:
    return service.patch_my_profile(user, payload)
