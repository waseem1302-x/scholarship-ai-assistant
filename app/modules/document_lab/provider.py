"""Consent-gated document analysis provider boundary."""

from typing import Protocol

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.modules.document_lab.models import DocumentKind, FeedbackCategory


class ProviderFeedbackItem(BaseModel):
    category: FeedbackCategory
    text: str = Field(min_length=1, max_length=1_500)
    excerpt: str | None = Field(default=None, max_length=300)
    rubric_category: str | None = Field(default=None, min_length=1, max_length=100)
    confidence: str = Field(default="medium", pattern="^(low|medium|high)$")
    is_general_suggestion: bool = False


class ProviderAnalysisOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=2_000)
    confidence: str = Field(pattern="^(low|medium|high)$")
    strengths: list[ProviderFeedbackItem] = Field(default_factory=list, max_length=20)
    suggestions: list[ProviderFeedbackItem] = Field(default_factory=list, max_length=20)
    questions_to_consider: list[ProviderFeedbackItem] = Field(default_factory=list, max_length=20)
    warnings: list[ProviderFeedbackItem] = Field(default_factory=list, max_length=20)
    abstained_reason: str | None = Field(default=None, max_length=100)


class DocumentProviderError(RuntimeError):
    status: str = "failed"


class DocumentProviderUnavailable(DocumentProviderError):
    status = "unavailable"


class DocumentProviderQuotaExhausted(DocumentProviderError):
    status = "quota_exhausted"


class DocumentProviderTimeout(DocumentProviderError):
    status = "failed"


class DocumentProvider(Protocol):
    name: str
    model_version: str

    def analyse(self, text: str, analysis_type: DocumentKind) -> ProviderAnalysisOutput: ...


class UnavailableDocumentProvider:
    def __init__(self, name: str, model_version: str) -> None:
        self.name = name
        self.model_version = model_version

    def analyse(self, text: str, analysis_type: DocumentKind) -> ProviderAnalysisOutput:
        del text, analysis_type
        raise DocumentProviderUnavailable("No reviewed document provider is configured")


def get_provider(settings: Settings) -> DocumentProvider:
    # Remote providers remain fail-closed until a reviewed adapter is installed.
    return UnavailableDocumentProvider(settings.document_lab_provider, settings.document_lab_model)
