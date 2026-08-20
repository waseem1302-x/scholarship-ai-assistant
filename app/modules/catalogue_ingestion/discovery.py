"""Pure, deterministic planning contracts for catalogue source discovery."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PLANNER_VERSION = "catalogue-discovery-query.v1"
MAX_PUBLIC_LABEL_LENGTH = 255
DOMAIN_PATTERN = re.compile(
    r"(?=^.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,99}$")

ALLOWED_DISCOVERY_FIELD_PATHS = frozenset(
    {
        "identity.name",
        "identity.provider",
        "identity.official_source",
        "cycle.status",
        "cycle.application_opening",
        "cycle.application_deadline",
        "funding.coverage",
        "eligibility.core",
        "application.route",
        "application.required_documents",
        "application.steps",
        "structure.participating_institutions",
        "structure.eligible_programmes",
        "institution.local_requirements",
        "institution.local_deadline",
        "relationships.independent_awards",
    }
)


class DiscoveryObjectiveKind(StrEnum):
    RESOLVE_CANONICAL_SOURCE = "resolve_canonical_source"
    RESOLVE_PROVIDER_IDENTITY = "resolve_provider_identity"
    CURRENT_CYCLE_STATUS = "current_cycle_status"
    CURRENT_APPLICATION_DEADLINE = "current_application_deadline"
    CURRENT_APPLICATION_OPENING = "current_application_opening"
    FUNDING_COVERAGE = "funding_coverage"
    ELIGIBILITY_CORE = "eligibility_core"
    APPLICATION_ROUTE = "application_route"
    REQUIRED_DOCUMENTS = "required_documents"
    APPLICATION_STEPS = "application_steps"
    PARTICIPATING_INSTITUTIONS = "participating_institutions"
    ELIGIBLE_PROGRAMMES = "eligible_programmes"
    INSTITUTION_LOCAL_REQUIREMENTS = "institution_local_requirements"
    INSTITUTION_LOCAL_DEADLINE = "institution_local_deadline"
    RELATED_INDEPENDENT_AWARDS = "related_independent_awards"
    CONFLICT_RESOLUTION_SOURCE = "conflict_resolution_source"
    FRESHNESS_REFRESH = "freshness_refresh"


class DiscoveryPrioritySnapshot(BaseModel):
    """Immutable, explainable lexicographic priority captured at run creation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default="catalogue-discovery-priority.v1", max_length=100)
    blocking_class: int = Field(ge=0, le=4)
    criticality_tier: int = Field(ge=0, le=3)
    conflict_or_stale_rank: int = Field(ge=0, le=4)
    current_cycle_rank: int = Field(ge=0, le=3)
    user_demand_rank: int = Field(default=0, ge=0, le=1_000_000)
    structural_dependency_rank: int = Field(default=0, ge=0, le=100)
    retry_penalty: int = Field(default=0, ge=0, le=100)
    deterministic_tiebreak: str = Field(min_length=1, max_length=100)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=20)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalized_reason_codes(values)

    @property
    def sort_key(self) -> tuple[int, int, int, int, int, int, int, str]:
        return (
            self.blocking_class,
            self.criticality_tier,
            self.conflict_or_stale_rank,
            self.current_cycle_rank,
            self.user_demand_rank,
            self.structural_dependency_rank,
            self.retry_penalty,
            self.deterministic_tiebreak,
        )


class DiscoveryScopeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scholarship_id: uuid.UUID | None = None
    candidate_id: uuid.UUID | None = None
    cycle_id: uuid.UUID | None = None
    track_id: uuid.UUID | None = None
    institution_id: uuid.UUID | None = None
    programme_id: uuid.UUID | None = None


class DiscoveryTargetIdentitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default="catalogue-discovery-target.v1", max_length=100)
    scholarship_name: str | None = Field(default=None, max_length=MAX_PUBLIC_LABEL_LENGTH)
    scholarship_aliases: tuple[str, ...] = Field(default=(), max_length=20)
    provider_name: str | None = Field(default=None, max_length=MAX_PUBLIC_LABEL_LENGTH)
    institution_name: str | None = Field(default=None, max_length=MAX_PUBLIC_LABEL_LENGTH)
    country: str | None = Field(default=None, max_length=100)
    programme_name: str | None = Field(default=None, max_length=MAX_PUBLIC_LABEL_LENGTH)
    cycle_hint: str | None = Field(default=None, max_length=120)
    reviewed_domains: tuple[str, ...] = Field(default=(), max_length=20)


class DiscoveryPublicContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default="catalogue-discovery-public-context.v1", max_length=100)
    objective_kind: DiscoveryObjectiveKind
    scope: DiscoveryScopeSnapshot
    field_paths: tuple[str, ...] = Field(min_length=1, max_length=20)
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=20)
    identity: DiscoveryTargetIdentitySnapshot

    @field_validator("field_paths")
    @classmethod
    def validate_field_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        unsupported = set(normalized) - ALLOWED_DISCOVERY_FIELD_PATHS
        if unsupported:
            raise ValueError(f"unsupported discovery field paths: {sorted(unsupported)}")
        return normalized

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalized_reason_codes(values)


