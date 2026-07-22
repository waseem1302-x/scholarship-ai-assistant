from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentUser
from app.modules.matching.schemas import MatchListResponse
from app.modules.matching.service import MatchingService
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.profiles.repository import StudentProfileRepository

router = APIRouter(prefix="/matches", tags=["matching"])

AUTHENTICATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "Authentication is required.",
}
PROFILE_REQUIRED_RESPONSE = {
    "model": ErrorResponse,
    "description": "A student profile is required before matching.",
}


def get_matching_service(session: Annotated[Session, Depends(get_db)]) -> MatchingService:
    return MatchingService(
        StudentProfileRepository(session),
        OpportunityRepository(session),
    )


@router.get(
    "/me",
    response_model=MatchListResponse,
    responses={400: PROFILE_REQUIRED_RESPONSE, 401: AUTHENTICATION_RESPONSE},
)
def match_my_profile(
    user: CurrentUser,
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> MatchListResponse:
    return service.match_for_user(user.id)
