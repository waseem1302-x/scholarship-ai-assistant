import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.modules.applications.deadlines import DeadlineUrgency
from app.modules.applications.models import (
    ApplicationLifecycle,
    ApplicationStatus,
    DeadlineState,
    ReminderStatus,
    TaskCategory,
    TaskPriority,
    TaskStatus,
)
from app.modules.opportunities.schemas import OpportunitySummaryResponse


class ChecklistItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    is_complete: bool = False
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class SavedOpportunityCreate(BaseModel):
    opportunity_id: uuid.UUID
    status: ApplicationStatus = ApplicationStatus.INTERESTED
    personal_notes: str | None = Field(default=None, max_length=5000)
    personal_deadline: datetime | None = None
    document_checklist: list[ChecklistItem] = Field(default_factory=list)
    recommendation_letters: list[ChecklistItem] = Field(default_factory=list)
    test_requirements: list[ChecklistItem] = Field(default_factory=list)
    submitted_at: datetime | None = None
    outcome_notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_submission_state(self) -> "SavedOpportunityCreate":
        if self.submitted_at is not None and self.status in {
            ApplicationStatus.INTERESTED,
            ApplicationStatus.RESEARCHING,
            ApplicationStatus.PREPARING_DOCUMENTS,
            ApplicationStatus.WAITING_FOR_RECOMMENDATION,
            ApplicationStatus.READY_TO_APPLY,
        }:
            raise ValueError(
                "submitted_at is only valid once the application is submitted or later"
            )
        return self


class SavedOpportunityUpdate(BaseModel):
    status: ApplicationStatus | None = None
    personal_notes: str | None = Field(default=None, max_length=5000)
    personal_deadline: datetime | None = None
    document_checklist: list[ChecklistItem] | None = None
    recommendation_letters: list[ChecklistItem] | None = None
    test_requirements: list[ChecklistItem] | None = None
    submitted_at: datetime | None = None
    outcome_notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_submission_state(self) -> "SavedOpportunityUpdate":
        if self.submitted_at is not None and self.status in {
            ApplicationStatus.INTERESTED,
            ApplicationStatus.RESEARCHING,
            ApplicationStatus.PREPARING_DOCUMENTS,
            ApplicationStatus.WAITING_FOR_RECOMMENDATION,
            ApplicationStatus.READY_TO_APPLY,
        }:
            raise ValueError(
                "submitted_at is only valid once the application is submitted or later"
            )
        return self


class SavedOpportunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ApplicationStatus
    personal_notes: str | None
    personal_deadline: datetime | None
    document_checklist: list[ChecklistItem]
    recommendation_letters: list[ChecklistItem]
    test_requirements: list[ChecklistItem]
    submitted_at: datetime | None
    outcome_notes: str | None
    created_at: datetime
    updated_at: datetime
    opportunity: OpportunitySummaryResponse


def _timezone_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("Timestamps must include an explicit timezone offset")
    return value.astimezone(UTC) if value is not None else None


def _iana_timezone(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Timezone must be a valid IANA timezone, such as Asia/Singapore") from exc
    return value


class ApplicationCreate(BaseModel):
    opportunity_id: uuid.UUID
    personal_deadline: datetime | None = None
    personal_deadline_timezone: str = Field(default="UTC", min_length=1, max_length=64)

    _check_personal_deadline = field_validator("personal_deadline")(_timezone_aware)
    _check_personal_timezone = field_validator("personal_deadline_timezone")(_iana_timezone)


class ApplicationUpdate(BaseModel):
    lifecycle: ApplicationLifecycle | None = None
    personal_deadline: datetime | None = None
    personal_deadline_timezone: str | None = Field(default=None, min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=5000)
    decision_notes: str | None = Field(default=None, max_length=5000)
    expected_version: int | None = Field(default=None, ge=1)

    _check_personal_deadline = field_validator("personal_deadline")(_timezone_aware)
    _check_personal_timezone = field_validator("personal_deadline_timezone")(_iana_timezone)


class ApplicationTaskCreate(BaseModel):
    category: TaskCategory
    title: str = Field(min_length=1, max_length=255)
    priority: TaskPriority = TaskPriority.NORMAL
    due_at: datetime | None = None
    source_id: uuid.UUID | None = None
    source_excerpt_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)

    _check_due_at = field_validator("due_at")(_timezone_aware)


class ApplicationTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    source_id: uuid.UUID | None = None
    source_excerpt_id: uuid.UUID | None = None
    completion_evidence: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=5000)

    _check_due_at = field_validator("due_at")(_timezone_aware)


class ApplicationReminderCreate(BaseModel):
    scheduled_at: datetime
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    task_id: uuid.UUID | None = None
    message: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)

    _check_scheduled_at = field_validator("scheduled_at")(_timezone_aware)


class ApplicationReminderUpdate(BaseModel):
    status: ReminderStatus | None = None
    scheduled_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    message: str | None = Field(default=None, max_length=500)

    _check_scheduled_at = field_validator("scheduled_at")(_timezone_aware)


class ApplicationNotificationPreferenceUpdate(BaseModel):
    in_app_enabled: bool


class ApplicationNotificationPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    in_app_enabled: bool
    updated_at: datetime


class ReminderWorkerHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    last_started_at: datetime | None
    last_completed_at: datetime | None
    processed_count: int
    failed_count: int
    is_healthy: bool


class ApplicationOperationalReportResponse(BaseModel):
    """Aggregate operational counters; deliberately contains no student content."""

    generated_at: datetime
    reminder_delivery_rate: float | None
    reminders_delivered: int
    reminders_failed: int
    overdue_open_tasks: int
    open_tasks: int
    task_completion_funnel: dict[str, int]
    failure_counts: dict[str, int]


class ApplicationDocumentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    task_id: uuid.UUID | None = None
    is_required: bool = True
    file_name: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=100)
    size_bytes: int | None = Field(default=None, ge=0, le=25_000_000)
    version_label: str | None = Field(default=None, max_length=100)
    expires_at: datetime | None = None
    reviewed_at: datetime | None = None
    is_complete: bool = False

    _check_expires_at = field_validator("expires_at", "reviewed_at")(_timezone_aware)


class ApplicationDocumentUpdate(ApplicationDocumentCreate):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class ApplicationTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    category: TaskCategory
    title: str
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    source_id: uuid.UUID | None
    source_excerpt_id: uuid.UUID | None
    is_generated: bool
    completion_evidence: str | None
    completed_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ApplicationReminderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID | None
    scheduled_at: datetime
    timezone: str
    message: str | None
    status: ReminderStatus
    delivered_at: datetime | None
    read_at: datetime | None
    failure_reason: str | None
    created_at: datetime


class ApplicationDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID | None
    name: str
    is_required: bool
    file_name: str | None
    content_type: str | None
    size_bytes: int | None
    version_label: str | None
    expires_at: datetime | None
    reviewed_at: datetime | None
    is_complete: bool
    created_at: datetime
    updated_at: datetime


class ApplicationEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    metadata_json: dict[str, object]
    created_at: datetime


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    lifecycle: ApplicationLifecycle
    official_deadline: datetime | None
    official_deadline_timezone: str
    official_deadline_state: DeadlineState
    official_deadline_source_id: uuid.UUID | None
    official_deadline_excerpt_id: uuid.UUID | None
    official_deadline_verified_at: datetime | None
    personal_deadline: datetime | None
    personal_deadline_timezone: str
    deadline_urgency: DeadlineUrgency
    notes: str | None
    submitted_at: datetime | None
    decision_notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    opportunity: OpportunitySummaryResponse
    tasks: list[ApplicationTaskResponse] = Field(default_factory=list)
    reminders: list[ApplicationReminderResponse] = Field(default_factory=list)
    documents: list[ApplicationDocumentResponse] = Field(default_factory=list)


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    pagination: "ApplicationPagination"


class ApplicationPagination(BaseModel):
    total: int
    limit: int
    offset: int
    count: int
    has_next: bool
    has_previous: bool


class CommandCentreResponse(BaseModel):
    urgent_tasks: list[ApplicationTaskResponse]
    blocked_tasks: list[ApplicationTaskResponse]
    blocked_applications: list[ApplicationResponse]
    approaching_deadlines: list[ApplicationResponse]
    submitted_applications: list[ApplicationResponse]
    upcoming_reminders: list[ApplicationReminderResponse]
    recently_changed_opportunities: list[ApplicationResponse]
