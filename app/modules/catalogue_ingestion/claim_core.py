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

CLAIM_CORE_VERSION = "pr6-claim-core.v1"


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
    def validate_operator(self) -> "EligibilityClaimValue":
        list_operator = self.operator in {EligibilityOperator.IN, EligibilityOperator.NOT_IN}
        if list_operator and (not isinstance(self.value, list) or not self.value):
            raise ValueError("in/not_in operators require a non-empty list")
        if not list_operator and isinstance(self.value, list):
            raise ValueError("scalar operators cannot use list values")
        return self


ClaimValue = Annotated[
    DegreeClaimValue | TemporalClaimValue | FundingClaimValue | EligibilityClaimValue,
    Field(discriminator="kind"),
]

_EXPECTED_KIND = {
    ClaimType.DEGREE_LEVEL: "degree",
    ClaimType.APPLICATION_OPENING: "temporal",
    ClaimType.APPLICATION_DEADLINE: "temporal",
    ClaimType.FUNDING_COMPONENT: "funding",
    ClaimType.ELIGIBILITY_RULE: "eligibility",
}


class SourceClaim(StrictModel):
    claim_type: ClaimType
    value_state: ClaimValueState = ClaimValueState.ASSERTED_VALUE
    value: ClaimValue | None = None
    scope_hint: ScopeHint = Field(default_factory=ScopeHint)
    collection_key_hint: str | None = Field(default=None, max_length=255)
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
        if self.value is not None and self.value.kind != _EXPECTED_KIND[self.claim_type]:
            raise ValueError("claim type and typed value kind do not match")
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
        "scope_hint": claim.scope_hint.model_dump(mode="json", exclude_none=True),
        "collection_key_hint": claim.collection_key_hint,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def clean_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