class DiscoveryObjective(BaseModel):
    """Public catalogue-only reason and scope for one bounded discovery run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective_kind: DiscoveryObjectiveKind
    scholarship_id: uuid.UUID | None = None
    candidate_id: uuid.UUID | None = None
    cycle_id: uuid.UUID | None = None
    track_id: uuid.UUID | None = None
    institution_id: uuid.UUID | None = None
    programme_id: uuid.UUID | None = None
    field_paths: tuple[str, ...] = Field(min_length=1, max_length=20)
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=20)
    criticality_tier: int = Field(ge=0, le=3)
    planner_version: str = Field(default=PLANNER_VERSION, min_length=1, max_length=100)
    scholarship_name: str | None = Field(default=None, max_length=MAX_PUBLIC_LABEL_LENGTH)
    scholarship_aliases: tuple[str, ...] = Field(default=(), max_length=20)
    provider_name: str | None = Field(default=None, max_length=MAX_PUBLIC_LABEL_LENGTH)
    institution_name: str | None = Field(default=None, max_length=MAX_PUBLIC_LABEL_LENGTH)
    country: str | None = Field(default=None, max_length=100)
    programme_name: str | None = Field(default=None, max_length=MAX_PUBLIC_LABEL_LENGTH)
    cycle_hint: str | None = Field(default=None, max_length=120)
    reviewed_domains: tuple[str, ...] = Field(default=(), max_length=20)

    @field_validator(
        "scholarship_name",
        "provider_name",
        "institution_name",
        "country",
        "programme_name",
        "cycle_hint",
    )
    @classmethod
    def normalize_optional_label(cls, value: str | None) -> str | None:
        return _normalize_label(value)

    @field_validator("scholarship_aliases")
    @classmethod
    def normalize_aliases(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = {_normalize_label(value) for value in values}
        normalized.discard(None)
        return tuple(sorted(normalized, key=str.casefold))

    @field_validator("field_paths")
    @classmethod
    def validate_field_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        unsupported = set(normalized) - ALLOWED_DISCOVERY_FIELD_PATHS
        if unsupported:
            raise ValueError(f"unsupported discovery field paths: {sorted(unsupported)}")
        return normalized

    @field_validator("reason_codes")
    @classmethod
    def validate_objective_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalized_reason_codes(values)

    @field_validator("reviewed_domains")
    @classmethod
    def normalize_reviewed_domains(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: set[str] = set()
        for value in values:
            domain = value.strip().casefold().strip(".")
            if not DOMAIN_PATTERN.fullmatch(domain):
                raise ValueError("reviewed domains must be bare public DNS names")
            normalized.add(domain)
        return tuple(sorted(normalized))

    @model_validator(mode="after")
    def validate_scope(self) -> DiscoveryObjective:
        if self.track_id is not None and self.cycle_id is None:
            raise ValueError("track scope requires cycle scope")
        if self.programme_id is not None and self.institution_id is None:
            raise ValueError("programme scope requires institution scope")
        if not any((self.scholarship_name, self.provider_name, self.institution_name)):
            raise ValueError("a public scholarship, provider, or institution name is required")
        if (
            self.objective_kind
            not in {
                DiscoveryObjectiveKind.RESOLVE_PROVIDER_IDENTITY,
                DiscoveryObjectiveKind.RELATED_INDEPENDENT_AWARDS,
            }
            and not self.scholarship_name
        ):
            raise ValueError("this discovery objective requires a public scholarship name")
        if self.objective_kind in {
            DiscoveryObjectiveKind.INSTITUTION_LOCAL_REQUIREMENTS,
            DiscoveryObjectiveKind.INSTITUTION_LOCAL_DEADLINE,
        } and not all((self.institution_id, self.institution_name)):
            raise ValueError("institution-local objectives require resolved institution context")
        if self.objective_kind is DiscoveryObjectiveKind.ELIGIBLE_PROGRAMMES and not all(
            (self.institution_id, self.institution_name)
        ):
            raise ValueError("programme discovery requires resolved institution context")
        if self.objective_kind is DiscoveryObjectiveKind.RELATED_INDEPENDENT_AWARDS and not any(
            (self.institution_name, self.provider_name)
        ):
            raise ValueError("related-award discovery requires a known public owner")
        return self

    def scope_snapshot(self) -> DiscoveryScopeSnapshot:
        return DiscoveryScopeSnapshot(
            scholarship_id=self.scholarship_id,
            candidate_id=self.candidate_id,
            cycle_id=self.cycle_id,
            track_id=self.track_id,
            institution_id=self.institution_id,
            programme_id=self.programme_id,
        )

    def identity_snapshot(self) -> DiscoveryTargetIdentitySnapshot:
        return DiscoveryTargetIdentitySnapshot(
            scholarship_name=self.scholarship_name,
            scholarship_aliases=self.scholarship_aliases,
            provider_name=self.provider_name,
            institution_name=self.institution_name,
            country=self.country,
            programme_name=self.programme_name,
            cycle_hint=self.cycle_hint,
            reviewed_domains=self.reviewed_domains,
        )

    def public_context(self) -> DiscoveryPublicContext:
        return DiscoveryPublicContext(
            objective_kind=self.objective_kind,
            scope=self.scope_snapshot(),
            field_paths=self.field_paths,
            reason_codes=self.reason_codes,
            identity=self.identity_snapshot(),
        )


class DiscoveryQueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ordinal: int = Field(ge=0)
    query_text: str = Field(min_length=1, max_length=1000)
    query_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_kind: str = Field(min_length=1, max_length=64)
    allowed_domains: tuple[str, ...] = Field(default=(), max_length=20)
    public_context: DiscoveryPublicContext


class DiscoveryQueryPlanner:
    def __init__(self, *, max_queries: int) -> None:
        if not 1 <= max_queries <= 20:
            raise ValueError("max_queries must be between 1 and 20")
        self.max_queries = max_queries

    def plan(self, objective: DiscoveryObjective) -> tuple[DiscoveryQueryPlan, ...]:
        raw_queries = self._queries(objective)
        plans: list[DiscoveryQueryPlan] = []
        seen: set[str] = set()
        context = objective.public_context()
        for query_kind, query_text in raw_queries:
            normalized_query = " ".join(query_text.split())
            query_hash = discovery_query_hash(objective, normalized_query)
            if query_hash in seen:
                continue
            seen.add(query_hash)
            plans.append(
                DiscoveryQueryPlan(
                    ordinal=len(plans),
                    query_text=normalized_query,
                    query_hash=query_hash,
                    query_kind=query_kind,
                    allowed_domains=objective.reviewed_domains,
                    public_context=context,
                )
            )
            if len(plans) == self.max_queries:
                break
        return tuple(plans)

    def _queries(self, objective: DiscoveryObjective) -> tuple[tuple[str, str], ...]:
        scholarship = _quoted(objective.scholarship_name)
        provider = _quoted(objective.provider_name)
        institution = _quoted(objective.institution_name)
        programme = _quoted(objective.programme_name)
        cycle = objective.cycle_hint or "current"
        kind = objective.objective_kind

        if kind is DiscoveryObjectiveKind.RESOLVE_CANONICAL_SOURCE:
            return _present(
                ("exact_identity", f"{scholarship} official scholarship"),
                *(("provider_refinement", f"{scholarship} {provider} official"),)
                if provider
                else (),
            )
        if kind is DiscoveryObjectiveKind.RESOLVE_PROVIDER_IDENTITY:
            return _present(
                ("provider_identity", f"{scholarship} {provider} scholarship provider"),
                *(("provider_official", f"{provider} official scholarships"),) if provider else (),
            )
        if kind in {
            DiscoveryObjectiveKind.CURRENT_CYCLE_STATUS,
            DiscoveryObjectiveKind.CURRENT_APPLICATION_OPENING,
        }:
            return _present(
                ("current_cycle", f"{scholarship} application {cycle}"),
                ("opening_date", f"{scholarship} applications open {cycle}"),
            )
        if kind is DiscoveryObjectiveKind.CURRENT_APPLICATION_DEADLINE:
            return _present(
                ("deadline", f"{scholarship} deadline {cycle}"),
                ("application_cycle", f"{scholarship} application {cycle}"),
            )
        if kind is DiscoveryObjectiveKind.FUNDING_COVERAGE:
            return _present(("funding", f"{scholarship} funding benefits tuition stipend"))
        if kind is DiscoveryObjectiveKind.ELIGIBILITY_CORE:
            return _present(("eligibility", f"{scholarship} eligibility requirements"))
        if kind is DiscoveryObjectiveKind.APPLICATION_ROUTE:
            return _present(("route", f"{scholarship} application route apply"))
        if kind is DiscoveryObjectiveKind.REQUIRED_DOCUMENTS:
            return _present(("documents", f"{scholarship} required application documents"))
        if kind is DiscoveryObjectiveKind.APPLICATION_STEPS:
            return _present(("steps", f"{scholarship} application process steps"))
        if kind is DiscoveryObjectiveKind.PARTICIPATING_INSTITUTIONS:
            return _present(("institutions", f"{scholarship} participating universities"))
        if kind is DiscoveryObjectiveKind.ELIGIBLE_PROGRAMMES:
            return _present(
                ("programmes", f"{scholarship} {institution} eligible programmes {programme}")
            )
        if kind is DiscoveryObjectiveKind.INSTITUTION_LOCAL_REQUIREMENTS:
            return _present(
                ("institution_requirements", f"{scholarship} {institution} requirements")
            )
        if kind is DiscoveryObjectiveKind.INSTITUTION_LOCAL_DEADLINE:
            return _present(
                ("institution_deadline", f"{scholarship} {institution} deadline {cycle}")
            )
        if kind is DiscoveryObjectiveKind.RELATED_INDEPENDENT_AWARDS:
            return _present(("related_awards", f"{institution or provider} scholarships"))
        if kind is DiscoveryObjectiveKind.CONFLICT_RESOLUTION_SOURCE:
            return _present(
                ("conflict_resolution", f"{scholarship} {provider} official current {cycle}")
            )
        return _present(("freshness", f"{scholarship} {provider} official current {cycle}"))


def discovery_query_hash(objective: DiscoveryObjective, query_text: str) -> str:
    payload = {
        "planner_version": objective.planner_version,
        "objective": objective.model_dump(mode="json"),
        "query": query_text.casefold(),
        "allowed_domains": list(objective.reviewed_domains),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _normalize_label(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _normalized_reason_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(sorted(set(values)))
    if any(not REASON_CODE_PATTERN.fullmatch(value) for value in normalized):
        raise ValueError("reason codes must be bounded uppercase identifiers")
    return normalized


def _quoted(value: str | None) -> str:
    if not value:
        return ""
    return f'"{value.replace(chr(34), "").strip()}"'


def _present(*queries: tuple[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple((kind, " ".join(text.split())) for kind, text in queries if text.strip())
