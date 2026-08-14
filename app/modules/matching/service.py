import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.errors import AppError
from app.modules.matching.models import (
    MatchEvaluation,
    MatchEvaluationResult,
    MatchRuleOutcome,
)
from app.modules.matching.repository import MatchEvaluationRepository
from app.modules.matching.schemas import (
    MatchExplanation,
    MatchListResponse,
    OpportunityMatchResponse,
)
from app.modules.opportunities.lifecycle import effective_application_window
from app.modules.opportunities.models import (
    ApplicationWindowState,
    DataConfidence,
    EligibilityOperator,
    EligibilityRule,
    EligibilityRuleType,
    FundingClassification,
    Opportunity,
    Source,
    SourceType,
    VerificationStatus,
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
    category: str = "eligibility"
    satisfied: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    uncertain: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


class MatchingService:
    MATCHER_VERSION = "2026-08-14.separated-fit-confidence.v1"

    def __init__(
        self,
        profile_repository: StudentProfileRepository,
        opportunity_repository: OpportunityRepository,
    ) -> None:
        self.profile_repository = profile_repository
        self.opportunity_repository = opportunity_repository
        self.opportunity_service = OpportunityService(opportunity_repository.session)
        self.evaluation_repository = MatchEvaluationRepository(opportunity_repository.session)

    def match_for_user(self, user_id) -> MatchListResponse:
        profile = self.profile_repository.get_by_user_id(user_id)
        if profile is None:
            raise AppError(
                "profile_required",
                "Create a student profile before requesting opportunity matches",
                400,
            )

        evaluated_at = datetime.now(UTC)
        profile_snapshot = _matching_profile_snapshot(profile)
        previous = self.evaluation_repository.latest_for_user(user_id)
        evaluation = MatchEvaluation(
            user_id=user_id,
            profile_id=profile.id,
            supersedes_evaluation_id=previous.id if previous else None,
            matcher_version=self.MATCHER_VERSION,
            evaluated_at=evaluated_at,
            expires_at=evaluated_at + timedelta(days=365),
            profile_snapshot_json=profile_snapshot,
            profile_snapshot_hash=_snapshot_hash(profile_snapshot),
        )
        self.evaluation_repository.add(evaluation)

        opportunities = self._candidate_opportunities(
            profile, self.opportunity_repository.list_public_opportunities()
        )
        evaluated_results = [
            self._match_opportunity_with_rules(profile, opportunity, evaluated_at)
            for opportunity in opportunities
        ]
        evaluated_results.sort(
            key=lambda item: (
                item[0].match_score,
                item[0].preference_fit if item[0].preference_fit is not None else -1,
                item[0].evidence_completeness,
            ),
            reverse=True,
        )
        for rank, (result, rules, opportunity) in enumerate(evaluated_results, start=1):
            evaluation.results.append(
                self._evaluation_result(
                    result=result,
                    rules=rules,
                    opportunity=opportunity,
                    rank=rank,
                )
            )
        self.opportunity_repository.session.commit()
        return MatchListResponse(
            profile_id=profile.id,
            evaluation_id=evaluation.id,
            results=[item[0] for item in evaluated_results],
        )

    def match_opportunity(
        self, profile: StudentProfile, opportunity: Opportunity
    ) -> OpportunityMatchResponse:
        result, _, _ = self._match_opportunity_with_rules(profile, opportunity, datetime.now(UTC))
        return result

    def _match_opportunity_with_rules(
        self,
        profile: StudentProfile,
        opportunity: Opportunity,
        evaluated_at: datetime,
    ) -> tuple[OpportunityMatchResponse, list[RuleResult], Opportunity]:
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
        eligibility_rules = [rule for rule in rules if rule.category == "eligibility"]
        preference_rules = [rule for rule in rules if rule.category == "preference"]
        missing_information = [item for rule in rules for item in rule.uncertain]
        eligibility_failures = [item for rule in eligibility_rules for item in rule.missing]
        preference_mismatches = [item for rule in preference_rules for item in rule.missing]
        answered = sum(bool(rule.satisfied or rule.missing) for rule in rules)
        completeness = round((answered / len(rules)) * 100) if rules else 0
        profile_completeness = _matching_profile_completeness(profile)
        source = self.opportunity_service._official_source(opportunity)
        confidence, confidence_factors = self._confidence(
            opportunity=opportunity,
            source=source,
            evidence_completeness=completeness,
            missing_information=missing_information,
            has_structured_rules=bool(opportunity.eligibility_rules),
        )
        if hard_failures:
            score = 0
            fit_score = None
            score_label = "not_eligible"
            eligibility_status = "ineligible"
        else:
            score = _weighted_percent(eligibility_rules)
            fit_score = score
            score_label = self._score_label(score)
            eligibility_status = (
                "potentially_eligible"
                if not missing_information and opportunity.eligibility_rules
                else "likely_eligible"
            )
            if not opportunity.eligibility_rules:
                eligibility_status = "unknown"
        preference_fit = _preference_fit(preference_rules)
        explanation = MatchExplanation(
            satisfied=[item for rule in rules for item in rule.satisfied],
            missing=[item for rule in rules for item in rule.missing],
            uncertain=[item for rule in rules for item in rule.uncertain],
            next_steps=[item for rule in rules for item in rule.next_steps],
        )
        response = OpportunityMatchResponse(
            opportunity=self.opportunity_service.to_summary_response(opportunity),
            match_score=score,
            score_label=score_label,
            eligibility_status=eligibility_status,
            fit_score=fit_score,
            preference_fit=preference_fit,
            evidence_completeness=completeness,
            profile_completeness=profile_completeness,
            confidence=confidence,
            confidence_factors=confidence_factors,
            eligibility_failures=eligibility_failures,
            preference_mismatches=preference_mismatches,
            missing_information=missing_information,
            failed_criteria=eligibility_failures,
            unknown_criteria=missing_information,
            warnings=hard_failures,
            matcher_version=self.MATCHER_VERSION,
            evaluated_at=evaluated_at,
            explanation=explanation,
        )
        return response, rules, opportunity

    def _evaluation_result(
        self,
        *,
        result: OpportunityMatchResponse,
        rules: list[RuleResult],
        opportunity: Opportunity,
        rank: int,
    ) -> MatchEvaluationResult:
        source = self.opportunity_service._official_source(opportunity)
        window = effective_application_window(opportunity, source)
        excerpt = _latest_excerpt(source)
        stored = MatchEvaluationResult(
            opportunity_id=opportunity.id,
            opportunity_cycle_id=window.cycle.id if window.cycle else None,
            source_id=source.id if source else None,
            source_excerpt_id=excerpt.id if excerpt else None,
            rank=rank,
            match_score=result.match_score,
            fit_score=result.fit_score,
            score_label=result.score_label,
            eligibility_status=result.eligibility_status,
            confidence=result.confidence,
            evidence_completeness=result.evidence_completeness,
            warnings_json=result.warnings,
            opportunity_snapshot_json=result.opportunity.model_dump(mode="json"),
            source_snapshot_json=_source_snapshot(source, excerpt),
        )
        structured_rules = list(opportunity.eligibility_rules)
        for index, rule in enumerate(rules):
            stored.rule_outcomes.append(
                MatchRuleOutcome(
                    eligibility_rule_id=(
                        structured_rules[index].id if index < len(structured_rules) else None
                    ),
                    rule_name=rule.name,
                    outcome=_rule_outcome(rule),
                    reason_code=_rule_reason_code(rule),
                    profile_fields_json=_profile_fields_for_rule(rule.name),
                    comparison_json={
                        "weight": rule.weight,
                        "awarded_score": rule.score,
                        "category": rule.category,
                    },
                    message=_rule_message(rule),
                    confidence=result.confidence,
                    next_actions_json=rule.next_steps,
                    source_id=(
                        structured_rules[index].source_id
                        if index < len(structured_rules)
                        else source.id
                        if source
                        else None
                    ),
                    source_excerpt_id=excerpt.id if excerpt else None,
                )
            )
        return stored

    @staticmethod
    def _candidate_opportunities(
        profile: StudentProfile, opportunities: list[Opportunity]
    ) -> list[Opportunity]:
        if profile.target_degree_level is None:
            return opportunities
        return [
            opportunity
            for opportunity in opportunities
            if opportunity.degree_level.value == profile.target_degree_level.value
        ]

    @staticmethod
    def _confidence(
        *,
        opportunity: Opportunity,
        source: Source | None,
        evidence_completeness: int,
        missing_information: list[str],
        has_structured_rules: bool,
    ) -> tuple[str, list[str]]:
        score = 0
        factors: list[str] = []
        if evidence_completeness >= 80:
            score += 2
            factors.append("Most evaluated requirements have known outcomes.")
        elif evidence_completeness >= 50:
            score += 1
            factors.append("Some evaluated requirements still need confirmation.")
        else:
            factors.append("Many evaluated requirements are unknown.")
        if has_structured_rules:
            score += 1
            factors.append("Official requirements include structured rules.")
        else:
            factors.append("Major eligibility requirements are not fully structured.")
        if source is not None and source.source_type is SourceType.OFFICIAL:
            score += 1
            factors.append("The selected source is official.")
        if (
            source is not None
            and source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
        ):
            score += 1
            factors.append("The official source is verified.")
        if source is not None and source.last_verified_at is not None:
            age_days = (datetime.now(UTC) - _as_utc(source.last_verified_at)).days
            if age_days <= 180:
                score += 1
                factors.append("The source verification is recent.")
            else:
                factors.append("The source verification is older than 180 days.")
        else:
            factors.append("Source freshness is unknown.")
        if opportunity.data_confidence is DataConfidence.LOW:
            score -= 1
            factors.append("The opportunity is marked low confidence.")
        if missing_information:
            score -= 1
            factors.append("Missing profile or source data lowers confidence.")
        if score >= 5:
            return "high", factors
        if score >= 3:
            return "medium", factors
        return "low", factors

    def _hard_failures(
        self,
        profile: StudentProfile,
        opportunity: Opportunity,
        rules: list[RuleResult],
    ) -> list[str]:
        failures: list[str] = []
        window = effective_application_window(
            opportunity, self.opportunity_service._official_source(opportunity)
        )
        if window.state in {
            ApplicationWindowState.CLOSED,
            ApplicationWindowState.ARCHIVED,
        }:
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
        return failures

    @staticmethod
    def _structured_rule(
        profile: StudentProfile,
        opportunity: Opportunity,
        rule: EligibilityRule,
    ) -> RuleResult:
        label = rule.rule_type.value.replace("_", " ")
        actual = _profile_value(profile, rule.rule_type)
        if rule.rule_type is EligibilityRuleType.APPLICATION_WINDOW:
            window = effective_application_window(opportunity, None)
            actual = window.state.value
            if window.state is ApplicationWindowState.DEADLINE_UNKNOWN:
                return _unknown_rule(
                    label,
                    "The official application window is not confirmed.",
                    "Verify the current application window from the official source.",
                )
        if actual is None or actual == []:
            return RuleResult(
                label,
                15,
                0,
                uncertain=[f"Your {label} is missing, so this rule is unknown."],
                next_steps=[f"Add your {label} to evaluate this requirement."],
            )
        if rule.rule_type is EligibilityRuleType.CGPA:
            if profile.grading_scale is None or rule.grading_scale is None:
                return _unknown_rule(
                    label,
                    "A grading scale is required for this CGPA comparison.",
                    "Add or verify the grading scale used for your CGPA.",
                )
            if Decimal(str(profile.grading_scale)) != Decimal(str(rule.grading_scale)):
                return _unknown_rule(
                    label,
                    "CGPA scales differ and no documented equivalence is available.",
                    "Verify an official grading equivalence before relying on this comparison.",
                )
            actual = Decimal(str(actual))
        if (
            rule.rule_type
            in {
                EligibilityRuleType.ENGLISH_TEST_STATUS,
                EligibilityRuleType.GRE_STATUS,
            }
            and actual == TestStatus.NOT_REQUIRED.value
            and not _compare(actual, rule.value_json, rule.operator)
        ):
            return _unknown_rule(
                label,
                "Your profile records a possible test waiver that must be confirmed.",
                "Confirm the waiver with the official source.",
            )
        satisfied = _compare(actual, rule.value_json, rule.operator)
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
                0,
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
        return _unstructured_rule("nationality")

    @staticmethod
    def _field_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        return _unstructured_rule("field")

    @staticmethod
    def _academic_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        return _unstructured_rule("academic")

    @staticmethod
    def _deadline_rule(opportunity: Opportunity) -> RuleResult:
        if opportunity.application_deadline is None:
            return RuleResult(
                "deadline",
                10,
                0,
                category="freshness",
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
                category="freshness",
                missing=["The stored deadline has already passed."],
            )
        if days_left <= 30:
            return RuleResult(
                "deadline",
                10,
                10,
                category="freshness",
                satisfied=[f"Deadline is upcoming in {days_left} days."],
                next_steps=["Prioritize this application soon because the deadline is close."],
            )
        return RuleResult(
            "deadline",
            10,
            10,
            category="freshness",
            satisfied=[f"Deadline is open with {days_left} days remaining."],
        )

    @staticmethod
    def _language_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        return _unstructured_rule("English-language")

    @staticmethod
    def _country_preference_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        countries = [_normalize(country) for country in profile.preferred_destination_countries]
        if not countries:
            return RuleResult(
                "location",
                10,
                0,
                category="preference",
                uncertain=["Preferred destination countries are missing from your profile."],
                next_steps=["Add preferred destination countries to improve ranking."],
            )
        if _normalize(opportunity.country) in countries:
            return RuleResult(
                "location",
                10,
                10,
                category="preference",
                satisfied=[f"Opportunity country matches your preferences: {opportunity.country}."],
            )
        return RuleResult(
            "location",
            10,
            0,
            category="preference",
            missing=[f"{opportunity.country} is not in your preferred destination countries."],
        )

    @staticmethod
    def _funding_rule(profile: StudentProfile, opportunity: Opportunity) -> RuleResult:
        needs_funding = bool(_normalize(profile.financial_need))
        if not needs_funding:
            return RuleResult(
                "funding",
                5,
                0,
                category="preference",
                uncertain=[
                    "Financial need or funding preference is not described in your profile."
                ],
            )
        if opportunity.funding_classification is FundingClassification.FULLY_FUNDED:
            return RuleResult(
                "funding",
                5,
                5,
                category="preference",
                satisfied=["All documented funding components are confirmed."],
            )
        if opportunity.funding_classification is FundingClassification.PARTIAL:
            return RuleResult(
                "funding",
                5,
                0,
                category="preference",
                uncertain=["Confirmed funding components may not fully meet your financial need."],
                next_steps=["Check remaining costs before prioritizing this opportunity."],
            )
        return RuleResult(
            "funding",
            5,
            0,
            category="preference",
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


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _profile_value(profile: StudentProfile, rule_type: EligibilityRuleType):
    values = {
        EligibilityRuleType.NATIONALITY: profile.nationality,
        EligibilityRuleType.RESIDENCE: profile.country_of_residence,
        EligibilityRuleType.TARGET_DEGREE: profile.target_degree_level.value
        if profile.target_degree_level
        else None,
        EligibilityRuleType.FIELD: [
            field for field in [profile.intended_field, profile.academic_discipline] if field
        ],
        EligibilityRuleType.CGPA: profile.cgpa,
        EligibilityRuleType.PERCENTAGE: profile.percentage,
        EligibilityRuleType.IELTS: profile.ielts_score,
        EligibilityRuleType.TOEFL: profile.toefl_score,
        EligibilityRuleType.WORK_EXPERIENCE_MONTHS: profile.work_experience_months,
        EligibilityRuleType.STUDY_MODE: (
            profile.preferred_study_mode.value if profile.preferred_study_mode else None
        ),
        EligibilityRuleType.INTAKE_YEAR: profile.target_intake_year,
        EligibilityRuleType.CURRENT_EDUCATION_LEVEL: (
            profile.current_education_level.value if profile.current_education_level else None
        ),
        EligibilityRuleType.ENGLISH_TEST_STATUS: profile.english_test_status.value,
        EligibilityRuleType.GRE_STATUS: profile.gre_status.value,
        EligibilityRuleType.DUOLINGO: profile.duolingo_score,
        EligibilityRuleType.GRE: profile.gre_score,
    }
    return values.get(rule_type)


def _compare(actual, required, operator: EligibilityOperator) -> bool:
    if isinstance(actual, list):
        if operator is EligibilityOperator.NOT_IN:
            return all(_compare(value, required, operator) for value in actual)
        return any(_compare(value, required, operator) for value in actual)
    if actual == "any" and operator in {
        EligibilityOperator.EQUALS,
        EligibilityOperator.IN,
    }:
        return True
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


def _weighted_percent(rules: list[RuleResult]) -> int:
    total_weight = sum(rule.weight for rule in rules)
    if total_weight == 0:
        return 0
    return round((sum(rule.score for rule in rules) / total_weight) * 100)


def _preference_fit(rules: list[RuleResult]) -> int | None:
    known_rules = [rule for rule in rules if rule.satisfied or rule.missing]
    if not known_rules:
        return None
    return _weighted_percent(known_rules)


def _matching_profile_completeness(profile: StudentProfile) -> int:
    fields = [
        profile.nationality or profile.nationality_code,
        profile.country_of_residence or profile.country_of_residence_code,
        _snapshot_value(profile.current_education_level),
        _snapshot_value(profile.target_degree_level),
        profile.intended_field or profile.intended_field_taxonomy or profile.academic_discipline,
        profile.cgpa or profile.percentage,
        _snapshot_value(profile.english_test_status)
        if profile.english_test_status is not TestStatus.UNKNOWN
        else None,
        profile.preferred_destination_countries or profile.preferred_destination_country_codes,
        profile.financial_need,
        profile.target_intake or profile.target_intake_year,
    ]
    completed = sum(value is not None and value != [] and value != "" for value in fields)
    return round((completed / len(fields)) * 100)


def _unknown_rule(
    label: str, message: str, next_step: str, *, category: str = "eligibility"
) -> RuleResult:
    return RuleResult(label, 15, 0, category=category, uncertain=[message], next_steps=[next_step])


def _unstructured_rule(label: str) -> RuleResult:
    return _unknown_rule(
        label,
        f"{label.title()} eligibility is not yet structured for this opportunity.",
        "Verify this requirement from the official source.",
    )


def _matching_profile_snapshot(profile: StudentProfile) -> dict[str, object]:
    """Return only profile inputs used for matching; never account or session data."""
    return {
        "schema_version": 1,
        "identity": {
            "nationality": profile.nationality,
            "country_of_residence": profile.country_of_residence,
        },
        "education": {
            "current_education_level": _snapshot_value(profile.current_education_level),
            "target_degree_level": _snapshot_value(profile.target_degree_level),
            "intended_field": profile.intended_field,
            "academic_discipline": profile.academic_discipline,
            "cgpa": _snapshot_value(profile.cgpa),
            "percentage": _snapshot_value(profile.percentage),
            "grading_scale": _snapshot_value(profile.grading_scale),
        },
        "test_evidence": {
            "english_test_status": _snapshot_value(profile.english_test_status),
            "ielts_score": _snapshot_value(profile.ielts_score),
            "toefl_score": profile.toefl_score,
            "duolingo_score": profile.duolingo_score,
            "gre_status": _snapshot_value(profile.gre_status),
            "gre_score": profile.gre_score,
        },
        "experience": {"work_experience_months": profile.work_experience_months},
        "preferences": {
            "financial_need": profile.financial_need,
            "preferred_destination_countries": profile.preferred_destination_countries,
            "preferred_study_mode": _snapshot_value(profile.preferred_study_mode),
            "target_intake": profile.target_intake,
            "target_intake_year": profile.target_intake_year,
        },
    }


def _snapshot_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    return getattr(value, "value", value)


def _snapshot_hash(snapshot: dict[str, object]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _latest_excerpt(source):
    if source is None or not source.excerpts:
        return None
    return max(source.excerpts, key=lambda excerpt: excerpt.captured_at)


def _source_snapshot(source, excerpt) -> dict[str, object] | None:
    if source is None:
        return None
    return {
        "source_id": str(source.id),
        "url": source.url,
        "content_hash": source.content_hash,
        "verification_status": source.verification_status.value,
        "last_verified_at": (
            source.last_verified_at.isoformat() if source.last_verified_at else None
        ),
        "excerpt_id": str(excerpt.id) if excerpt else None,
        "excerpt_content_hash": excerpt.content_hash if excerpt else None,
    }


def _rule_outcome(rule: RuleResult) -> str:
    if rule.satisfied:
        return "satisfied"
    if rule.missing:
        return "failed"
    return "unknown"


def _rule_reason_code(rule: RuleResult) -> str:
    normalized_name = re.sub(r"[^a-z0-9]+", "_", rule.name.lower()).strip("_")
    return f"match.{normalized_name}.{_rule_outcome(rule)}"


def _rule_message(rule: RuleResult) -> str:
    return (rule.satisfied or rule.missing or rule.uncertain or ["Rule evaluated."])[0]


def _profile_fields_for_rule(rule_name: str) -> list[str]:
    fields = {
        "degree": ["target_degree_level"],
        "target degree": ["target_degree_level"],
        "nationality": ["nationality"],
        "residence": ["country_of_residence"],
        "field": ["intended_field", "academic_discipline"],
        "academic": ["cgpa", "grading_scale"],
        "cgpa": ["cgpa", "grading_scale"],
        "percentage": ["percentage"],
        "ielts": ["ielts_score", "english_test_status"],
        "toefl": ["toefl_score", "english_test_status"],
        "work experience months": ["work_experience_months"],
        "language": [
            "english_test_status",
            "ielts_score",
            "toefl_score",
            "duolingo_score",
        ],
        "location": ["preferred_destination_countries"],
        "funding": ["financial_need"],
    }
    return fields.get(rule_name, [])
