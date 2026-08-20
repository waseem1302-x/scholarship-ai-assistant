import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.catalogue_ingestion.acquisition_contract import (
    AcquisitionContractManifest,
    AcquisitionInputKind,
    AcquisitionOutcome,
    AcquisitionScenario,
    CollectionCoverage,
    IdempotencyOutcome,
    ObjectiveCoverage,
    evaluate_acquisition_outcome,
)
from app.modules.catalogue_ingestion.discovery import DiscoveryObjectiveKind

FIXTURE = (
    Path(__file__).parent / "fixtures" / "catalogue_acquisition" / "complete_acquisition_v1.json"
)


def _manifest() -> AcquisitionContractManifest:
    return AcquisitionContractManifest.model_validate(
        json.loads(FIXTURE.read_text(encoding="utf-8"))
    )


def _scenario(identifier: str) -> AcquisitionScenario:
    return next(item for item in _manifest().scenarios if item.scenario_id == identifier)


def _passing_outcome(scenario: AcquisitionScenario) -> AcquisitionOutcome:
    objective_coverage = tuple(
        ObjectiveCoverage(
            objective=objective,
            target_count=scenario.expected_canonical_scholarship_count,
            resolved_count=scenario.expected_canonical_scholarship_count,
            explicit_unknown_count=0,
            source_checked_count=scenario.expected_canonical_scholarship_count,
            evidence_backed_count=scenario.expected_canonical_scholarship_count,
            scope_preserved_count=scenario.expected_canonical_scholarship_count,
            conflict_count=0,
        )
        for objective in scenario.required_objectives
    )
    collection_coverage = tuple(
        CollectionCoverage(
            objective=expectation.objective,
            authoritative_source_items=(
                280
                if expectation.objective is DiscoveryObjectiveKind.PARTICIPATING_INSTITUTIONS
                else expectation.minimum_items
            ),
            graph_items_persisted=(
                280
                if expectation.objective is DiscoveryObjectiveKind.PARTICIPATING_INSTITUTIONS
                else expectation.minimum_items
            ),
            duplicate_graph_items=0,
            authoritative_source_complete=True,
        )
        for expectation in scenario.collections
    )
    return AcquisitionOutcome(
        scenario_id=scenario.scenario_id,
        operator_supplied_url_count=scenario.operator_supplied_url_count,
        seed_candidates_created=scenario.expected_seed_candidate_count,
        canonical_scholarships_resolved=scenario.expected_canonical_scholarship_count,
        owner_types_observed=scenario.required_owner_types,
        objective_coverage=objective_coverage,
        collection_coverage=collection_coverage,
        manual_followup_urls=0,
        automatic_publications=0,
        idempotency=IdempotencyOutcome(
            new_canonical_scholarships_on_rerun=0,
            new_relationships_on_rerun=0,
            new_sources_on_rerun=0,
            model_calls_for_unchanged_sources=0,
        ),
    )


def test_manifest_covers_url_name_and_document_entry_points() -> None:
    manifest = _manifest()

    assert manifest.execution_evidence is False
    assert {scenario.input_kind for scenario in manifest.scenarios} == {
        AcquisitionInputKind.URL,
        AcquisitionInputKind.NAME,
        AcquisitionInputKind.DOCUMENT,
    }
    assert all(scenario.max_manual_followup_urls == 0 for scenario in manifest.scenarios)
    assert all(scenario.automatic_publication_allowed is False for scenario in manifest.scenarios)


@pytest.mark.parametrize(
    "scenario_id",
    (
        "csc_root_to_complete_graph",
        "mext_name_to_complete_core",
        "text_pdf_to_independent_acquisition_runs",
    ),
)
def test_target_scenario_examples_satisfy_the_contract(scenario_id: str) -> None:
    scenario = _scenario(scenario_id)

    assert evaluate_acquisition_outcome(scenario, _passing_outcome(scenario)) == ()


