"""Personalized Scholarship Match Strategy Report Exporter."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.modules.matching.schemas import OpportunityMatchResponse
from app.modules.profiles.models import StudentProfile


class StrategyMatchHighlight(BaseModel):
    rank: int
    opportunity_id: str
    name: str
    provider: str
    country: str
    degree_level: str
    funding_type: str
    fit_score_percentage: int
    is_eligible: bool
    eligibility_summary: str
    deadline_text: str
    official_url: str


class StudentStrategyReport(BaseModel):
    generated_at_utc: str
    student_profile: dict[str, Any]
    total_matches_found: int
    top_tier_matches_count: int
    key_strengths: list[str]
    strategic_recommendations: list[str]
    immediate_action_items: list[str]
    top_matches: list[StrategyMatchHighlight]


def build_match_strategy_report(
    profile: StudentProfile,
    matches: list[OpportunityMatchResponse],
) -> StudentStrategyReport:
    """Build a comprehensive, exportable scholarship strategy report for a student."""
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Profile summary
    profile_summary = {
        "nationality": profile.nationality or profile.nationality_code or "International",
        "target_degree": profile.target_degree_level.value.upper()
        if profile.target_degree_level
        else "MASTERS",
        "field_of_study": profile.intended_field or "General",
        "cgpa": f"{float(profile.cgpa):.2f}" if profile.cgpa is not None else "Not Specified",
        "gpa_scale": f"{float(profile.grading_scale):.1f}"
        if profile.grading_scale is not None
        else "4.0",
    }

    # Top matches sorted by match score descending
    sorted_matches = sorted(
        matches,
        key=lambda m: (m.eligibility_status == "eligible", m.match_score),
        reverse=True,
    )

    top_highlights: list[StrategyMatchHighlight] = []
    top_tier_count = 0

    for idx, match in enumerate(sorted_matches[:10], start=1):
        if match.match_score >= 80:
            top_tier_count += 1

        reasons = []
        if match.explanation and match.explanation.satisfied:
            reasons.extend(match.explanation.satisfied[:2])
        elif match.eligibility_status == "eligible":
            reasons.append("Academic & Citizenship criteria fully satisfied")
        if not reasons:
            reasons.append("Strong overall profile fit")

        deadline = match.opportunity.application_deadline
        deadline_str = deadline.strftime("%B %d, %Y") if deadline else "Check Official Portal"
        official_url = (
            getattr(match.opportunity, "official_source_url", None)
            or "https://scholarship-portal.gov"
        )

        top_highlights.append(
            StrategyMatchHighlight(
                rank=idx,
                opportunity_id=str(match.opportunity.id),
                name=match.opportunity.name,
                provider=match.opportunity.provider_name,
                country=match.opportunity.country or "International",
                degree_level=match.opportunity.degree_level.value.upper(),
                funding_type=match.opportunity.funding_type.value.upper(),
                fit_score_percentage=match.match_score,
                is_eligible=(match.eligibility_status == "eligible"),
                eligibility_summary=" • ".join(reasons),
                deadline_text=deadline_str,
                official_url=official_url,
            )
        )

    # Strategic Insights
    eligible_count = sum(1 for m in matches if m.eligibility_status == "eligible")
    strengths = [
        f"Eligible for {eligible_count} verified global scholarship programmes.",
        "Competitive academic standing in "
        f"'{profile.intended_field or 'selected field'}' with target degree "
        f"{profile_summary['target_degree']}.",
    ]
    if profile.cgpa and profile.cgpa >= Decimal("3.3"):
        strengths.append(
            "Strong CGPA "
            f"({profile_summary['cgpa']}/{profile_summary['gpa_scale']}) exceeds minimum "
            "threshold for top government scholarships."
        )

    recommendations = [
        "Prioritize the Top 3 Tier-1 opportunities (85%+ fit) with approaching closing dates.",
        "Prepare standardized official English test scores (IELTS Academic 6.5+ or TOEFL iBT "
        "90+) to maximize admission acceptance.",
        "Secure 2 strong academic recommendation letters tailored specifically to your chosen "
        "degree track.",
    ]

    action_items = [
        "Request certified, sealed university transcripts from your registrar office.",
        "Draft a compelling 500-word Statement of Purpose / Research Proposal.",
        "Set calendar reminders for top-tier scholarship deadlines 30 days in advance.",
    ]

    return StudentStrategyReport(
        generated_at_utc=now_str,
        student_profile=profile_summary,
        total_matches_found=len(matches),
        top_tier_matches_count=top_tier_count,
        key_strengths=strengths,
        strategic_recommendations=recommendations,
        immediate_action_items=action_items,
        top_matches=top_highlights,
    )
