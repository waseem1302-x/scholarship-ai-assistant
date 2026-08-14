import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.document_lab.models import (
    AnalysisProviderStatus,
    AnalysisStatus,
    DocumentKind,
    DocumentVersionStatus,
    ExtractionStatus,
    FeedbackCategory,
    ScanStatus,
)


class DocumentLabPolicyResponse(BaseModel):
    enabled: bool
    feature_enabled: bool
    accepting_uploads: bool
    scanner_ready: bool
    worker_ready: bool
    analysis_provider_ready: bool
    supported_types: list[str]
    max_upload_bytes: int
    max_pages: int
    max_extracted_characters: int
    retention_days: int
    notice_version: str
    data_use_notice: str


class DocumentFeedbackResponse(BaseModel):
    id: uuid.UUID
    category: FeedbackCategory
    text: str
    excerpt: str | None
    rubric_category: str
    confidence: str
    is_general_suggestion: bool
    position: int


class DocumentAnalysisResponse(BaseModel):
    id: uuid.UUID
    version_id: uuid.UUID
    analysis_type: DocumentKind
    status: AnalysisStatus
    provider_status: AnalysisProviderStatus
    rubric_version: str
    provider: str
    model_version: str
    summary: str | None
    confidence: str | None
    abstained_reason: str | None
    created_at: datetime
    completed_at: datetime | None
    feedback: list[DocumentFeedbackResponse] = Field(default_factory=list)
    strengths: list[DocumentFeedbackResponse] = Field(default_factory=list)
    suggestions: list[DocumentFeedbackResponse] = Field(default_factory=list)
    questions_to_consider: list[DocumentFeedbackResponse] = Field(default_factory=list)
    warnings: list[DocumentFeedbackResponse] = Field(default_factory=list)
    quoted_evidence: list[str] = Field(default_factory=list)


class DocumentVersionResponse(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    version_number: int
    declared_content_type: str
    detected_content_type: str
    encryption_key_version: str
    size_bytes: int
    page_count: int | None
    status: DocumentVersionStatus
    scan_status: ScanStatus
    extraction_status: ExtractionStatus | None = None
    rejection_code: str | None
    created_at: datetime


class DocumentAssetResponse(BaseModel):
    id: uuid.UUID
    document_kind: DocumentKind
    display_name: str
    retention_expires_at: datetime
    created_at: datetime
    versions: list[DocumentVersionResponse] = Field(default_factory=list)


class AnalysisCreateRequest(BaseModel):
    analysis_type: DocumentKind
    consent: bool
    notice_version: str = Field(min_length=1, max_length=100)


class ApplicationDocumentLinkRequest(BaseModel):
    version_id: uuid.UUID
    confirmed: bool


class ApplicationDocumentLinkResponse(BaseModel):
    id: uuid.UUID
    application_document_id: uuid.UUID
    version_id: uuid.UUID
    confirmed_at: datetime


class DocumentExportResponse(BaseModel):
    exported_at: datetime
    assets: list[DocumentAssetResponse]
    analyses: list[DocumentAnalysisResponse]
