import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.applications.models import ApplicationStatus
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
