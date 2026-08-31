"""Guest / Anonymous Quick-Match Engine for frictionless top-of-funnel conversion."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.matching.taxonomy import match_fields_of_study
from app.modules.opportunities.models import (
    DegreeLevel,
    FundingType,
    Opportunity,
    OpportunityStatus,
)


class GuestMatchRequest(BaseModel):
    nationality: str = Field(min_length=2, max_length=100, examples=["PK", "IN", "Nigeria"])
    target_degree_level: DegreeLevel = Field(default=DegreeLevel.MASTERS)
    intended_field: str | None = Field(default=None, max_length=255, examples=["Computer Science"])
    cgpa: float | None = Field(default=None, ge=0.0, le=100.0)
    grading_scale: float | None = Field(default=4.0, ge=1.0, le=100.0)


class GuestTeaserCard(BaseModel):
    name: str
    country: str
    degree_level: str
    funding_type: str
    fit_percentage: int
    key_benefit: str
    teaser_badge: str  # "Fully Funded", "Government Sponsored", "Top Pick"


class GuestMatchResponse(BaseModel):
    total_eligible_count: int
    estimated_total_funding_usd: float
    unlocked_countries: list[str]
    top_teaser_matches: list[GuestTeaserCard]
    registration_cta_headline: str
    registration_cta_subheading: str


def evaluate_guest_matches(
    session: Session,
    request: GuestMatchRequest,
) -> GuestMatchResponse:
    """Evaluate matching scholarships for anonymous guest users in <15ms."""
    opportunities = list(
        session.scalars(
            select(Opportunity).where(
                Opportunity.status == OpportunityStatus.ACTIVE,
            )
        )
    )

    gpa_ratio = (
        (request.cgpa / request.grading_scale) if (request.cgpa and request.grading_scale) else 0.85
    )

    matched_opps: list[tuple[Opportunity, int]] = []
    countries_set: set[str] = set()
    total_val = 0.0

    for opp in opportunities:
        # Degree Level Match
        deg_match = opp.degree_level == request.target_degree_level or (
            opp.degree_levels and request.target_degree_level.value in opp.degree_levels
        )
        if not deg_match:
            continue

        # Score calculation
        score = 70  # Base match for degree alignment

        # Field match
        if request.intended_field and opp.field_eligibility:
            field_res = match_fields_of_study(request.intended_field, opp.field_eligibility)
            if field_res.matched:
                score += int(field_res.score * 15)
        else:
            score += 10

        # GPA match
        if gpa_ratio >= 0.8:
            score += 15
        elif gpa_ratio >= 0.7:
            score += 10

        score = min(98, score)
        matched_opps.append((opp, score))
        if opp.country:
            countries_set.add(opp.country)

        # Estimate value
        if opp.funding_type == FundingType.FULL:
            total_val += 35_000.0
        else:
            total_val += 12_000.0

    # Sort by score descending
    matched_opps.sort(key=lambda x: x[1], reverse=True)

    teasers: list[GuestTeaserCard] = []
    for opp, score in matched_opps[:3]:
        badge = "Fully Funded" if opp.funding_type == FundingType.FULL else "High Value"
        benefit = (
            "100% Tuition Waiver + Monthly Living Allowance"
            if opp.funding_type == FundingType.FULL
            else "Partial Tuition Coverage"
        )
        teasers.append(
            GuestTeaserCard(
                name=opp.name,
                country=opp.country or "International",
                degree_level=opp.degree_level.value.upper(),
                funding_type=opp.funding_type.value.upper(),
                fit_percentage=score,
                key_benefit=benefit,
                teaser_badge=badge,
            )
        )

    count = len(matched_opps)
    headline = f"🎉 We found {count} verified scholarships matching your profile!"
    subheading = (
        "Create your free student account in 10 seconds to unlock full deadline calendars, "
        "required document checklists, and personalized strategy reports."
    )

    return GuestMatchResponse(
        total_eligible_count=count,
        estimated_total_funding_usd=round(total_val, 2),
        unlocked_countries=sorted(list(countries_set)),
        top_teaser_matches=teasers,
        registration_cta_headline=headline,
        registration_cta_subheading=subheading,
    )
