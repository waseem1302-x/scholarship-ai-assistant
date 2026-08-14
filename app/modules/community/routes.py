import uuid
from typing import Annotated

from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse
from app.db.session import get_db, get_system_db
from app.modules.auth.dependencies import (
    CurrentUser,
    require_admin_step_up,
    require_verified_student,
)
from app.modules.auth.models import User
from app.modules.community.models import CommunityTopic
from app.modules.community.schemas import (
    CommunityBlockCreate,
    CommunityExportResponse,
    CommunityModerationActionRequest,
    CommunityModerationQueueResponse,
    CommunityPostCreate,
    CommunityPostDetailResponse,
    CommunityPostListResponse,
    CommunityPostUpdate,
    CommunityPreferenceResponse,
    CommunityPreferenceUpdate,
    CommunityReplyCreate,
    CommunityReplyResponse,
    CommunityReplyUpdate,
    CommunityReportCreate,
    CommunityReportResponse,
)
from app.modules.community.service import CommunityService
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/community", tags=["scholarship community"])
AUTH = {"model": ErrorResponse, "description": "Authentication is required."}
NOT_FOUND = {
    "model": ErrorResponse,
    "description": "The community record was not found.",
}


def get_community_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CommunityService:
    return CommunityService(session, settings)


def get_privileged_community_service(
    session: Annotated[Session, Depends(get_system_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CommunityService:
    return CommunityService(session, settings)


@router.get(
    "/preferences",
    response_model=CommunityPreferenceResponse,
    responses={401: AUTH},
)
def get_preferences(
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
):
    return service.preferences(user)


@router.put(
    "/preferences",
    response_model=CommunityPreferenceResponse,
    responses={401: AUTH, 409: {"model": ErrorResponse}},
)
def update_preferences(
    payload: CommunityPreferenceUpdate,
    user: Annotated[User, Depends(require_verified_student)],
    service: Annotated[CommunityService, Depends(get_community_service)],
):
    return service.update_preferences(user, payload)


@router.get("/posts", response_model=CommunityPostListResponse, responses={401: AUTH})
def list_posts(
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
    q: str | None = Query(default=None, min_length=2, max_length=100),
    topic: CommunityTopic | None = None,
    opportunity_id: uuid.UUID | None = None,
    bookmarked_only: bool = False,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> CommunityPostListResponse:
    return service.list_posts(
        user,
        query=q,
        topic=topic,
        opportunity_id=opportunity_id,
        bookmarked_only=bookmarked_only,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/posts",
    response_model=CommunityPostDetailResponse,
    status_code=status.HTTP_201_CREATED,
    responses={401: AUTH, 403: {"model": ErrorResponse}, 404: NOT_FOUND},
)
def create_post(
    payload: CommunityPostCreate,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
):
    return service.create_post(payload, user)


@router.get(
    "/posts/{post_id}",
    response_model=CommunityPostDetailResponse,
    responses={401: AUTH, 404: NOT_FOUND},
)
def get_post(
    post_id: uuid.UUID,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
):
    return service.get_post(post_id, user)


@router.patch(
    "/posts/{post_id}",
    response_model=CommunityPostDetailResponse,
    responses={401: AUTH, 403: {"model": ErrorResponse}, 404: NOT_FOUND},
)
def update_post(
    post_id: uuid.UUID,
    payload: CommunityPostUpdate,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
):
    return service.update_post(post_id, payload, user)


@router.delete(
    "/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTH, 404: NOT_FOUND},
)
def delete_post(
    post_id: uuid.UUID,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
) -> Response:
    service.delete_post(post_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/posts/{post_id}/replies",
    response_model=CommunityReplyResponse,
    status_code=status.HTTP_201_CREATED,
    responses={401: AUTH, 404: NOT_FOUND},
)
def create_reply(
    post_id: uuid.UUID,
    payload: CommunityReplyCreate,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
):
    return service.create_reply(post_id, payload, user)


@router.patch(
    "/replies/{reply_id}",
    response_model=CommunityReplyResponse,
    responses={401: AUTH, 404: NOT_FOUND},
)
def update_reply(
    reply_id: uuid.UUID,
    payload: CommunityReplyUpdate,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
):
    return service.update_reply(reply_id, payload, user)


@router.delete(
    "/replies/{reply_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTH, 404: NOT_FOUND},
)
def delete_reply(
    reply_id: uuid.UUID,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
) -> Response:
    service.delete_reply(reply_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/posts/{post_id}/bookmarks",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTH, 404: NOT_FOUND},
)
def bookmark(
    post_id: uuid.UUID,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
) -> Response:
    service.bookmark(post_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/posts/{post_id}/bookmarks",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTH},
)
def unbookmark(
    post_id: uuid.UUID,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
) -> Response:
    service.unbookmark(post_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/blocks",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTH, 404: NOT_FOUND},
)
def block(
    payload: CommunityBlockCreate,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
) -> Response:
    service.block(payload, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/blocks/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTH},
)
def unblock(
    user_id: uuid.UUID,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
) -> Response:
    service.unblock(user_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reports",
    response_model=CommunityReportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={401: AUTH, 404: NOT_FOUND, 409: {"model": ErrorResponse}},
)
def report(
    payload: CommunityReportCreate,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
):
    return service.report(payload, user)


@router.get("/export", response_model=CommunityExportResponse, responses={401: AUTH})
def export_data(
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
):
    return service.export_data(user)


@router.delete("/data", status_code=status.HTTP_204_NO_CONTENT, responses={401: AUTH})
def delete_data(
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_community_service)],
) -> Response:
    service.delete_data(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/admin/reports",
    response_model=CommunityModerationQueueResponse,
    dependencies=[Depends(require_admin_step_up)],
    responses={401: AUTH, 403: {"model": ErrorResponse}},
)
def moderation_queue(
    service: Annotated[CommunityService, Depends(get_privileged_community_service)],
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    return service.moderation_queue(limit=limit, offset=offset)


@router.post(
    "/admin/moderation-actions",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_step_up)],
    responses={401: AUTH, 403: {"model": ErrorResponse}, 404: NOT_FOUND},
)
def moderate(
    payload: CommunityModerationActionRequest,
    user: CurrentUser,
    service: Annotated[CommunityService, Depends(get_privileged_community_service)],
) -> Response:
    service.moderate(payload, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
