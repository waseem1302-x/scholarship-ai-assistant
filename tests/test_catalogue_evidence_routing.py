import uuid

import app.modules.catalogue_ingestion.evidence_routing as evidence_routing_module
from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ScopedCoverageState
from app.modules.catalogue_ingestion.evidence_blocks import (
    DEFAULT_EVIDENCE_BLOCK_MAX_CHARS,
    build_evidence_blocks,
)
from app.modules.catalogue_ingestion.evidence_routing import (
    CatalogueEvidenceRouter,
    EvidenceRouteDecision,
    _route_is_selected,
    _RouteTarget,
)
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


def test_route_persistence_batches_selected_keys_and_omits_unselected(monkeypatch) -> None:
    class RecordingSession:
        def __init__(self) -> None:
            self.lookup_batch_sizes: list[int] = []
            self.added = []

        def scalars(self, statement):
            values = next(
                value
                for value in statement.compile().params.values()
                if isinstance(value, list)
            )
            self.lookup_batch_sizes.append(len(values))
            return []

        def add_all(self, records) -> None:
            self.added.extend(records)

        def flush(self) -> None:
            return None

    decisions = tuple(
        EvidenceRouteDecision(
            route_key=str(index) * 64,
            block_id=uuid.uuid4(),
            coverage_cell_id=None,
            scope_node_id=None,
            objective=ClaimObjective.FUNDING,
            scope_type=ScopeNodeType.SCHOLARSHIP_FAMILY.value,
            scope_key="scholarship",
            relevance_score=30,
            relevance_reasons=("objective_lexicon_match",),
            selected=index != 2,
            coverage_input_fingerprint=uuid.uuid4().hex * 2,
        )
        for index in range(4)
    )
    session = RecordingSession()
    router = CatalogueEvidenceRouter(session)
    monkeypatch.setattr(router, "decisions_for_candidate", lambda _candidate_id: decisions)
    monkeypatch.setattr(
        evidence_routing_module,
        "_ROUTE_KEY_LOOKUP_BATCH_SIZE",
        2,
        raising=False,
    )

    persisted = router.persist_candidate(uuid.uuid4())

    assert session.lookup_batch_sizes == [2, 1]
    assert len(persisted) == 3
    assert all(item.selected for item in persisted)


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


def test_semantic_lines_become_stable_exact_evidence_units() -> None:
    """A later fact must not disappear inside a 4,000-character mixed-topic block."""
    artifact_id = uuid.UUID("00000000-0000-0000-0000-000000000123")
    text = (
        "Eligibility\n"
        "Applicants must hold a bachelor's degree.\n"
        "Passport copy\n"
        "Academic transcript\n"
        "Appeals\n"
        "An appeal must be submitted within two days."
    )

    first = build_evidence_blocks(
        text,
        source_artifact_id=artifact_id,
        source_content_hash="b" * 64,
        source_role="primary",
    )
    second = build_evidence_blocks(
        text,
        source_artifact_id=artifact_id,
        source_content_hash="b" * 64,
        source_role="primary",
    )

    assert [block.block_text for block in first] == [
        "Eligibility\nApplicants must hold a bachelor's degree.\n",
        "Passport copy\n",
        "Academic transcript\n",
        "Appeals\nAn appeal must be submitted within two days.",
    ]
    assert "".join(block.block_text for block in first) == text
    assert [block.block_key for block in first] == [block.block_key for block in second]
    assert [(block.start_offset, block.end_offset) for block in first] == [
        (0, 54),
        (54, 68),
        (68, 88),
        (88, 140),
    ]
