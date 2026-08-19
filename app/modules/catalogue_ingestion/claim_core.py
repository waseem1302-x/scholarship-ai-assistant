"""Pure PR6 source-claim contracts for the highest-risk decision facts.

These models describe assertions extracted from one immutable official-source
snapshot. They are not catalogue truth and contain no canonical graph IDs.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CLAIM_CORE_VERSION = "pr6-claim-core.v2"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimType(StrEnum):
    DEGREE_LEVEL = "degree_level"
    APPLICATION_OPENING = "application_opening"
    APPLICATION_DEADLINE = "application_deadline"
    FUNDING_COMPONENT = "funding_component"
    ELIGIBILITY_RULE = "eligibility_rule"


class ClaimValueState(StrEnum):
    ASSERTED_VALUE = "asserted_value"
    ASSERTED_ABSENT = "asserted_absent"
    ASSERTED_UNKNOWN = "asserted_unknown"
    ASSERTED_NOT_APPLICABLE = "asserted_not_applicable"


class EvidenceRole(StrEnum):
    VALUE = "value"
    SCOPE = "scope"
    APPLICABILITY = "applicability"
    NEGATION = "negation"
    SUPERSESSION = "supersession"


class DegreeLevelValue(StrEnum):
    BACHELORS = "bachelors"
    MASTERS = "masters"
    PHD = "phd"
    POSTDOC = "postdoc"
    SHORT_COURSE = "short_course"


class TemporalPrecision(StrEnum):
    DATE = "date"
    DATETIME = "datetime"


class FundingCoverage(StrEnum):
    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    NOT_COVERED = "not_covered"
    UNKNOWN = "unknown"


class FundingComponentType(StrEnum):
    TUITION = "tuition"
    STIPEND = "stipend"
    ACCOMMODATION = "accommodation"
    TRAVEL = "travel"
    INSURANCE = "insurance"
    FEES = "fees"
    OTHER = "other"


class FundingFrequency(StrEnum):
    ONE_TIME = "one_time"
    MONTHLY = "monthly"
    ANNUAL = "annual"
    PER_SEMESTER = "per_semester"
    PER_ACADEMIC_YEAR = "per_academic_year"
    VARIABLE = "variable"
    OTHER = "other"
    NOT_STATED = "not_stated"


class FundingAmountKind(StrEnum):
    EXACT = "exact"
    UP_TO = "up_to"
    AT_LEAST = "at_least"
    RANGE = "range"
    VARIABLE = "variable"
    NOT_STATED = "not_stated"


class EligibilityRuleType(StrEnum):
    NATIONALITY = "nationality"
    RESIDENCE = "residence"
    TARGET_DEGREE = "target_degree"
    FIELD = "field"
    CGPA = "cgpa"
    PERCENTAGE = "percentage"
    IELTS = "ielts"
    TOEFL = "toefl"
    WORK_EXPERIENCE_MONTHS = "work_experience_months"
    AGE = "age"
    OTHER = "other"


class EligibilityOperator(StrEnum):
    EQUALS = "equals"
    IN = "in"
    NOT_IN = "not_in"
    GTE = "gte"
    LTE = "lte"


_NUMERIC_ELIGIBILITY_TYPES = {
    EligibilityRuleType.CGPA,
    EligibilityRuleType.PERCENTAGE,
    EligibilityRuleType.IELTS,
    EligibilityRuleType.TOEFL,
    EligibilityRuleType.WORK_EXPERIENCE_MONTHS,
    EligibilityRuleType.AGE,
}
_TEXT_ELIGIBILITY_TYPES = {
    EligibilityRuleType.NATIONALITY,
    EligibilityRuleType.RESIDENCE,
    EligibilityRuleType.TARGET_DEGREE,
    EligibilityRuleType.FIELD,
}


class ScopeHint(StrictModel):
    cycle_label: str | None = Field(default=None, max_length=255)
    track_name: str | None = Field(default=None, max_length=255)
    route_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    institution_name: str | None = Field(default=None, max_length=255)
    programme_name: str | None = Field(default=None, max_length=500)

    @field_validator("route_country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"[A-Za-z]{2}", value):
            raise ValueError("route_country_code must contain two letters")
        return value.upper()


class EvidenceProposal(StrictModel):
    role: EvidenceRole
    excerpt: str = Field(min_length=5, max_length=4000)
    section_label: str | None = Field(default=None, max_length=255)
    locator: str | None = Field(default=None, max_length=500)

    @field_validator("excerpt")
    @classmethod
    def excerpt_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence excerpt cannot be blank")
        return value


class DegreeClaimSubject(StrictModel):
    kind: Literal["degree_subject"] = "degree_subject"
    level: DegreeLevelValue


class FundingClaimSubject(StrictModel):
    kind: Literal["funding_subject"] = "funding_subject"
    component_type: FundingComponentType

    @model_validator(mode="after")
    def reject_untyped_other(self) -> "FundingClaimSubject":
        if self.component_type is FundingComponentType.OTHER:
            raise ValueError("other funding components require a future typed subtype")
        return self


class EligibilityClaimSubject(StrictModel):
    kind: Literal["eligibility_subject"] = "eligibility_subject"
    rule_type: EligibilityRuleType

    @model_validator(mode="after")
    def reject_untyped_other(self) -> "EligibilityClaimSubject":
        if self.rule_type is EligibilityRuleType.OTHER:
            raise ValueError("other eligibility rules require a future typed subtype")
        return self


ClaimSubject = Annotated[
    DegreeClaimSubject | FundingClaimSubject | EligibilityClaimSubject,
    Field(discriminator="kind"),
]


class DegreeClaimValue(StrictModel):
    kind: Literal["degree"] = "degree"
    level: DegreeLevelValue


class TemporalClaimValue(StrictModel):
    kind: Literal["temporal"] = "temporal"
    precision: TemporalPrecision
    calendar_date: date | None = None
    datetime_value: datetime | None = None
    timezone_label: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_precision(self) -> "TemporalClaimValue":
        if self.precision is TemporalPrecision.DATE:
            if self.calendar_date is None or self.datetime_value is not None:
                raise ValueError("date precision requires calendar_date only")
        else:
            if self.datetime_value is None or self.calendar_date is not None:
                raise ValueError("datetime precision requires datetime_value only")
            if self.datetime_value.tzinfo is None or self.datetime_value.utcoffset() is None:
                raise ValueError("datetime_value must be offset-aware")
        return self


class FundingClaimValue(StrictModel):
    kind: Literal["funding"] = "funding"
    component_type: FundingComponentType
    coverage_status: FundingCoverage
    amount_kind: FundingAmountKind = FundingAmountKind.NOT_STATED
    amount: Decimal | None = Field(default=None, ge=0)
    amount_min: Decimal | None = Field(default=None, ge=0)
    amount_max: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    frequency: FundingFrequency = FundingFrequency.NOT_STATED

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"[A-Za-z]{3}", value):
            raise ValueError("currency must contain three letters")
        return value.upper()

    @model_validator(mode="after")
    def validate_amount_shape(self) -> "FundingClaimValue":
        if self.component_type is FundingComponentType.OTHER:
            raise ValueError("other funding components require a future typed subtype")
        if self.frequency is FundingFrequency.OTHER:
            raise ValueError("other funding frequencies require a future typed subtype")
        values = (self.amount, self.amount_min, self.amount_max)
        if self.coverage_status is FundingCoverage.NOT_COVERED and any(
            item is not None for item in values
        ):
            raise ValueError("not-covered funding cannot contain a monetary amount")
        expected = {
            FundingAmountKind.EXACT: (True, False, False),
            FundingAmountKind.UP_TO: (False, False, True),
            FundingAmountKind.AT_LEAST: (False, True, False),
            FundingAmountKind.RANGE: (False, True, True),
            FundingAmountKind.VARIABLE: (False, False, False),
            FundingAmountKind.NOT_STATED: (False, False, False),
        }[self.amount_kind]
        present = tuple(item is not None for item in values)
        if present != expected:
            raise ValueError("funding amount fields do not match amount_kind")
        if self.amount_min is not None and self.amount_max is not None:
            if self.amount_min > self.amount_max:
                raise ValueError("funding range minimum cannot exceed maximum")
        if any(expected) and self.currency is None:
            raise ValueError("currency is required when a monetary amount is present")
        return self


EligibilityScalar = str | int | Decimal | bool


class EligibilityClaimValue(StrictModel):
    kind: Literal["eligibility"] = "eligibility"
    rule_type: EligibilityRuleType
    operator: EligibilityOperator
    value: EligibilityScalar | list[EligibilityScalar]
    unit: str | None = Field(default=None, max_length=64)
    grading_scale: Decimal | None = Field(default=None, gt=0)
    required: bool = True

    @model_validator(mode="after")
    def validate_operator_and_value_domain(self) -> "EligibilityClaimValue":
        if self.rule_type is EligibilityRuleType.OTHER:
            raise ValueError("other eligibility rules require a future typed subtype")
        list_operator = self.operator in {EligibilityOperator.IN, EligibilityOperator.NOT_IN}
        if list_operator and (not isinstance(self.value, list) or not self.value):
            raise ValueError("in/not_in operators require a non-empty list")
        if not list_operator and isinstance(self.value, list):
            raise ValueError("scalar operators cannot use list values")

        if self.rule_type in _NUMERIC_ELIGIBILITY_TYPES:
            if self.operator not in {
                EligibilityOperator.EQUALS,
                EligibilityOperator.GTE,
                EligibilityOperator.LTE,
            }:
                raise ValueError("numeric eligibility rules require equals/gte/lte")
            if (
                isinstance(self.value, list)
                or isinstance(self.value, (str, bool))
                or not isinstance(self.value, (int, Decimal))
            ):
                raise ValueError("numeric eligibility rules require a numeric scalar")

        if self.rule_type in _TEXT_ELIGIBILITY_TYPES:
            allowed = {
                EligibilityOperator.EQUALS,
                EligibilityOperator.IN,
                EligibilityOperator.NOT_IN,
            }
            if self.operator not in allowed:
                raise ValueError("text eligibility rules require equals/in/not_in")
            values = self.value if isinstance(self.value, list) else [self.value]
            if any(not isinstance(item, str) for item in values):
                raise ValueError("text eligibility rules require string values")

        if self.grading_scale is not None and self.rule_type is not EligibilityRuleType.CGPA:
            raise ValueError("grading_scale is only valid for CGPA rules")
        return self


ClaimValue = Annotated[
    DegreeClaimValue | TemporalClaimValue | FundingClaimValue | EligibilityClaimValue,
    Field(discriminator="kind"),
]

_EXPECTED_VALUE_KIND = {
    ClaimType.DEGREE_LEVEL: "degree",
    ClaimType.APPLICATION_OPENING: "temporal",
    ClaimType.APPLICATION_DEADLINE: "temporal",
    ClaimType.FUNDING_COMPONENT: "funding",
    ClaimType.ELIGIBILITY_RULE: "eligibility",
}
_EXPECTED_SUBJECT_KIND = {
    ClaimType.DEGREE_LEVEL: "degree_subject",
    ClaimType.FUNDING_COMPONENT: "funding_subject",
    ClaimType.ELIGIBILITY_RULE: "eligibility_subject",
}
_COLLECTION_CLAIM_TYPES = set(_EXPECTED_SUBJECT_KIND)


class SourceClaim(StrictModel):
    claim_type: ClaimType
    value_state: ClaimValueState = ClaimValueState.ASSERTED_VALUE
    value: ClaimValue | None = None
    subject: ClaimSubject | None = None
    scope_hint: ScopeHint = Field(default_factory=ScopeHint)
    evidence: list[EvidenceProposal] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_claim_shape(self) -> "SourceClaim":
        if self.value_state is ClaimValueState.ASSERTED_VALUE:
            if self.value is None:
                raise ValueError("asserted_value claims require a value")
            if not any(item.role is EvidenceRole.VALUE for item in self.evidence):
                raise ValueError("asserted_value claims require value evidence")
        else:
            if self.value is not None:
                raise ValueError("non-value claim states cannot contain a typed value")
            if self.value_state in {
                ClaimValueState.ASSERTED_ABSENT,
                ClaimValueState.ASSERTED_NOT_APPLICABLE,
            } and not any(item.role is EvidenceRole.NEGATION for item in self.evidence):
                raise ValueError("absence/not-applicable claims require negation evidence")
            if self.value_state is ClaimValueState.ASSERTED_UNKNOWN and not any(
                item.role in {EvidenceRole.VALUE, EvidenceRole.APPLICABILITY}
                for item in self.evidence
            ):
                raise ValueError("asserted_unknown claims require explicit unknown evidence")

        scope_values = self.scope_hint.model_dump(exclude_none=True)
        if scope_values and not any(item.role is EvidenceRole.SCOPE for item in self.evidence):
            raise ValueError("source-derived scope hints require scope evidence")

        if self.value is not None and self.value.kind != _EXPECTED_VALUE_KIND[self.claim_type]:
            raise ValueError("claim type and typed value kind do not match")

        if self.subject is not None:
            expected_subject = _EXPECTED_SUBJECT_KIND.get(self.claim_type)
            if expected_subject is None or self.subject.kind != expected_subject:
                raise ValueError("claim type and typed subject kind do not match")
            if self.value is not None and not _subject_matches_value(self.subject, self.value):
                raise ValueError("claim subject must identify the same collection member as value")

        if (
            self.value is None
            and self.claim_type in _COLLECTION_CLAIM_TYPES
            and self.subject is None
        ):
            raise ValueError("non-value collection claims require a typed subject")
        return self


class SourceClaimBatch(StrictModel):
    contract_version: Literal[CLAIM_CORE_VERSION] = CLAIM_CORE_VERSION
    claims: list[SourceClaim] = Field(default_factory=list, max_length=100)


def claim_fingerprint(claim: SourceClaim) -> str:
    """Fingerprint one source assertion; DB uniqueness must also include source extraction."""

    payload = {
        "claim_type": claim.claim_type.value,
        "value_state": claim.value_state.value,
        "value": None if claim.value is None else claim.value.model_dump(mode="json"),
        "subject": None if claim.subject is None else claim.subject.model_dump(mode="json"),
        "scope_hint": claim.scope_hint.model_dump(mode="json", exclude_none=True),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def clean_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _subject_matches_value(subject: ClaimSubject, value: ClaimValue) -> bool:
    if isinstance(subject, DegreeClaimSubject) and isinstance(value, DegreeClaimValue):
        return subject.level is value.level
    if isinstance(subject, FundingClaimSubject) and isinstance(value, FundingClaimValue):
        return subject.component_type is value.component_type
    if isinstance(subject, EligibilityClaimSubject) and isinstance(value, EligibilityClaimValue):
        return subject.rule_type is value.rule_type
    return False


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
