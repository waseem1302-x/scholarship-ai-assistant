import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.community.models import (
    CommunityContentStatus,
    CommunityModerationAction,
    CommunityReportReason,
    CommunityReportStatus,
    CommunityTopic,
)


class CommunityAuthorResponse(BaseModel):
    id: uuid.UUID
    display_name: str


class CommunityOpportunityResponse(BaseModel):
    id: uuid.UUID
    name: str


class CommunityReplyResponse(BaseModel):
    id: uuid.UUID
    body: str
    author: CommunityAuthorResponse
    created_at: datetime
    updated_at: datetime
    is_owner: bool = False


class CommunityPostSummaryResponse(BaseModel):
    id: uuid.UUID
    topic: CommunityTopic
    title: str
    body: str
    author: CommunityAuthorResponse
    opportunity: CommunityOpportunityResponse | None = None
    reply_count: int
    visible_reply_count: int
    created_at: datetime
    updated_at: datetime
    is_owner: bool = False
    is_bookmarked: bool = False
    replies: list[CommunityReplyResponse] = Field(default_factory=list)


class CommunityPostDetailResponse(CommunityPostSummaryResponse):
    replies: list[CommunityReplyResponse] = Field(default_factory=list)


class CommunityPostListResponse(BaseModel):
    posts: list[CommunityPostSummaryResponse]
    total: int
    limit: int
    offset: int
    has_next: bool


class CommunityPostCreate(BaseModel):
    topic: CommunityTopic
    title: str = Field(min_length=4, max_length=160)
    body: str = Field(min_length=10, max_length=6000)
    opportunity_id: uuid.UUID | None = None


class CommunityPostUpdate(BaseModel):
    title: str = Field(min_length=4, max_length=160)
    body: str = Field(min_length=10, max_length=6000)
    topic: CommunityTopic


class CommunityReplyCreate(BaseModel):
    body: str = Field(min_length=2, max_length=4000)


class CommunityReplyUpdate(CommunityReplyCreate):
    pass


class CommunityBlockCreate(BaseModel):
    user_id: uuid.UUID


class CommunityReportCreate(BaseModel):
    post_id: uuid.UUID | None = None
    reply_id: uuid.UUID | None = None
    reason: CommunityReportReason
    detail: str | None = Field(default=None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def exactly_one_target(self) -> "CommunityReportCreate":
        if (self.post_id is None) == (self.reply_id is None):
            raise ValueError("Provide exactly one of post_id or reply_id")
        return self


class CommunityPreferenceResponse(BaseModel):
    display_name: str | None
    consented: bool
    suspended: bool
    notice_version: str


class CommunityPreferenceUpdate(BaseModel):
    consent: bool | None = None
    display_name: str | None = Field(default=None, min_length=3, max_length=40)


class CommunityReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reason: CommunityReportReason
    detail: str | None
    status: CommunityReportStatus
    created_at: datetime
    post_id: uuid.UUID | None
    reply_id: uuid.UUID | None


class CommunityModerationQueueItem(BaseModel):
    report: CommunityReportResponse
    content_type: str
    content_id: uuid.UUID
    content_preview: str
    author: CommunityAuthorResponse
    status: CommunityContentStatus


class CommunityModerationQueueResponse(BaseModel):
    reports: list[CommunityModerationQueueItem]
    total: int
    limit: int
    offset: int
    has_next: bool


class CommunityModerationActionRequest(BaseModel):
    action: CommunityModerationAction
    post_id: uuid.UUID | None = None
    reply_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    report_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, min_length=3, max_length=300)

    @model_validator(mode="after")
    def valid_target(self) -> "CommunityModerationActionRequest":
        content_count = int(self.post_id is not None) + int(self.reply_id is not None)
        if self.action in {
            CommunityModerationAction.HIDE,
            CommunityModerationAction.RESTORE,
        }:
            if content_count != 1 or self.user_id or self.report_id:
                raise ValueError("Hide and restore require exactly one post_id or reply_id")
        elif self.action in {
            CommunityModerationAction.SUSPEND,
            CommunityModerationAction.REINSTATE,
        }:
            if self.user_id is None or content_count or self.report_id:
                raise ValueError("Suspend and reinstate require user_id only")
        elif self.action is CommunityModerationAction.RESOLVE_REPORT and (
            self.report_id is None or content_count or self.user_id
        ):
            raise ValueError("Resolve report requires report_id only")
        return self


class CommunityExportResponse(BaseModel):
    preferences: CommunityPreferenceResponse
    posts: list[CommunityPostDetailResponse]
    reports: list[CommunityReportResponse]
