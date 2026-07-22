import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from app.core.errors import AppError
from app.modules.matching.schemas import (
    MatchExplanation,
    MatchListResponse,
    OpportunityMatchResponse,
)
from app.modules.opportunities.models import FundingType, Opportunity
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.opportunities.service import OpportunityService
from app.modules.profiles.models import StudentProfile, TestStatus
from app.modules.profiles.repository import StudentProfileRepository


@dataclass(frozen=True)
class RuleResult:
    name: str
    weight: int
    score: float
    satisfied: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    uncertain: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


class MatchingService:
    def __init__(
        self,
        profile_repository: StudentProfileRepository,
        opportunity_repository: OpportunityRepository,
    ) -> None:
        self.profile_repository = profile_repository
        self.opportunity_repository = opportunity_repository
        self.opportunity_service = OpportunityService(opportunity_repository.session)

    def match_for_user(self, user_id) -> MatchListResponse:
        profile = self.profile_repository.get_by_user_id(user_id)
        if profile is None:
            raise AppError(
                "profile_required",
                "Create a student profile before requesting opportunity matches",
                400,
            )

        opportunities = self.opportunity_repository.list_public_opportunities()
        results = [self.match_opportunity(profile, opportunity) for opportunity in opportunities]
        results.sort(key=lambda item: item.match_score, reverse=True)
        return MatchListResponse(profile_id=profile.id, results=results)

    def match_opportunity(
        self, profile: StudentProfile, opportunity: Opportunity
    ) -> OpportunityMatchResponse:
        rules = [
            self._degree_rule(profile, opportunity),
            self._nationality_rule(profile, opportunity),
            self._field_rule(profile, opportunity),
            self._academic_rule(profile, opportunity),
            self._deadline_rule(opportunity),
            self._language_rule(profile, opportunity),
            self._country_preference_rule(profile, opportunity),
            self._funding_rule(profile, opportunity),
        ]
        score = round(sum(rule.score for rule in rules))
        explanation = MatchExplanation(
            satisfied=[item for rule in rules for item in rule.satisfied],
            missing=[item for rule in rules for item in rule.missing],
            uncertain=[item for rule in rules for item in rule.uncertain],
            next_steps=[item for rule in rules for item in rule.next_steps],
        )
        return OpportunityMatchResponse(
            opportunity=self.opportunity_service.to_summary_response(opportunity),
            match_score=score,
            score_label=self._score_label(score),
            explanation=explanation,
        )

    @staticmethod
    def _degree_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        if profile.target_degree_level is None:
            return RuleResult(
                "degree",
                20,
                10,
                uncertain=["Target degree level is missing from your profile."],
                next_steps=["Add your target degree level to improve matching."],
            )
        if profile.target_degree_level.value == opportunity.degree_level.value:
            return RuleResult(
                "degree",
                20,
                20,
                satisfied=[f"Target degree matches: {opportunity.degree_level.value}."],
            )
        return RuleResult(
            "degree",
            20,
            0,
            missing=[
                f"Your target degree is {profile.target_degree_level.value}, "
                f"but this opportunity is for {opportunity.degree_level.value}."
            ],
        )

    @staticmethod
    def _nationality_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        requirement = _normalize(opportunity.nationality_eligibility)
        nationality = _normalize(profile.nationality)
        if not requirement:
            return RuleResult(
                "nationality",
                15,
                7.5,
                uncertain=["Nationality eligibility is not structured for this opportunity."],
                next_steps=["Verify nationality eligibility from the official source."],
            )
        if not nationality:
            return RuleResult(
                "nationality",
                15,
                7.5,
                uncertain=["Your nationality is missing from your profile."],
                next_steps=["Add your nationality to check this requirement."],
            )
        if (
            nationality in requirement
            or "international" in requirement
            or "all nationalities" in requirement
        ):
            return RuleResult(
                "nationality",
                15,
                15,
                satisfied=["Nationality appears compatible with the stated eligibility."],
            )
        return RuleResult(
            "nationality",
            15,
            0,
            missing=["Your nationality was not found in the stated eligibility text."],
            next_steps=["Check the official source for country-specific eligibility details."],
        )

    @staticmethod
    def _field_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        requirement = _normalize(opportunity.field_eligibility)
        intended = _normalize(profile.intended_field)
        discipline = _normalize(profile.academic_discipline)
        if not requirement:
            return RuleResult(
                "field",
                15,
                7.5,
                uncertain=["Field eligibility is not structured for this opportunity."],
                next_steps=["Verify eligible fields from the official source."],
            )
        if not intended and not discipline:
            return RuleResult(
                "field",
                15,
                7.5,
                uncertain=["Your intended field or academic discipline is missing."],
                next_steps=["Add your intended field to improve matching."],
            )
        profile_terms = [term for term in [intended, discipline] if term]
        if any(term in requirement or _token_overlap(term, requirement) for term in profile_terms):
            return RuleResult(
                "field",
                15,
                15,
                satisfied=["Your field appears compatible with the stated field eligibility."],
            )
        return RuleResult(
            "field",
            15,
            0,
            missing=["Your field was not found in the stated field eligibility text."],
        )

    @staticmethod
    def _academic_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        requirement = opportunity.minimum_academic_requirement
        if not requirement:
            return RuleResult(
                "academic",
                15,
                7.5,
                uncertain=["Minimum academic requirement is not structured for this opportunity."],
                next_steps=["Verify the minimum academic requirement from the official source."],
            )
        required_cgpa = _extract_required_cgpa(requirement)
        if required_cgpa is None:
            return RuleResult(
                "academic",
                15,
                7.5,
                uncertain=["Academic requirement exists but could not be parsed into a CGPA rule."],
                next_steps=["Review the official academic requirement manually."],
            )
        if profile.cgpa is None or profile.grading_scale is None:
            return RuleResult(
                "academic",
                15,
                7.5,
                uncertain=["Your CGPA or grading scale is missing from your profile."],
                next_steps=["Add CGPA and grading scale to check academic fit."],
            )
        normalized_cgpa = _normalize_cgpa(profile.cgpa, profile.grading_scale)
        if normalized_cgpa >= required_cgpa:
            return RuleResult(
                "academic",
                15,
                15,
                satisfied=[f"Academic requirement appears satisfied: CGPA >= {required_cgpa}."],
            )
        return RuleResult(
            "academic",
            15,
            0,
            missing=[f"Academic requirement may not be satisfied: CGPA below {required_cgpa}."],
        )

    @staticmethod
    def _deadline_rule(opportunity: Opportunity) -> RuleResult:
        if opportunity.application_deadline is None:
            return RuleResult(
                "deadline",
                10,
                5,
                uncertain=["Application deadline is missing."],
                next_steps=["Verify the deadline before planning an application."],
            )
        deadline = _as_utc(opportunity.application_deadline)
        now = datetime.now(UTC)
        days_left = (deadline - now).days
        if days_left < 0:
            return RuleResult(
                "deadline",
                10,
                0,
                missing=["The stored deadline has already passed."],
            )
        if days_left <= 30:
            return RuleResult(
                "deadline",
                10,
                10,
                satisfied=[f"Deadline is upcoming in {days_left} days."],
                next_steps=["Prioritize this application soon because the deadline is close."],
            )
        return RuleResult(
            "deadline",
            10,
            10,
            satisfied=[f"Deadline is open with {days_left} days remaining."],
        )

    @staticmethod
    def _language_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        requirement = _normalize(opportunity.english_language_requirement)
        if not requirement:
            return RuleResult(
                "language",
                10,
                5,
                uncertain=["English-language requirement is not stated in structured data."],
                next_steps=["Check whether IELTS, TOEFL, Duolingo, or a waiver is required."],
            )
        mentions_test = any(
            test in requirement for test in ["ielts", "toefl", "duolingo", "english"]
        )
        if not mentions_test:
            return RuleResult(
                "language",
                10,
                5,
                uncertain=["Language text exists but no supported test rule was detected."],
            )
        if profile.english_test_status is TestStatus.TAKEN and any(
            score is not None
            for score in [profile.ielts_score, profile.toefl_score, profile.duolingo_score]
        ):
            return RuleResult(
                "language",
                10,
                10,
                satisfied=["You have a recorded English test score."],
            )
        if profile.english_test_status is TestStatus.NOT_REQUIRED:
            return RuleResult(
                "language",
                10,
                5,
                uncertain=[
                    "Your profile says English test is not required, "
                    "but this opportunity mentions English."
                ],
                next_steps=["Verify whether a waiver applies to you."],
            )
        return RuleResult(
            "language",
            10,
            0,
            missing=["English test evidence is missing or not yet taken."],
            next_steps=["Confirm IELTS, TOEFL, Duolingo, or waiver requirements."],
        )

    @staticmethod
    def _country_preference_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        countries = [_normalize(country) for country in profile.preferred_destination_countries]
        if not countries:
            return RuleResult(
                "location",
                10,
                5,
                uncertain=["Preferred destination countries are missing from your profile."],
                next_steps=["Add preferred destination countries to improve ranking."],
            )
        if _normalize(opportunity.country) in countries:
            return RuleResult(
                "location",
                10,
                10,
                satisfied=[f"Opportunity country matches your preferences: {opportunity.country}."],
            )
        return RuleResult(
            "location",
            10,
            2,
            missing=[f"{opportunity.country} is not in your preferred destination countries."],
        )

    @staticmethod
    def _funding_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        needs_funding = bool(_normalize(profile.financial_need))
        if not needs_funding:
            return RuleResult(
                "funding",
                5,
                2.5,
                uncertain=[
                    "Financial need or funding preference is not described in your profile."
                ],
            )
        if opportunity.funding_type in {
            FundingType.FULL,
            FundingType.TUITION_ONLY,
            FundingType.STIPEND_ONLY,
        }:
            return RuleResult(
                "funding",
                5,
                5,
                satisfied=[
                    f"Funding type may support your need: {opportunity.funding_type.value}."
                ],
            )
        if opportunity.funding_type is FundingType.PARTIAL:
            return RuleResult(
                "funding",
                5,
                2.5,
                uncertain=["Partial funding may not fully meet your financial need."],
                next_steps=["Check remaining costs before prioritizing this opportunity."],
            )
        return RuleResult(
            "funding",
            5,
            0,
            missing=["Funding coverage is unknown."],
            next_steps=["Verify funding coverage from the official source."],
        )

    @staticmethod
    def _score_label(score: int) -> str:
        if score >= 80:
            return "strong_match"
        if score >= 60:
            return "possible_match"
        if score >= 40:
            return "weak_match"
        return "low_match"


def _normalize(value: str | None) -> str:
    return " ".join(value.lower().strip().split()) if value else ""


def _token_overlap(left: str, right: str) -> bool:
    left_tokens = {token for token in re.split(r"\W+", left) if len(token) >= 4}
    right_tokens = {token for token in re.split(r"\W+", right) if len(token) >= 4}
    return bool(left_tokens & right_tokens)


def _extract_required_cgpa(requirement: str) -> Decimal | None:
    patterns = [
        r"cgpa\s*(?:of|:|>=|at least|minimum)?\s*(\d(?:\.\d+)?)",
        r"(\d(?:\.\d+)?)\s*/\s*4(?:\.0)?",
    ]
    normalized = requirement.lower()
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return Decimal(match.group(1))
    return None


def _normalize_cgpa(cgpa: Decimal, scale: Decimal) -> Decimal:
    if scale == Decimal("4.00") or scale == Decimal("4"):
        return cgpa
    return (cgpa / scale) * Decimal("4.00")


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
