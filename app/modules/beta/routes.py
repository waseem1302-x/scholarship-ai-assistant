import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import require_admin_step_up, require_roles
from app.modules.auth.models import User, UserRole
from app.modules.beta.schemas import (
    BetaInvitationCreate,
    BetaInvitationDeliveryResponse,
    BetaInvitationResponse,
    BetaPolicyResponse,
)
from app.modules.beta.service import BetaService

router = APIRouter(prefix="/beta", tags=["beta operations"])
AdminUser = Annotated[User, Depends(require_admin_step_up)]
StudentOrAdmin = Annotated[User, Depends(require_roles(UserRole.STUDENT, UserRole.ADMIN))]


def get_beta_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BetaService:
    return BetaService(session, settings)


BetaServiceDependency = Annotated[BetaService, Depends(get_beta_service)]


@router.get("/policy", response_model=BetaPolicyResponse)
def beta_policy(_: StudentOrAdmin, service: BetaServiceDependency) -> BetaPolicyResponse:
    return service.policy()


@router.get("/admin/invitations", response_model=list[BetaInvitationResponse])
def list_invitations(_: AdminUser, service: BetaServiceDependency) -> list[BetaInvitationResponse]:
    return service.list_invitations()


@router.post(
    "/admin/invitations",
    response_model=BetaInvitationDeliveryResponse,
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def create_invitation(
    payload: BetaInvitationCreate, admin: AdminUser, service: BetaServiceDependency
) -> BetaInvitationDeliveryResponse:
    return service.create_invitation(payload, admin)


@router.delete(
    "/admin/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def revoke_invitation(
    invitation_id: uuid.UUID, admin: AdminUser, service: BetaServiceDependency
) -> Response:
    service.revoke_invitation(invitation_id, admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
