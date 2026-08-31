from decimal import Decimal

from app.core.config import Settings
from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ScopedCoverageState
from app.modules.catalogue_ingestion.models import (
    CatalogueCandidate,
    CatalogueIngestionRun,
    IngestionMode,
)
from app.modules.catalogue_ingestion.observability import CatalogueObservabilityService
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueCoverageCell,
    CatalogueScopeNode,
    ScopeDiscoveryConfidence,
    ScopeNodeType,
)


def test_candidate_observability_exposes_explicit_unresolved_scoped_branch(db_session) -> None:
    run = CatalogueIngestionRun(
        source_label="observability.json",
        source_fingerprint="f" * 64,
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
        max_candidates=1,
        max_pages_per_candidate=1,
        max_model_calls=1,
        max_input_characters=1_000,
        max_output_tokens=256,
        max_estimated_cost=Decimal("1"),
    )
    candidate = CatalogueCandidate(
        run=run,
        seed_index=0,
        idempotency_key="a" * 64,
        seed_name="Observable Scholarship",
    )
    db_session.add_all((run, candidate))
    db_session.flush()
    node = CatalogueScopeNode(
        candidate_id=candidate.id,
        node_type=ScopeNodeType.PROGRAMME,
        canonical_key="programme:example",
        display_label="Example programme",
        discovery_confidence=ScopeDiscoveryConfidence.HIGH,
        provenance_json={"asserted": True},
    )
    db_session.add(node)
    db_session.flush()
    coverage = CatalogueCoverageCell(
        candidate_id=candidate.id,
        objective=ClaimObjective.ELIGIBILITY,
        scope_node_id=node.id,
        state=ScopedCoverageState.BLOCKED,
        required=True,
        reason="official_programme_page_not_acquired",
        missing_frontier_reasons=["javascript_render_required"],
        evaluator_version="test.v1",
        input_fingerprint="b" * 64,
    )
    db_session.add(coverage)
    db_session.commit()

    response = CatalogueObservabilityService(
        db_session,
        Settings(
            env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret="test-secret-that-is-at-least-32-characters-long",
        ),
    ).candidate(candidate.id)

    assert response.lease.is_active is False
    assert response.topology.nodes[0].display_label == "Example programme"
    assert response.coverage[0].state is ScopedCoverageState.BLOCKED
    assert response.unresolved_branches[0].reason == "official_programme_page_not_acquired"
    assert response.unresolved_branches[0].missing_frontier_reasons == [
        "javascript_render_required"
    ]
    assert response.provider_attempts == []
