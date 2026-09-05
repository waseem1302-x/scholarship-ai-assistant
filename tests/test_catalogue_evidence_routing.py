import uuid

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ScopedCoverageState
from app.modules.catalogue_ingestion.evidence_blocks import (
    DEFAULT_EVIDENCE_BLOCK_MAX_CHARS,
    build_evidence_blocks,
)
from app.modules.catalogue_ingestion.evidence_routing import _route_is_selected, _RouteTarget
from app.modules.catalogue_ingestion.topology_models import ScopeNodeType


def _target() -> _RouteTarget:
    return _RouteTarget(
        coverage_cell_id=None,
        scope_node_id=None,
        objective=ClaimObjective.FUNDING,
        state=ScopedCoverageState.UNKNOWN,
        scope_type=ScopeNodeType.SCHOLARSHIP_FAMILY.value,
        scope_key="scholarship",
        display_label="Scholarship",
        lifecycle_key="",
        missing_frontier_reasons=("initial_extraction_frontier",),
        expected_item_count=None,
        resolved_item_count=0,
        input_fingerprint=uuid.uuid4().hex,
    )


def test_official_source_link_alone_does_not_schedule_an_unrelated_paid_objective() -> None:
    assert not _route_is_selected(
        score=24,
        reasons={"source_scope_link", "scholarship_family_scope"},
        target=_target(),
        scope_signal=True,
        selection_threshold=18,
    )


def test_topic_match_schedules_the_relevant_paid_objective() -> None:
    assert _route_is_selected(
        score=33,
        reasons={"objective_lexicon_match", "scholarship_family_scope"},
        target=_target(),
        scope_signal=True,
        selection_threshold=18,
    )


def test_large_mixed_page_is_partitioned_into_compact_non_overlapping_blocks() -> None:
    sections = [
        f"SECTION {index}:\n" + (f"Scholarship detail {index}. " * 220)
        for index in range(8)
    ]
    text = "\n\n".join(sections)

    blocks = build_evidence_blocks(
        text,
        source_artifact_id=uuid.uuid4(),
        source_content_hash="a" * 64,
        source_role="primary",
    )

    assert len(blocks) > 3
    assert max(len(block.block_text) for block in blocks) <= DEFAULT_EVIDENCE_BLOCK_MAX_CHARS
    assert "".join(block.block_text for block in blocks) == text
