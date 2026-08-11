import uuid
from datetime import datetime

from pydantic import BaseModel

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
    evidence_completeness: int
    confidence: str
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
    results: list[OpportunityMatchResponse]
