import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.assistant.schemas import (
    AssistantAnswerRequest,
    AssistantAnswerResponse,
    AssistantExportResponse,
    AssistantPreferenceResponse,
    AssistantPreferenceUpdate,
    ConversationDetailResponse,
    ConversationSummaryResponse,
    FeedbackRequest,
    HistoryPreferenceRequest,
    SaveAnswerResponse,
)
from app.modules.assistant.service import AssistantService
from app.modules.auth.dependencies import CurrentUser, require_verified_student
from app.modules.auth.models import User

router = APIRouter(prefix="/assistant", tags=["citation-first assistant"])
VerifiedStudentUser = Annotated[User, Depends(require_verified_student)]
AUTH = {"model": ErrorResponse, "description": "Authentication is required."}
NOT_FOUND = {
    "model": ErrorResponse,
    "description": "The requested private assistant record was not found.",
}


def get_assistant_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantService:
    return AssistantService(session, settings)


@router.post(
    "/answers",
    response_model=AssistantAnswerResponse,
    responses={401: AUTH, 404: NOT_FOUND, 429: {"model": ErrorResponse}},
)
def create_answer(
    payload: AssistantAnswerRequest,
    user: VerifiedStudentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> AssistantAnswerResponse:
    return service.answer(payload, user)


@router.get(
    "/conversations",
    response_model=list[ConversationSummaryResponse],
    responses={401: AUTH},
)
def list_conversations(
    user: CurrentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> list[ConversationSummaryResponse]:
    return service.list_conversations(user.id)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    responses={401: AUTH, 404: NOT_FOUND},
)
def get_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> ConversationDetailResponse:
    return service.get_conversation(conversation_id, user.id)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTH, 404: NOT_FOUND},
)
def delete_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> Response:
    service.delete_conversation(conversation_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/preferences",
    response_model=AssistantPreferenceResponse,
    responses={401: AUTH},
)
def get_preferences(
    user: CurrentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> AssistantPreferenceResponse:
    return service.get_preferences(user.id)


@router.put(
    "/preferences",
    response_model=AssistantPreferenceResponse,
    responses={401: AUTH},
)
def update_preferences(
    payload: AssistantPreferenceUpdate,
    user: VerifiedStudentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> AssistantPreferenceResponse:
    return service.update_preferences(user.id, payload)


@router.put(
    "/history-preference",
    response_model=AssistantPreferenceResponse,
    responses={401: AUTH},
)
def set_history_preference_legacy(
    payload: HistoryPreferenceRequest,
    user: VerifiedStudentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> AssistantPreferenceResponse:
    return service.update_preferences(
        user.id, AssistantPreferenceUpdate(history_enabled=payload.enabled)
    )


@router.post(
    "/answers/{answer_id}/save",
    response_model=SaveAnswerResponse,
    responses={401: AUTH, 404: NOT_FOUND},
)
def save_answer(
    answer_id: uuid.UUID,
    user: VerifiedStudentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> SaveAnswerResponse:
    return service.save_answer(answer_id, user.id)


@router.post(
    "/answers/{answer_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTH, 404: NOT_FOUND},
)
def submit_feedback(
    answer_id: uuid.UUID,
    payload: FeedbackRequest,
    user: VerifiedStudentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> Response:
    service.feedback(answer_id, payload, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/export", response_model=AssistantExportResponse, responses={401: AUTH})
def export_assistant_data(
    user: CurrentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> AssistantExportResponse:
    return AssistantExportResponse(conversations=service.export_data(user.id))


@router.delete("/data", status_code=status.HTTP_204_NO_CONTENT, responses={401: AUTH})
def delete_assistant_data(
    user: CurrentUser,
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> Response:
    service.delete_all_data(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