def test_csc_contract_requires_one_scholarship_and_complete_source_derived_institutions() -> None:
    scenario = _scenario("csc_root_to_complete_graph")
    outcome = _passing_outcome(scenario)

    assert scenario.expected_canonical_scholarship_count == 1
    participation = next(
        item
        for item in outcome.collection_coverage
        if item.objective is DiscoveryObjectiveKind.PARTICIPATING_INSTITUTIONS
    )
    assert participation.authoritative_source_items == 280
    assert participation.graph_items_persisted == 280
    assert evaluate_acquisition_outcome(scenario, outcome) == ()

    inflated = outcome.model_copy(update={"canonical_scholarships_resolved": 281})
    assert "canonical_scholarship_count_failed" in evaluate_acquisition_outcome(scenario, inflated)
    incomplete_collection = participation.model_copy(update={"graph_items_persisted": 279})
    changed_collections = tuple(
        incomplete_collection if item.objective is participation.objective else item
        for item in outcome.collection_coverage
    )
    incomplete = outcome.model_copy(update={"collection_coverage": changed_collections})
    assert "collection_graph_mismatch:participating_institutions" in (
        evaluate_acquisition_outcome(scenario, incomplete)
    )


def test_contract_rejects_missing_evidence_scope_and_unresolved_conflict() -> None:
    scenario = _scenario("mext_name_to_complete_core")
    outcome = _passing_outcome(scenario)
    funding = next(
        item
        for item in outcome.objective_coverage
        if item.objective is DiscoveryObjectiveKind.FUNDING_COVERAGE
    )
    invalid_funding = funding.model_copy(
        update={
            "resolved_count": 0,
            "evidence_backed_count": 0,
            "scope_preserved_count": 0,
            "conflict_count": 1,
        }
    )
    changed_coverage = tuple(
        invalid_funding if item.objective is funding.objective else item
        for item in outcome.objective_coverage
    )

    violations = evaluate_acquisition_outcome(
        scenario,
        outcome.model_copy(update={"objective_coverage": changed_coverage}),
    )

    assert "objective_completeness_failed:funding_coverage" in violations
    assert "objective_scope_failed:funding_coverage" in violations
    assert "objective_conflict_unresolved:funding_coverage" in violations

    uncited_funding = funding.model_copy(update={"evidence_backed_count": 0})
    uncited_coverage = tuple(
        uncited_funding if item.objective is funding.objective else item
        for item in outcome.objective_coverage
    )
    assert "objective_evidence_failed:funding_coverage" in evaluate_acquisition_outcome(
        scenario,
        outcome.model_copy(update={"objective_coverage": uncited_coverage}),
    )


def test_contract_rejects_manual_completion_auto_publication_and_non_idempotent_rerun() -> None:
    scenario = _scenario("text_pdf_to_independent_acquisition_runs")
    outcome = _passing_outcome(scenario)
    invalid = outcome.model_copy(
        update={
            "manual_followup_urls": 1,
            "automatic_publications": 1,
            "idempotency": IdempotencyOutcome(
                new_canonical_scholarships_on_rerun=1,
                new_relationships_on_rerun=1,
                new_sources_on_rerun=1,
                model_calls_for_unchanged_sources=1,
            ),
        }
    )

    violations = evaluate_acquisition_outcome(scenario, invalid)

    assert "manual_followup_budget_failed" in violations
    assert "automatic_publication_forbidden" in violations
    assert "idempotent_rerun_failed" in violations


def test_scenario_schema_rejects_a_name_contract_with_an_operator_url() -> None:
    scenario = _scenario("mext_name_to_complete_core")

    with pytest.raises(ValidationError, match="only URL scenarios"):
        AcquisitionScenario.model_validate(
            scenario.model_dump() | {"operator_supplied_url_count": 1}
        )

    with pytest.raises(ValidationError, match="cannot exceed seed candidate count"):
        AcquisitionScenario.model_validate(
            scenario.model_dump() | {"expected_canonical_scholarship_count": 2}
        )
