"""Versioned, source-scoped claim contracts for direct URL acquisition."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.catalogue_ingestion.trust_domains import EvidenceTrustDomain

CLAIM_SCHEMA_VERSION = "catalogue-claims.v5"
PREVIOUS_CLAIM_SCHEMA_VERSION = "catalogue-claims.v4"
V3_CLAIM_SCHEMA_VERSION = "catalogue-claims.v3"
LEGACY_CLAIM_SCHEMA_VERSION = "catalogue-claims.v2"
CLAIM_SCHEMA_VERSIONS = frozenset(
    {
        LEGACY_CLAIM_SCHEMA_VERSION,
        V3_CLAIM_SCHEMA_VERSION,
        PREVIOUS_CLAIM_SCHEMA_VERSION,
        CLAIM_SCHEMA_VERSION,
    }
)


class ClaimObjective(StrEnum):
    IDENTITY = "identity"
    PROGRAMMES = "programmes"
    PROGRAMME_DETAILS = "programme_details"
    ROUTES = "routes"
    ELIGIBILITY = "eligibility"
    ELIGIBILITY_CONTEXT = "eligibility_context"
    DOCUMENTS_CORE = "documents_core"
    DOCUMENTS_REQUIREMENTS = "documents_requirements"
    DOCUMENTS_COUNTS = "documents_counts"
    DOCUMENTS_FORMAT = "documents_format"
    FUNDING = "funding"
    APPLICATION_TIMELINE = "application_timeline"


class ObjectiveCoverageState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NOT_STATED = "not_stated"
    NOT_APPLICABLE = "not_applicable"


class ScopedCoverageState(StrEnum):
    UNKNOWN = "unknown"
    NOT_YET_ACQUIRED = "not_yet_acquired"
    BLOCKED = "blocked"
    NOT_STATED = "not_stated"
    NOT_APPLICABLE = "not_applicable"
    PARTIAL = "partial"
    COMPLETE = "complete"
    CONFLICTING = "conflicting"
    QUARANTINED = "quarantined"
    FAILED = "failed"


class ClaimEntityType(StrEnum):
    SCHOLARSHIP = "scholarship"
    CYCLE = "cycle"
    PROGRAMME = "programme"
    TRACK = "track"
    INSTITUTION = "institution"
    ELIGIBILITY = "eligibility"
    DEADLINE = "deadline"
    EVENT = "event"
    FUNDING = "funding"
    DOCUMENT = "document"
    STEP = "step"
    RESOURCE = "resource"


SUPPORTED_CLAIM_FIELDS: dict[ClaimEntityType, frozenset[str]] = {
    ClaimEntityType.SCHOLARSHIP: frozenset(
        {"name", "provider_name", "country_code", "degree_levels", "alias"}
    ),
    ClaimEntityType.CYCLE: frozenset({"intake_year"}),
    ClaimEntityType.PROGRAMME: frozenset(
        {
            "name",
            "programme_type",
            "degree_levels",
            "fields_of_study",
            "duration",
            "description",
            "application_route_keys",
            "display_order",
        }
    ),
    ClaimEntityType.TRACK: frozenset(
        {
            "name",
            "track_type",
            "parent_track_key",
            "application_method",
            "application_url",
            "display_order",
        }
    ),
    ClaimEntityType.INSTITUTION: frozenset(
        {
            "canonical_name",
            "institution_type",
            "country_code",
            "official_website",
            "role",
            "application_url",
        }
    ),
    ClaimEntityType.ELIGIBILITY: frozenset(
        {
            "rule_type",
            "operator",
            "value",
            "unit",
            "required",
            "condition",
            "is_exclusion",
            "critical",
            "original_text",
            "notes",
            "display_order",
        }
    ),
    ClaimEntityType.DEADLINE: frozenset(
        {
            "deadline_at",
            "deadline_text",
            "deadline_type",
            "precision",
            "timezone",
            "varies_by",
            "label",
            "notes",
        }
    ),
    ClaimEntityType.EVENT: frozenset(
        {
            "event_type",
            "starts_at",
            "ends_at",
            "date_text",
            "precision",
            "timezone",
            "label",
            "notes",
            "display_order",
        }
    ),
    ClaimEntityType.FUNDING: frozenset(
        {
            "component_type",
            "coverage_status",
            "amount",
            "currency",
            "frequency",
            "unit",
            "qualifier",
            "original_text",
            "description",
        }
    ),
    ClaimEntityType.DOCUMENT: frozenset(
        {
            "name",
            "required",
            "condition",
            "submission_stage",
            "original_count",
            "copy_count",
            "translation_requirement",
            "certification_requirement",
            "form_year",
            "notes",
            "display_order",
        }
    ),
    ClaimEntityType.STEP: frozenset(
        {
            "title",
            "stage_type",
            "required",
            "actor_type",
            "actor_name",
            "outcome",
            "original_text",
            "description",
            "application_url",
            "display_order",
        }
    ),
    ClaimEntityType.RESOURCE: frozenset(
        {
            "title",
            "resource_type",
            "url",
            "contact_type",
            "organization",
            "contact_name",
            "email",
            "phone",
            "address",
            "original_text",
            "required",
            "notes",
            "display_order",
        }
    ),
}

CLAIM_FIELD_ALIASES: dict[ClaimEntityType, dict[str, str]] = {
    ClaimEntityType.SCHOLARSHIP: {
        "aliases": "alias",
        "canonical_name": "name",
        "destination_country_code": "country_code",
        "scholarship": "name",
    },
    ClaimEntityType.PROGRAMME: {"fields_of_study_list": "fields_of_study"},
    ClaimEntityType.TRACK: {
        "method": "application_method",
        "order": "display_order",
        "parent_route": "parent_track_key",
        "route_type": "track_type",
    },
    ClaimEntityType.INSTITUTION: {
        "administering_body": "canonical_name",
        "administering_bodies": "canonical_name",
        "name": "canonical_name",
    },
    ClaimEntityType.FUNDING: {
        "component_amount": "amount",
        "component_description": "description",
        "component_frequency": "frequency",
        "payment_frequency": "frequency",
        "payment_unit": "unit",
    },
    ClaimEntityType.STEP: {
        "label": "title",
        "order": "display_order",
        "step_type": "stage_type",
        "stage": "stage_type",
    },
    ClaimEntityType.RESOURCE: {
        "label": "title",
        "link": "url",
        "email_address": "email",
        "telephone": "phone",
        "contact_person": "contact_name",
    },
}


class StrictClaimModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimScope(StrictClaimModel):
    scholarship_family_key: str | None = None
    cycle_key: str | None = None
    country_key: str | None = None
    institution_key: str | None = None
    track_key: str | None = None
    programme_key: str | None = None
    degree_level_key: str | None = None
    subject_key: str | None = None
    award_variant_key: str | None = None
    application_channel_key: str | None = None


class ClaimValue(StrictClaimModel):
    string_value: str | None
    decimal_value: Decimal | None
    integer_value: int | None
    boolean_value: bool | None
    string_list_value: list[str] | None

    @model_validator(mode="after")
    def exactly_one_value(self) -> "ClaimValue":
        if self.string_list_value == []:
            self.string_list_value = None
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
    def valid_span(self) -> "ExtractedClaim":
        field_path = self.field_path.strip().casefold()
        if field_path not in SUPPORTED_CLAIM_FIELDS[self.entity_type]:
            for separator in (".", " ", "_", "/"):
                prefix = f"{self.entity_type.value}{separator}"
                if field_path.startswith(prefix):
                    field_path = field_path[len(prefix) :]
                    break
        field_path = field_path.replace(" ", "_").replace("-", "_")
        self.field_path = CLAIM_FIELD_ALIASES.get(self.entity_type, {}).get(field_path, field_path)
        if self.excerpt_end <= self.excerpt_start:
            raise ValueError("Claim evidence span must be non-empty")
        return self


class ClaimExtractionOutput(StrictClaimModel):
    objective: ClaimObjective = ClaimObjective.IDENTITY
    coverage_state: ObjectiveCoverageState = ObjectiveCoverageState.COMPLETE
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
    trust_domain: EvidenceTrustDomain | None = None
    claim_id: str | None = None
    objectives: list[ClaimObjective] = Field(default_factory=list)


class ClaimConflictRecord(StrictClaimModel):
    entity_type: ClaimEntityType
    entity_key: str
    field_path: str
    scope: ClaimScope
    reason: str


class ClaimRejectionRecord(StrictClaimModel):
    artifact_id: str
    entity_type: ClaimEntityType
    entity_key: str
    field_path: str
    scope: ClaimScope
    reason: str


class ScopeCoverageDecision(StrictClaimModel):
    scope_node_id: str | None = None
    scope_type: str
    scope_key: str
    lifecycle_key: str | None = None
    objective: ClaimObjective
    state: ScopedCoverageState
    required: bool = True
    supporting_claim_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    expected_item_count: int | None = None
    resolved_item_count: int = 0
    reason: str
    missing_frontier_reasons: list[str] = Field(default_factory=list)


class ClaimResolution(StrictClaimModel):
    schema_version: Literal[
        "catalogue-claims.v2",
        "catalogue-claims.v3",
        "catalogue-claims.v4",
        "catalogue-claims.v5",
    ] = CLAIM_SCHEMA_VERSION
    resolved: list[ResolvedClaim]
    conflicts: list[str]
    rejected: list[str]
    completeness_errors: list[str]
    unknown_objectives: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    objective_coverage: dict[str, str] = Field(default_factory=dict)
    provider_objective_coverage: dict[str, str] = Field(default_factory=dict)
    conflict_records: list[ClaimConflictRecord] = Field(default_factory=list)
    rejection_records: list[ClaimRejectionRecord] = Field(default_factory=list)
    scope_coverage: list[ScopeCoverageDecision] = Field(default_factory=list)
    coverage_revision: str | None = None

    @property
    def is_materializable(self) -> bool:
        return not self.conflicts and not self.rejected and not self.completeness_errors
