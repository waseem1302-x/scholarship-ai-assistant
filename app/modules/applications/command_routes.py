import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.applications.command_service import ApplicationCommandService
from app.modules.applications.schemas import (
    ApplicationCreate,
    ApplicationDocumentCreate,
    ApplicationDocumentResponse,
    ApplicationDocumentUpdate,
    ApplicationEventResponse,
    ApplicationListResponse,
    ApplicationNotificationPreferenceResponse,
    ApplicationNotificationPreferenceUpdate,
    ApplicationOperationalReportResponse,
    ApplicationPagination,
    ApplicationReminderCreate,
    ApplicationReminderResponse,
    ApplicationReminderUpdate,
    ApplicationResponse,
    ApplicationTaskCreate,
    ApplicationTaskResponse,
    ApplicationTaskUpdate,
    ApplicationUpdate,
    CommandCentreResponse,
    ReminderWorkerHealthResponse,
)
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import User, UserRole

router = APIRouter(prefix="/applications", tags=["applications"])
StudentUser = Annotated[User, Depends(require_roles(UserRole.STUDENT))]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


def service(session: Annotated[Session, Depends(get_db)]) -> ApplicationCommandService:
    return ApplicationCommandService(session)


CommandService = Annotated[ApplicationCommandService, Depends(service)]
Errors = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.get("/command-centre", response_model=CommandCentreResponse, responses=Errors)
def command_centre(user: StudentUser, application_service: CommandService) -> CommandCentreResponse:
    return application_service.dashboard(user)


@router.get(
    "/operational-report",
    response_model=ApplicationOperationalReportResponse,
    responses=Errors,
)
def operational_report(
    _: AdminUser, application_service: CommandService
) -> ApplicationOperationalReportResponse:
    """Admin-only aggregate workflow health; no private application content is returned."""
    return application_service.operational_report()


@router.get(
    "/notification-preferences",
    response_model=ApplicationNotificationPreferenceResponse,
    responses=Errors,
)
def get_notification_preference(
    user: StudentUser, application_service: CommandService
) -> ApplicationNotificationPreferenceResponse:
    return application_service.notification_preference(user=user)


@router.put(
    "/notification-preferences",
    response_model=ApplicationNotificationPreferenceResponse,
    responses=Errors,
)
def update_notification_preference(
    payload: ApplicationNotificationPreferenceUpdate,
    user: StudentUser,
    application_service: CommandService,
) -> ApplicationNotificationPreferenceResponse:
    return application_service.update_notification_preference(payload, user=user)


@router.get(
    "/reminder-worker-health", response_model=ReminderWorkerHealthResponse, responses=Errors
)
def reminder_worker_health(
    user: StudentUser, application_service: CommandService
) -> ReminderWorkerHealthResponse:
    return application_service.reminder_worker_health()


@router.get("/export", responses=Errors)
def export_application_data(
    user: StudentUser, application_service: CommandService
) -> dict[str, object]:
    """Private data export; excludes operational logs and other users' data."""
    return application_service.export(user)


@router.delete("/data", status_code=status.HTTP_204_NO_CONTENT, responses=Errors)
def delete_all_application_data(user: StudentUser, application_service: CommandService) -> Response:
    application_service.delete_all_application_data(user=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED, responses=Errors
)
def create_application(
    payload: ApplicationCreate, user: StudentUser, application_service: CommandService
) -> ApplicationResponse:
    return application_service.create(payload, user=user)


@router.get("", response_model=ApplicationListResponse, responses=Errors)
def list_applications(
    user: StudentUser,
    application_service: CommandService,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApplicationListResponse:
    items, total = application_service.list(user, limit=limit, offset=offset)
    return ApplicationListResponse(
        items=items,
        pagination=ApplicationPagination(
            total=total,
            limit=limit,
            offset=offset,
            count=len(items),
            has_next=offset + len(items) < total,
            has_previous=offset > 0,
        ),
    )


@router.get("/{application_id}", response_model=ApplicationResponse, responses=Errors)
def get_application(
    application_id: uuid.UUID, user: StudentUser, application_service: CommandService
) -> ApplicationResponse:
    return application_service.get(application_id, user=user)


@router.patch("/{application_id}", response_model=ApplicationResponse, responses=Errors)
def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    user: StudentUser,
    application_service: CommandService,
) -> ApplicationResponse:
    return application_service.update(application_id, payload, user=user)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT, responses=Errors)
def delete_application(
    application_id: uuid.UUID, user: StudentUser, application_service: CommandService
) -> Response:
    application_service.delete(application_id, user=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{application_id}/events", response_model=list[ApplicationEventResponse], responses=Errors
)
def list_events(
    application_id: uuid.UUID,
    user: StudentUser,
    application_service: CommandService,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ApplicationEventResponse]:
    events, _ = application_service.events(application_id, user=user, limit=limit, offset=offset)
    return events


@router.post(
    "/{application_id}/tasks",
    response_model=ApplicationTaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses=Errors,
)
def create_task(
    application_id: uuid.UUID,
    payload: ApplicationTaskCreate,
    user: StudentUser,
    application_service: CommandService,
) -> ApplicationTaskResponse:
    return application_service.create_task(application_id, payload, user=user)


@router.patch(
    "/{application_id}/tasks/{task_id}", response_model=ApplicationTaskResponse, responses=Errors
)
def update_task(
    application_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: ApplicationTaskUpdate,
    user: StudentUser,
    application_service: CommandService,
) -> ApplicationTaskResponse:
    return application_service.update_task(application_id, task_id, payload, user=user)


@router.delete(
    "/{application_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, responses=Errors
)
def delete_task(
    application_id: uuid.UUID,
    task_id: uuid.UUID,
    user: StudentUser,
    application_service: CommandService,
) -> Response:
    application_service.delete_task(application_id, task_id, user=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{application_id}/reminders",
    response_model=ApplicationReminderResponse,
    status_code=status.HTTP_201_CREATED,
    responses=Errors,
)
def create_reminder(
    application_id: uuid.UUID,
    payload: ApplicationReminderCreate,
    user: StudentUser,
    application_service: CommandService,
) -> ApplicationReminderResponse:
    return application_service.create_reminder(application_id, payload, user=user)


@router.patch(
    "/{application_id}/reminders/{reminder_id}",
    response_model=ApplicationReminderResponse,
    responses=Errors,
)
def update_reminder(
    application_id: uuid.UUID,
    reminder_id: uuid.UUID,
    payload: ApplicationReminderUpdate,
    user: StudentUser,
    application_service: CommandService,
) -> ApplicationReminderResponse:
    return application_service.update_reminder(application_id, reminder_id, payload, user=user)


@router.post(
    "/{application_id}/documents",
    response_model=ApplicationDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses=Errors,
)
def create_document(
    application_id: uuid.UUID,
    payload: ApplicationDocumentCreate,
    user: StudentUser,
    application_service: CommandService,
) -> ApplicationDocumentResponse:
    return application_service.create_document(application_id, payload, user=user)


@router.patch(
    "/{application_id}/documents/{document_id}",
    response_model=ApplicationDocumentResponse,
    responses=Errors,
)
def update_document(
    application_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: ApplicationDocumentUpdate,
    user: StudentUser,
    application_service: CommandService,
) -> ApplicationDocumentResponse:
    return application_service.update_document(application_id, document_id, payload, user=user)
