"""Versioned, source-scoped claim contracts for direct URL acquisition."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CLAIM_SCHEMA_VERSION = "catalogue-claims.v2"


class ClaimEntityType(StrEnum):
    SCHOLARSHIP = "scholarship"
    CYCLE = "cycle"
    TRACK = "track"
    INSTITUTION = "institution"
    DEADLINE = "deadline"
    FUNDING = "funding"
    DOCUMENT = "document"
    STEP = "step"


class StrictClaimModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimScope(StrictClaimModel):
    cycle_key: str | None
    track_key: str | None
    institution_key: str | None
    programme_key: str | None


class ClaimValue(StrictClaimModel):
    string_value: str | None
    decimal_value: Decimal | None
    integer_value: int | None
    boolean_value: bool | None
    string_list_value: list[str] | None

    @model_validator(mode="after")
    def exactly_one_value(self) -> ClaimValue:
        values = (
            self.string_value,
            self.decimal_value,
            self.integer_value,
            self.boolean_value,
            self.string_list_value,
        )
        if sum(value is not None for value in values) != 1:
            raise ValueError("A claim must contain exactly one typed value")
        return self

    def primitive(self) -> str | Decimal | int | bool | list[str]:
        for value in (
            self.string_value,
            self.decimal_value,
            self.integer_value,
            self.boolean_value,
            self.string_list_value,
        ):
            if value is not None:
                return value
        raise AssertionError("ClaimValue validation guarantees one value")


class ExtractedClaim(StrictClaimModel):
    entity_type: ClaimEntityType
    entity_key: str = Field(min_length=1, max_length=120)
    field_path: str = Field(min_length=1, max_length=255)
    value: ClaimValue
    scope: ClaimScope
    excerpt: str = Field(min_length=1)
    excerpt_start: int = Field(ge=0)
    excerpt_end: int = Field(ge=0)
    basis: Literal["explicit", "normalized"]

    @model_validator(mode="after")
    def valid_span(self) -> ExtractedClaim:
        if self.excerpt_end <= self.excerpt_start:
            raise ValueError("Claim evidence span must be non-empty")
        return self


class ClaimExtractionOutput(StrictClaimModel):
    claims: list[ExtractedClaim]
    unknown_objectives: list[str]
    conflicts: list[str]
    warnings: list[str]


class ResolvedClaim(StrictClaimModel):
    claim: ExtractedClaim
    artifact_id: str
    source_id: str
    source_url: str
    content_hash: str
    trust_tier: int = Field(ge=1)


class ClaimResolution(StrictClaimModel):
    schema_version: Literal["catalogue-claims.v2"] = CLAIM_SCHEMA_VERSION
    resolved: list[ResolvedClaim]
    conflicts: list[str]
    rejected: list[str]
    completeness_errors: list[str]
    unknown_objectives: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_materializable(self) -> bool:
        return not self.conflicts and not self.rejected and not self.completeness_errors
