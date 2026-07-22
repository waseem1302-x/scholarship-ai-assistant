import uuid

from pydantic import BaseModel

from app.modules.opportunities.schemas import OpportunitySummaryResponse


class MatchExplanation(BaseModel):
    satisfied: list[str]
    missing: list[str]
    uncertain: list[str]
    next_steps: list[str]


class OpportunityMatchResponse(BaseModel):
    opportunity: OpportunitySummaryResponse
    match_score: int
    score_label: str
    explanation: MatchExplanation
    disclaimer: str = (
        "This score ranks profile fit against stated requirements. It is not a probability "
        "of admission, scholarship selection, or visa approval."
    )


class MatchListResponse(BaseModel):
    profile_id: uuid.UUID
    results: list[OpportunityMatchResponse]
