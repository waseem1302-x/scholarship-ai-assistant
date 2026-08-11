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
from app.modules.opportunities.lifecycle import effective_application_window
from app.modules.opportunities.models import (
    ApplicationWindowState,
    EligibilityOperator,
    EligibilityRule,
    EligibilityRuleType,
    FundingType,
    Opportunity,
)
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
    MATCHER_VERSION = "2026-08-11.structured-hard-gates.v1"

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
        rules = (
            [
                self._structured_rule(profile, opportunity, rule)
                for rule in opportunity.eligibility_rules
            ]
            if opportunity.eligibility_rules
            else [
                self._degree_rule(profile, opportunity),
                self._nationality_rule(profile, opportunity),
                self._field_rule(profile, opportunity),
                self._academic_rule(profile, opportunity),
                self._language_rule(profile, opportunity),
            ]
        )
        rules.extend(
            [
                self._deadline_rule(opportunity),
                self._country_preference_rule(profile, opportunity),
                self._funding_rule(profile, opportunity),
            ]
        )
        hard_failures = self._hard_failures(profile, opportunity, rules)
        unknown = [item for rule in rules for item in rule.uncertain]
        failed = [item for rule in rules for item in rule.missing]
        answered = sum(bool(rule.satisfied or rule.missing) for rule in rules)
        completeness = round((answered / len(rules)) * 100) if rules else 0
        if hard_failures:
            score = 0
            fit_score = None
            score_label = "not_eligible"
            eligibility_status = "ineligible"
        else:
            score = round(sum(rule.score for rule in rules))
            fit_score = score
            score_label = self._score_label(score)
            eligibility_status = "eligible" if not unknown else "likely_eligible"
            if not opportunity.eligibility_rules and not profile.target_degree_level:
                eligibility_status = "unknown"
        explanation = MatchExplanation(
            satisfied=[item for rule in rules for item in rule.satisfied],
            missing=[item for rule in rules for item in rule.missing],
            uncertain=[item for rule in rules for item in rule.uncertain],
            next_steps=[item for rule in rules for item in rule.next_steps],
        )
        return OpportunityMatchResponse(
            opportunity=self.opportunity_service.to_summary_response(opportunity),
            match_score=score,
            score_label=score_label,
            eligibility_status=eligibility_status,
            fit_score=fit_score,
            evidence_completeness=completeness,
            confidence="high" if completeness >= 80 else "medium" if completeness >= 50 else "low",
            failed_criteria=failed,
            unknown_criteria=unknown,
            warnings=hard_failures,
            matcher_version=self.MATCHER_VERSION,
            evaluated_at=datetime.now(UTC),
            explanation=explanation,
        )

    def _hard_failures(
        self, profile: StudentProfile, opportunity: Opportunity, rules: list[RuleResult]
    ) -> list[str]:
        failures: list[str] = []
        window = effective_application_window(
            opportunity, self.opportunity_service._official_source(opportunity)
        )
        if window.state in {ApplicationWindowState.CLOSED, ApplicationWindowState.ARCHIVED}:
            failures.append("The application window is closed or archived.")
        if (
            profile.target_degree_level
            and profile.target_degree_level.value != opportunity.degree_level.value
        ):
            failures.append("Target degree does not match this opportunity.")
        if opportunity.eligibility_rules:
            for rule, result in zip(opportunity.eligibility_rules, rules, strict=False):
                if rule.required and result.missing:
                    failures.extend(result.missing)
        else:
            # Legacy text only identifies unmistakable exclusions; ambiguous text remains unknown.
            nationality = _normalize(profile.nationality)
            requirement = _normalize(opportunity.nationality_eligibility)
            if nationality and _explicitly_excludes(nationality, requirement):
                failures.append(
                    "Your nationality is explicitly excluded by the stored requirement."
                )
        return failures

    @staticmethod
    def _structured_rule(
        profile: StudentProfile, opportunity: Opportunity, rule: EligibilityRule
    ) -> RuleResult:
        actual = _profile_value(profile, rule.rule_type)
        label = rule.rule_type.value.replace("_", " ")
        if rule.rule_type is EligibilityRuleType.APPLICATION_WINDOW:
            window = effective_application_window(opportunity, None)
            if window.state in {ApplicationWindowState.CLOSED, ApplicationWindowState.ARCHIVED}:
                return RuleResult(label, 15, 0, missing=["The application window is closed."])
            if window.state in {
                ApplicationWindowState.DEADLINE_UNKNOWN,
                ApplicationWindowState.UPCOMING,
            }:
                return RuleResult(
                    label,
                    15,
                    7.5,
                    uncertain=["Application timing is not currently confirmed open."],
                )
            return RuleResult(label, 15, 15, satisfied=["Application window is currently open."])
        if actual is None:
            return RuleResult(
                label,
                15,
                7.5,
                uncertain=[f"Your {label} is missing, so this rule is unknown."],
                next_steps=[f"Add your {label} to evaluate this requirement."],
            )
        required = rule.value_json
        if rule.rule_type is EligibilityRuleType.CGPA:
            if profile.grading_scale not in {
                Decimal("4"),
                Decimal("4.00"),
                Decimal("5"),
                Decimal("5.00"),
            }:
                return RuleResult(
                    label,
                    15,
                    7.5,
                    uncertain=["Your grading scale is unsupported for this CGPA comparison."],
                )
            actual = (Decimal(str(actual)) / profile.grading_scale) * rule.grading_scale
        satisfied = _compare(actual, required, rule.operator)
        message = (
            f"{label.title()} requirement {'is satisfied' if satisfied else 'is not satisfied'}."
        )
        return RuleResult(
            label,
            15,
            15 if satisfied else 0,
            satisfied=[message] if satisfied else [],
            missing=[] if satisfied else [message],
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


def _profile_value(profile: StudentProfile, rule_type: EligibilityRuleType):
    values = {
        EligibilityRuleType.NATIONALITY: profile.nationality,
        EligibilityRuleType.RESIDENCE: profile.country_of_residence,
        EligibilityRuleType.TARGET_DEGREE: profile.target_degree_level.value
        if profile.target_degree_level
        else None,
        EligibilityRuleType.FIELD: profile.intended_field or profile.academic_discipline,
        EligibilityRuleType.CGPA: profile.cgpa,
        EligibilityRuleType.PERCENTAGE: profile.percentage,
        EligibilityRuleType.IELTS: profile.ielts_score,
        EligibilityRuleType.TOEFL: profile.toefl_score,
        EligibilityRuleType.WORK_EXPERIENCE_MONTHS: profile.work_experience_months,
    }
    return values.get(rule_type)


def _compare(actual, required, operator: EligibilityOperator) -> bool:
    if operator in {EligibilityOperator.IN, EligibilityOperator.NOT_IN}:
        candidates = {_normalize(str(item)) for item in required}
        matches = _normalize(str(actual)) in candidates
        return matches if operator is EligibilityOperator.IN else not matches
    if operator is EligibilityOperator.EQUALS:
        return _normalize(str(actual)) == _normalize(str(required))
    try:
        actual_number = Decimal(str(actual))
        required_number = Decimal(str(required))
    except Exception:
        return False
    if operator is EligibilityOperator.GTE:
        return actual_number >= required_number
    if operator is EligibilityOperator.LTE:
        return actual_number <= required_number
    return False


def _explicitly_excludes(nationality: str, requirement: str) -> bool:
    escaped = re.escape(nationality)
    excluded_pattern = (
        rf"(?:not eligible|ineligible|except|excluding)\s+(?:for\s+)?"
        rf"(?:citizens?\s+of\s+)?{escaped}"
    )
    return bool(
        re.search(excluded_pattern, requirement)
        or re.search(rf"{escaped}\s+(?:applicants?\s+)?(?:are|is)\s+not eligible", requirement)
    )
