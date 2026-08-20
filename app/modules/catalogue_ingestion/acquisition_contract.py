"""Machine-checkable acceptance contract for complete scholarship acquisition."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.catalogue_ingestion.discovery import DiscoveryObjectiveKind
from app.modules.opportunities.evidence_models import SourceOwnerType

ACQUISITION_CONTRACT_VERSION = "scholarship-acquisition.v1"

_COLLECTION_OBJECTIVES = frozenset(
    {
        DiscoveryObjectiveKind.APPLICATION_ROUTE,
        DiscoveryObjectiveKind.PARTICIPATING_INSTITUTIONS,
        DiscoveryObjectiveKind.ELIGIBLE_PROGRAMMES,
        DiscoveryObjectiveKind.RELATED_INDEPENDENT_AWARDS,
    }
)


class AcquisitionInputKind(StrEnum):
    NAME = "name"
    URL = "url"
    DOCUMENT = "document"


class CollectionExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: DiscoveryObjectiveKind
    minimum_items: int = Field(ge=0, le=100_000)
    require_authoritative_source_complete: bool = True
    require_graph_matches_authoritative_source: bool = True

    @model_validator(mode="after")
    def require_collection_objective(self) -> CollectionExpectation:
        if self.objective not in _COLLECTION_OBJECTIVES:
            raise ValueError("collection expectation requires a structural discovery objective")
        return self


class AcquisitionScenario(BaseModel):
    """Versioned target behavior, not evidence that a runtime already satisfies it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    title: str = Field(min_length=3, max_length=255)
    input_kind: AcquisitionInputKind
    operator_supplied_url_count: int = Field(ge=0, le=1)
    expected_seed_candidate_count: int = Field(ge=1, le=10_000)
    expected_canonical_scholarship_count: int = Field(ge=1, le=10_000)
    required_objectives: tuple[DiscoveryObjectiveKind, ...] = Field(min_length=1)
    required_owner_types: tuple[SourceOwnerType, ...] = ()
    collections: tuple[CollectionExpectation, ...] = ()
    max_manual_followup_urls: int = Field(default=0, ge=0, le=100)
    require_source_checks_for_unknowns: Literal[True] = True
    require_field_evidence: Literal[True] = True
    require_scope_preservation: Literal[True] = True
    require_idempotent_rerun: Literal[True] = True
    automatic_publication_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_scenario(self) -> AcquisitionScenario:
        expected_url_count = 1 if self.input_kind is AcquisitionInputKind.URL else 0
        if self.operator_supplied_url_count != expected_url_count:
            raise ValueError("only URL scenarios may begin with one operator-supplied URL")
        if self.expected_canonical_scholarship_count > self.expected_seed_candidate_count:
            raise ValueError("canonical scholarship count cannot exceed seed candidate count")
        if len(set(self.required_objectives)) != len(self.required_objectives):
            raise ValueError("required acquisition objectives must be unique")
        if len(set(self.required_owner_types)) != len(self.required_owner_types):
            raise ValueError("required source owner types must be unique")
        collection_objectives = [item.objective for item in self.collections]
        if len(set(collection_objectives)) != len(collection_objectives):
            raise ValueError("collection expectations must have unique objectives")
        if any(item not in self.required_objectives for item in collection_objectives):
            raise ValueError("collection objectives must also be required acquisition objectives")
        return self


class ObjectiveCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: DiscoveryObjectiveKind
    target_count: int = Field(ge=1, le=10_000)
    resolved_count: int = Field(ge=0, le=10_000)
    explicit_unknown_count: int = Field(ge=0, le=10_000)
    source_checked_count: int = Field(ge=0, le=10_000)
    evidence_backed_count: int = Field(ge=0, le=10_000)
    scope_preserved_count: int = Field(ge=0, le=10_000)
    conflict_count: int = Field(default=0, ge=0, le=10_000)

    @model_validator(mode="after")
    def validate_counts(self) -> ObjectiveCoverage:
        if (
            self.resolved_count + self.explicit_unknown_count + self.conflict_count
            > self.target_count
        ):
            raise ValueError("objective outcome counts cannot exceed target count")
        if self.source_checked_count > self.target_count:
            raise ValueError("source-checked count cannot exceed target count")
        if self.evidence_backed_count > self.resolved_count:
            raise ValueError("evidence-backed count cannot exceed resolved count")
        if self.scope_preserved_count > self.target_count:
            raise ValueError("scope-preserved count cannot exceed target count")
        return self


class CollectionCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: DiscoveryObjectiveKind
    authoritative_source_items: int = Field(ge=0, le=100_000)
    graph_items_persisted: int = Field(ge=0, le=100_000)
    duplicate_graph_items: int = Field(default=0, ge=0, le=100_000)
    authoritative_source_complete: bool

    @model_validator(mode="after")
    def require_collection_objective(self) -> CollectionCoverage:
        if self.objective not in _COLLECTION_OBJECTIVES:
            raise ValueError("collection coverage requires a structural discovery objective")
        return self


class IdempotencyOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    new_canonical_scholarships_on_rerun: int = Field(ge=0, le=10_000)
    new_relationships_on_rerun: int = Field(ge=0, le=100_000)
    new_sources_on_rerun: int = Field(ge=0, le=100_000)
    model_calls_for_unchanged_sources: int = Field(ge=0, le=100_000)


class AcquisitionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    operator_supplied_url_count: int = Field(ge=0, le=100)
    seed_candidates_created: int = Field(ge=0, le=10_000)
    canonical_scholarships_resolved: int = Field(ge=0, le=10_000)
    owner_types_observed: tuple[SourceOwnerType, ...] = ()
    objective_coverage: tuple[ObjectiveCoverage, ...] = ()
    collection_coverage: tuple[CollectionCoverage, ...] = ()
    manual_followup_urls: int = Field(ge=0, le=100_000)
    automatic_publications: int = Field(ge=0, le=10_000)
    idempotency: IdempotencyOutcome

    @model_validator(mode="after")
    def require_unique_dimensions(self) -> AcquisitionOutcome:
        objectives = [item.objective for item in self.objective_coverage]
        collections = [item.objective for item in self.collection_coverage]
        if len(set(objectives)) != len(objectives):
            raise ValueError("objective coverage entries must be unique")
        if len(set(collections)) != len(collections):
            raise ValueError("collection coverage entries must be unique")
        if len(set(self.owner_types_observed)) != len(self.owner_types_observed):
            raise ValueError("observed source owner types must be unique")
        return self


class AcquisitionContractManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal[ACQUISITION_CONTRACT_VERSION]
    execution_evidence: Literal[False]
    scenarios: tuple[AcquisitionScenario, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_scenarios(self) -> AcquisitionContractManifest:
        identifiers = [scenario.scenario_id for scenario in self.scenarios]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("acquisition scenario identifiers must be unique")
        return self


def evaluate_acquisition_outcome(
    scenario: AcquisitionScenario,
    outcome: AcquisitionOutcome,
) -> tuple[str, ...]:
    """Return stable violation codes; an empty tuple means the target contract passed."""

    violations: list[str] = []
    if outcome.scenario_id != scenario.scenario_id:
        violations.append("scenario_id_mismatch")
    if outcome.operator_supplied_url_count != scenario.operator_supplied_url_count:
        violations.append("operator_input_boundary_failed")
    if outcome.seed_candidates_created != scenario.expected_seed_candidate_count:
        violations.append("seed_candidate_count_failed")
    if outcome.canonical_scholarships_resolved != scenario.expected_canonical_scholarship_count:
        violations.append("canonical_scholarship_count_failed")

    missing_owners = set(scenario.required_owner_types) - set(outcome.owner_types_observed)
    if missing_owners:
        violations.append("required_source_owner_missing")

    coverage_by_objective = {item.objective: item for item in outcome.objective_coverage}
    for objective in scenario.required_objectives:
        coverage = coverage_by_objective.get(objective)
        prefix = objective.value
        if coverage is None:
            violations.append(f"objective_missing:{prefix}")
            continue
        if coverage.target_count != scenario.expected_canonical_scholarship_count:
            violations.append(f"objective_target_count_failed:{prefix}")
        if coverage.resolved_count + coverage.explicit_unknown_count != coverage.target_count:
            violations.append(f"objective_completeness_failed:{prefix}")
        if coverage.source_checked_count != coverage.target_count:
            violations.append(f"objective_source_check_failed:{prefix}")
        if coverage.evidence_backed_count != coverage.resolved_count:
            violations.append(f"objective_evidence_failed:{prefix}")
        if coverage.scope_preserved_count != coverage.target_count:
            violations.append(f"objective_scope_failed:{prefix}")
        if coverage.conflict_count:
            violations.append(f"objective_conflict_unresolved:{prefix}")

    collection_by_objective = {item.objective: item for item in outcome.collection_coverage}
    for expectation in scenario.collections:
        coverage = collection_by_objective.get(expectation.objective)
        prefix = expectation.objective.value
        if coverage is None:
            violations.append(f"collection_missing:{prefix}")
            continue
        if coverage.authoritative_source_items < expectation.minimum_items:
            violations.append(f"collection_minimum_failed:{prefix}")
        if (
            expectation.require_authoritative_source_complete
            and not coverage.authoritative_source_complete
        ):
            violations.append(f"collection_source_incomplete:{prefix}")
        if (
            expectation.require_graph_matches_authoritative_source
            and coverage.graph_items_persisted != coverage.authoritative_source_items
        ):
            violations.append(f"collection_graph_mismatch:{prefix}")
        if coverage.duplicate_graph_items:
            violations.append(f"collection_duplicates_present:{prefix}")

    if outcome.manual_followup_urls > scenario.max_manual_followup_urls:
        violations.append("manual_followup_budget_failed")
    if outcome.automatic_publications:
        violations.append("automatic_publication_forbidden")
    if scenario.require_idempotent_rerun and any(
        (
            outcome.idempotency.new_canonical_scholarships_on_rerun,
            outcome.idempotency.new_relationships_on_rerun,
            outcome.idempotency.new_sources_on_rerun,
            outcome.idempotency.model_calls_for_unchanged_sources,
        )
    ):
        violations.append("idempotent_rerun_failed")
    return tuple(violations)


__all__ = [
    "ACQUISITION_CONTRACT_VERSION",
    "AcquisitionContractManifest",
    "AcquisitionInputKind",
    "AcquisitionOutcome",
    "AcquisitionScenario",
    "CollectionCoverage",
    "CollectionExpectation",
    "IdempotencyOutcome",
    "ObjectiveCoverage",
    "evaluate_acquisition_outcome",
]
