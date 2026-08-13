import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.modules.assistant.models import (
    AssistantAnswerStatus,
    AssistantFeedbackType,
)


class CitationResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID | None
    source_id: uuid.UUID
    source_excerpt_id: uuid.UUID | None
    claim: str
    claim_key: str
    source_title: str
    source_url: HttpUrl
    excerpt: str
    last_verified_at: datetime | None
    freshness: str


class FactResponse(BaseModel):
    text: str
    citation_ids: list[uuid.UUID] = Field(min_length=1)


class PossibleMatchResponse(BaseModel):
    opportunity_id: uuid.UUID
    name: str
    reason: str
    citation_ids: list[uuid.UUID] = Field(min_length=1)


class RequirementResponse(BaseModel):
    text: str
    citation_ids: list[uuid.UUID] = Field(min_length=1)


class PrivateProgressItemResponse(BaseModel):
    opportunity_id: uuid.UUID
    name: str
    lifecycle: str
    outstanding_tasks: int


class AssistantStructuredResponse(BaseModel):
    answer: str
    answer_type: str
    confidence: str
    facts: list[FactResponse] = Field(default_factory=list)
    possible_matches: list[PossibleMatchResponse] = Field(default_factory=list)
    requirements_to_check: list[RequirementResponse] = Field(default_factory=list)
    private_progress: list[PrivateProgressItemResponse] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    citations: list[CitationResponse] = Field(default_factory=list)
    abstained_reason: str | None = None


class ConversationSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    history_enabled: bool
    created_at: datetime
    updated_at: datetime


class AssistantAnswerRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    conversation_id: uuid.UUID | None = None
    use_profile: bool = False
    use_application_data: bool = False
    selected_opportunity_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)


class AssistantAnswerResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: AssistantAnswerStatus
    provider: str
    model_version: str
    prompt_template_version: str
    retrieval_version: str
    evidence_packet_id: uuid.UUID
    created_at: datetime
    saved_to_workspace: bool
    response: AssistantStructuredResponse


class ConversationDetailResponse(ConversationSummaryResponse):
    answers: list[AssistantAnswerResponse] = Field(default_factory=list)


class AssistantPreferenceResponse(BaseModel):
    consented: bool
    history_enabled: bool
    history_retention_days: int
    feedback_retention_days: int


class AssistantPreferenceUpdate(BaseModel):
    consent: bool | None = None
    history_enabled: bool | None = None


class HistoryPreferenceRequest(BaseModel):
    enabled: bool


class FeedbackRequest(BaseModel):
    feedback_type: AssistantFeedbackType
    comment: str | None = Field(default=None, max_length=1000)


class SaveAnswerResponse(BaseModel):
    id: uuid.UUID
    saved_to_workspace: bool
    saved_at: datetime | None


class AssistantExportResponse(BaseModel):
    conversations: list[ConversationDetailResponse]
