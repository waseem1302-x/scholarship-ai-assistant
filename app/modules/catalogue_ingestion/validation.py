"""Deterministic evidence, domain, funding, date, and catalogue-schema validation."""

from __future__ import annotations

import re
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
    rules = [
        EligibilityRuleCreate(
            rule_type=rule.rule_type,
            operator=rule.operator,
            value=rule.value,
            unit=rule.unit,
            grading_scale=rule.grading_scale,
            required=rule.required,
            confidence=rule.confidence,
        )
        for rule in eligibility.rules
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
            eligibility_warnings=output.warnings + output.unknown_fields,
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
    for name, value in funding_statuses(output):
        if value is not FundingCoverageStatus.UNKNOWN:
            fields.add(f"funding.{name}")
    return fields


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
    return re.sub(r"\s+", " ", value).strip().casefold()
