import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.opportunities.schemas import OpportunitySummaryResponse


class MatchExplanation(BaseModel):
    satisfied: list[str]
    missing: list[str]
    uncertain: list[str]
    next_steps: list[str]


class OpportunityMatchResponse(BaseModel):
    opportunity: OpportunitySummaryResponse
    # Retained for API compatibility. It is zero when hard eligibility failed.
    match_score: int
    score_label: str
    eligibility_status: str
    fit_score: int | None
    preference_fit: int | None = None
    evidence_completeness: int
    profile_completeness: int
    confidence: str
    confidence_factors: list[str] = Field(default_factory=list)
    eligibility_failures: list[str] = Field(default_factory=list)
    preference_mismatches: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    failed_criteria: list[str]
    unknown_criteria: list[str]
    warnings: list[str]
    matcher_version: str
    evaluated_at: datetime
    explanation: MatchExplanation
    disclaimer: str = (
        "This score ranks profile fit against stated requirements. It is not a probability "
        "of admission, scholarship selection, or visa approval."
    )


class MatchListResponse(BaseModel):
    profile_id: uuid.UUID
    evaluation_id: uuid.UUID | None = None
    results: list[OpportunityMatchResponse]


class MatchEvaluationRecordResponse(BaseModel):
    """History contract. Profile snapshots remain owner-only and are not returned here."""

    id: uuid.UUID
    profile_id: uuid.UUID | None
    supersedes_evaluation_id: uuid.UUID | None
    matcher_version: str
    evaluated_at: datetime
    expires_at: datetime
    profile_snapshot_hash: str
