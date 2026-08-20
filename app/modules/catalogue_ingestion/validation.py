"""Deterministic evidence, domain, funding, date, and catalogue-schema validation."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import ValidationError

from app.modules.catalogue_ingestion.schemas import CatalogueExtractionOutput
from app.modules.opportunities.models import (
    DataConfidence,
    FundingCoverageStatus,
    OpportunityStatus,
    SourceType,
    VerificationStatus,
)
from app.modules.opportunities.schemas import (
    EligibilityRuleCreate,
    OpportunityCreate,
    OpportunityCycleCreate,
    SourceCreate,
)

REQUIRED_EVIDENCE_FIELDS = {
    "identity.name",
    "identity.provider_name",
    "identity.country",
    "study.degree_level",
}

COUNTRY_EVIDENCE_ALIASES = {
    "united kingdom": ("uk", "u.k."),
    "united states": (
        "united states of america",
        "usa",
        "u.s.a.",
        "u.s.",
    ),
}

ACADEMIC_REQUIREMENT_CUES = (
    "must",
    "required",
    "requires",
    "requirement",
    "minimum",
    "at least",
    "should have",
    "need to have",
    "needs to have",
    "eligible if",
)

ACADEMIC_QUALIFICATION_MARKERS = (
    "degree",
    "bachelor",
    "master",
    "gpa",
    "grade",
    "percentage",
    "academic qualification",
    "qualification",
    "equivalent",
)

ACADEMIC_NEGATION_CUES = (
    "not required",
    "does not require",
    "do not require",
    "no minimum",
    "no requirement",
    "not mandatory",
    "without requiring",
)

TUITION_NEGATION_CUES = (
    "not covered",
    "does not cover",
    "do not cover",
    "not paid",
    "not included",
    "excluded",
)

TUITION_PARTIAL_CUES = (
    "partially covered",
    "partly covered",
    "partial coverage",
    "not fully covered",
)

TUITION_CONFIRMED_CUES = (
    "covered",
    "coverage",
    "paid",
    "waived",
    "waiver",
    "funded",
    "full tuition",
)


@dataclass(frozen=True)
class ValidatedProposal:
    payload: OpportunityCreate | None
    errors: list[str]


def validate_and_build_proposal(
    output: CatalogueExtractionOutput,
    *,
    source_url: str,
    source_text: str,
    source_title: str,
    content_hash: str,
    trust_tier: int,
) -> ValidatedProposal:
    errors = evidence_errors(output, source_url=source_url, source_text=source_text)
    errors.extend(semantic_evidence_errors(output, source_text=source_text))
    if output.conflicts:
        errors.append("unresolved official-source conflicts must be reviewed")

    identity = output.identity
    study = output.study
    required = {
        "identity.name": identity.name,
        "identity.provider_name": identity.provider_name,
        "identity.country": identity.country,
        "study.degree_level": study.degree_level,
    }
    errors.extend(f"{field} is required" for field, value in required.items() if value is None)
    if errors:
        return ValidatedProposal(None, sorted(set(errors)))

    evidence_excerpt = " ".join(
        evidence.excerpt.strip()
        for evidence in output.evidence
        if evidence.basis != "unknown" and evidence.excerpt.strip()
    )[:12_000]
    if len(evidence_excerpt) < 20:
        return ValidatedProposal(None, ["official source evidence excerpt is insufficient"])

    # The existing catalogue's publication policy recognizes SourceType.OFFICIAL
    # as the reviewed trust gate. The staging record preserves the finer trust tier.
    source_type = SourceType.OFFICIAL
    application = output.application
    funding = output.funding
    eligibility = output.eligibility
    omitted_non_mandatory_rules = sum(not rule.required for rule in eligibility.rules)
    rules = [
        EligibilityRuleCreate(
            rule_type=rule.rule_type,
            operator=rule.operator,
            value=rule.value,
            unit=rule.unit,
            grading_scale=rule.grading_scale,
            required=True,
            confidence=rule.confidence,
        )
        for rule in eligibility.rules
        if rule.required
    ]
    try:
        payload = OpportunityCreate(
            name=identity.name,
            provider_name=identity.provider_name,
            provider_canonical_id=identity.provider_canonical_id,
            programme_family_id=identity.programme_family_id,
            cycle_id=study.cycle_id,
            provider_website_url=identity.provider_website_url,
            university_name=identity.university_name,
            university_website_url=identity.university_website_url,
            country=identity.country,
            degree_level=study.degree_level,
            field_eligibility=study.field_eligibility,
            nationality_eligibility=eligibility.nationality_eligibility,
            application_opening_date=application.application_opening_date,
            application_deadline=application.application_deadline,
            intake_year=study.intake_year,
            funding_type=funding.funding_type,
            funding_policy=funding.funding_policy,
            tuition_coverage_status=funding.tuition_coverage_status,
            stipend_coverage_status=funding.stipend_coverage_status,
            accommodation_coverage_status=funding.accommodation_coverage_status,
            travel_coverage_status=funding.travel_coverage_status,
            insurance_coverage_status=funding.insurance_coverage_status,
            fees_coverage_status=funding.fees_coverage_status,
            application_fee_status=funding.application_fee_status,
            tuition_coverage=funding.tuition_coverage,
            monthly_stipend_amount=funding.monthly_stipend_amount,
            monthly_stipend_currency=funding.monthly_stipend_currency,
            accommodation_coverage=funding.accommodation_coverage,
            travel_allowance=funding.travel_allowance,
            health_insurance=funding.health_insurance,
            application_fee_info=funding.application_fee_info,
            english_language_requirement=eligibility.english_language_requirement,
            standardized_test_requirement=eligibility.standardized_test_requirement,
            minimum_academic_requirement=eligibility.minimum_academic_requirement,
            required_documents=application.required_documents,
            application_method=application.application_method,
            application_url=application.application_url,
            status=OpportunityStatus.DRAFT,
            data_confidence=DataConfidence.MEDIUM,
            notes="AI-assisted proposal; official-source evidence and human review required.",
            eligibility_warnings=(
                output.warnings
                + output.unknown_fields
                + (
                    [
                        "Non-mandatory AI-extracted eligibility rules were omitted "
                        "from structured matching."
                    ]
                    if omitted_non_mandatory_rules
                    else []
                )
            ),
            eligibility_rules=rules,
            application_cycles=[
                OpportunityCycleCreate(
                    intake_year=study.intake_year,
                    application_opening_date=application.application_opening_date,
                    application_deadline=application.application_deadline,
                    timezone=application.timezone or "UTC",
                    is_rolling=application.is_rolling,
                )
            ],
            source=SourceCreate(
                url=source_url,
                source_type=source_type,
                title=source_title[:255],
                content_hash=content_hash,
                relevant_excerpt=evidence_excerpt,
                verification_status=VerificationStatus.NEEDS_REVIEW,
            ),
        )
    except ValidationError as exc:
        return ValidatedProposal(
            None,
            [
                ".".join(str(part) for part in error["loc"]) + ": " + error["msg"]
                for error in exc.errors()
            ],
        )
    return ValidatedProposal(payload, [])


def evidence_errors(
    output: CatalogueExtractionOutput, *, source_url: str, source_text: str
) -> list[str]:
    normalized_text = _normalize(source_text)
    errors: list[str] = []
    supported_fields: set[str] = set()
    for evidence in output.evidence:
        if evidence.source_url != source_url:
            errors.append(
                f"{evidence.field_path}: evidence URL does not match fetched official source"
            )
        if evidence.basis == "unknown":
            continue
        if len(evidence.excerpt.strip()) < 5 or _normalize(evidence.excerpt) not in normalized_text:
            errors.append(f"{evidence.field_path}: excerpt was not found in fetched source text")
            continue
        supported_fields.add(evidence.field_path)
    for field in sorted(required_evidence_fields(output) - supported_fields):
        errors.append(f"{field}: field-level official-source evidence is required")
    return errors


def required_evidence_fields(output: CatalogueExtractionOutput) -> set[str]:
    fields = set(REQUIRED_EVIDENCE_FIELDS)
    if output.application.application_opening_date is not None:
        fields.add("application.application_opening_date")
    if output.application.application_deadline is not None:
        fields.add("application.application_deadline")
    if output.application.application_url is not None:
        fields.add("application.application_url")
    if output.eligibility.minimum_academic_requirement is not None:
        fields.add("eligibility.minimum_academic_requirement")
    for name, value in funding_statuses(output):
        if value is not FundingCoverageStatus.UNKNOWN:
            fields.add(f"funding.{name}")
    return fields


def semantic_evidence_errors(
    output: CatalogueExtractionOutput,
    *,
    source_text: str,
) -> list[str]:
    """Reject high-risk claims whose cited excerpt does not support the value."""

    normalized_source = _normalize(source_text)

    def excerpts(field_path: str) -> list[str]:
        return [
            _normalize(evidence.excerpt)
            for evidence in output.evidence
            if evidence.field_path == field_path
            and evidence.basis != "unknown"
            and len(evidence.excerpt.strip()) >= 5
            and _normalize(evidence.excerpt) in normalized_source
        ]

    errors: list[str] = []

    country = output.identity.country
    if country is not None:
        normalized_country = _normalize(country)
        country_terms = {
            normalized_country,
            *COUNTRY_EVIDENCE_ALIASES.get(normalized_country, ()),
        }
        country_excerpts = excerpts("identity.country")

        if not any(
            _contains_term(excerpt, term) for excerpt in country_excerpts for term in country_terms
        ):
            errors.append(
                "identity.country: evidence does not explicitly name the claimed study country"
            )

    tuition_status = output.funding.tuition_coverage_status
    if tuition_status is not FundingCoverageStatus.UNKNOWN:
        tuition_excerpts = excerpts("funding.tuition_coverage_status")
        if not any(
            _tuition_status_supported(tuition_status, excerpt) for excerpt in tuition_excerpts
        ):
            errors.append(
                "funding.tuition_coverage_status: evidence does not support "
                "the claimed tuition coverage status"
            )

    if output.eligibility.minimum_academic_requirement is not None:
        academic_excerpts = excerpts("eligibility.minimum_academic_requirement")

        explicit_requirement = any(
            _academic_requirement_supported(excerpt) for excerpt in academic_excerpts
        )

        if not explicit_requirement:
            errors.append(
                "eligibility.minimum_academic_requirement: evidence does not "
                "state an explicit academic requirement"
            )

    return errors


def _tuition_status_supported(
    status: FundingCoverageStatus,
    excerpt: str,
) -> bool:
    if not _contains_term(excerpt, "tuition"):
        return False

    status_value = status.value

    has_negative = any(cue in excerpt for cue in TUITION_NEGATION_CUES)
    has_partial = any(cue in excerpt for cue in TUITION_PARTIAL_CUES)

    if status_value == "not_covered":
        return has_negative

    if status_value == "partial":
        return has_partial

    if status_value == "confirmed":
        if has_negative or has_partial:
            return False
        return any(cue in excerpt for cue in TUITION_CONFIRMED_CUES)

    return False


def _academic_requirement_supported(excerpt: str) -> bool:
    if any(cue in excerpt for cue in ACADEMIC_NEGATION_CUES):
        return False

    # Also reject forms such as "No bachelor's degree is required".
    if re.search(
        r"(?<!\w)no(?!\w).{0,80}"
        r"(?:degree|bachelor|master|gpa|grade|qualification)",
        excerpt,
    ):
        return False

    return any(cue in excerpt for cue in ACADEMIC_REQUIREMENT_CUES) and any(
        marker in excerpt for marker in ACADEMIC_QUALIFICATION_MARKERS
    )


def _contains_term(text: str, term: str) -> bool:
    normalized_term = _normalize(term)
    return (
        re.search(
            rf"(?<!\w){re.escape(normalized_term)}(?!\w)",
            text,
        )
        is not None
    )


def funding_statuses(
    output: CatalogueExtractionOutput,
) -> Iterable[tuple[str, FundingCoverageStatus]]:
    funding = output.funding
    return (
        ("tuition_coverage_status", funding.tuition_coverage_status),
        ("stipend_coverage_status", funding.stipend_coverage_status),
        ("accommodation_coverage_status", funding.accommodation_coverage_status),
        ("travel_coverage_status", funding.travel_coverage_status),
        ("insurance_coverage_status", funding.insurance_coverage_status),
        ("fees_coverage_status", funding.fees_coverage_status),
    )


def _normalize(value: str) -> str:
    """Canonicalize harmless text-encoding differences for evidence comparison only."""

    normalized = unicodedata.normalize("NFKC", value)

    # Azure has been observed returning an apostrophe as the exact two-character
    # sequence U+0003 followed by "9". Normalize only that specific corruption;
    # do not treat arbitrary control characters as punctuation.
    normalized = normalized.replace("\x039", "'")

    normalized = normalized.translate(
        str.maketrans(
            {
                "\u2018": "'",
                "\u2019": "'",
                "\u201b": "'",
                "\u02bc": "'",
                "\u00b4": "'",
                "\u0060": "'",
                "\x19": "'",
                "\u2013": "-",
                "\u2014": "-",
                "\u2212": "-",
                "\u00a0": " ",
            }
        )
    )
    return re.sub(r"\s+", " ", normalized).strip().casefold()
