import hashlib
import uuid
from dataclasses import replace
from decimal import Decimal

import pytest

from app.modules.catalogue_ingestion.claim_bundle_schemas import (
    BundleEvidenceReference,
    BundleObjectiveCoverage,
    ClaimBundleExtractionOutput,
)
from app.modules.catalogue_ingestion.claim_provider import ExtractionSchemaError
from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ObjectiveCoverageState
from app.modules.catalogue_ingestion.evidence_block_models import (
    EVIDENCE_BLOCK_BUILDER_VERSION,
    CatalogueEvidenceBlock,
    CatalogueEvidenceRoute,
)
from app.modules.catalogue_ingestion.evidence_blocks import build_evidence_blocks
from app.modules.catalogue_ingestion.extraction_cache import CatalogueExtractionCache
from app.modules.catalogue_ingestion.extraction_planner import (
    ExtractionEvidenceRef,
    ExtractionJobPlan,
    ExtractionScopeTarget,
    _build_artifact_jobs,
    split_extraction_job,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceRole,
    CandidateSourceStatus,
    CatalogueCandidateSource,
    CatalogueSourceArtifact,
)
from app.modules.catalogue_ingestion.production_service import (
    ProductionCatalogueIngestionService,
)


def _single_block_job() -> tuple[
    ExtractionJobPlan,
    CatalogueEvidenceBlock,
    CatalogueEvidenceRoute,
]:
    candidate_id = uuid.uuid4()
    source_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    text = f"{'A' * 6_000}\n\nOUTSIDE-SLICE-MARKER{'B' * 6_000}"
    block = CatalogueEvidenceBlock(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        source_id=source_id,
        source_artifact_id=artifact_id,
        block_index=0,
        block_key="b" * 64,
        block_hash=hashlib.sha256(text.encode()).hexdigest(),
        source_content_hash="c" * 64,
        start_offset=0,
        end_offset=len(text),
        block_text=text,
        heading="Application timeline",
        section_key="application-timeline",
        coordinate_json=[],
        topology_hints=[],
        language_hints=["en"],
        source_role=CandidateSourceRole.PRIMARY.value,
        builder_version=EVIDENCE_BLOCK_BUILDER_VERSION,
    )
    route = CatalogueEvidenceRoute(
        id=uuid.uuid4(),
        route_key="r" * 64,
        candidate_id=candidate_id,
        evidence_block_id=block.id,
        coverage_cell_id=None,
        scope_node_id=None,
        objective=ClaimObjective.APPLICATION_TIMELINE,
        scope_type="opportunity",
        scope_key="root",
        relevance_score=100,
        relevance_reasons=["timeline heading"],
        selected=True,
        coverage_input_fingerprint="f" * 64,
    )
    evidence = ExtractionEvidenceRef(
        block_id=block.id,
        block_key=block.block_key,
        block_index=block.block_index,
        block_hash=block.block_hash,
        start_offset=block.start_offset,
        end_offset=block.end_offset,
        heading=block.heading,
    )
    scope = ExtractionScopeTarget(
        objective=route.objective,
        scope_type=route.scope_type,
        scope_key=route.scope_key,
        coverage_input_fingerprint=route.coverage_input_fingerprint,
    )
    job = ExtractionJobPlan(
        job_key="parent",
        source_id=source_id,
        source_artifact_id=artifact_id,
        source_content_hash=block.source_content_hash,
        evidence=(evidence,),
        objectives=(ClaimObjective.APPLICATION_TIMELINE,),
        scopes=(scope,),
        evidence_text=text,
        evidence_character_count=len(text),
        estimated_input_tokens=5_000,
        max_output_tokens=1_070,
        estimated_cost_upper=Decimal("0.01"),
    )
    return job, block, route


def test_truncated_single_block_job_splits_into_contiguous_evidence_spans() -> None:
    job, block, route = _single_block_job()

    children = split_extraction_job(
        job,
        blocks_by_id={block.id: block},
        routes=[route],
        run_max_output_tokens=6_000,
        input_cost_per_million=Decimal("0.25"),
        output_cost_per_million=Decimal("2.00"),
    )

    assert len(children) == 2
    left, right = children
    assert left.evidence[0].start_offset == 0
    assert left.evidence[0].end_offset == right.evidence[0].start_offset
    assert right.evidence[0].end_offset == len(block.block_text)
    assert left.job_key != right.job_key
    assert left.max_output_tokens == 6_000
    assert right.max_output_tokens == 6_000
    assert left.recovery_depth == 1
    assert right.recovery_depth == 1
    left_text = left.evidence_text.split("\n", 1)[1].rsplit("\n</EVIDENCE_BLOCK>", 1)[0]
    right_text = right.evidence_text.split("\n", 1)[1].rsplit("\n</EVIDENCE_BLOCK>", 1)[0]
    assert left_text + right_text == block.block_text

    assert (
        split_extraction_job(
            left,
            blocks_by_id={block.id: block},
            routes=[route],
            run_max_output_tokens=6_000,
            input_cost_per_million=Decimal("0.25"),
            output_cost_per_million=Decimal("2.00"),
        )
        == ()
    )


def test_cache_identity_distinguishes_slices_of_the_same_evidence_block(db_session) -> None:
    job, block, _route = _single_block_job()
    source = CatalogueCandidateSource(
        id=job.source_id,
        candidate_id=block.candidate_id,
        url="https://example.edu/scholarship",
        canonical_url="https://example.edu/scholarship",
        final_url="https://example.edu/scholarship",
        source_role=CandidateSourceRole.PRIMARY,
        status=CandidateSourceStatus.FETCHED,
        is_official=True,
        trust_tier=1,
        classification_reason="reviewed official source",
        content_type="text/html",
        content_hash=block.source_content_hash,
    )
    artifact = CatalogueSourceArtifact(
        id=job.source_artifact_id,
        source_id=job.source_id,
        final_url=source.final_url,
        content_type="text/html",
        content_hash=block.source_content_hash,
        normalized_text=block.block_text,
        extraction_method="normalized_text",
        byte_count=len(block.block_text.encode()),
        character_count=len(block.block_text),
        fetch_metadata={},
    )
    cache = CatalogueExtractionCache(db_session)
    common = {
        "source": source,
        "artifact": artifact,
        "blocks": [block],
        "routes": [],
        "objectives": [ClaimObjective.APPLICATION_TIMELINE.value],
        "prompt_hash": "p" * 64,
        "schema_version": "schema.v1",
        "parser_version": "parser.v1",
        "normalizer_version": "normalizer.v1",
        "resolver_version": "resolver.v1",
        "validator_version": "validator.v1",
        "provider": "provider",
        "model": "model",
        "capability_identity": "capability",
    }

    left = cache.build_identity(**common, evidence_spans=[(block.block_key, 0, 6_000)])
    right = cache.build_identity(
        **common,
        evidence_spans=[(block.block_key, 6_002, len(block.block_text))],
    )

    assert left.cache_key != right.cache_key


def test_recovery_child_rejects_evidence_outside_its_supplied_span() -> None:
    job, block, route = _single_block_job()
    left, _right = split_extraction_job(
        job,
        blocks_by_id={block.id: block},
        routes=[route],
        run_max_output_tokens=6_000,
        input_cost_per_million=Decimal("0.25"),
        output_cost_per_million=Decimal("2.00"),
    )
    excerpt = "OUTSIDE-SLICE-MARKER"
    excerpt_start = block.block_text.index(excerpt)
    raw_output = ClaimBundleExtractionOutput(
        evidence_refs=[
            BundleEvidenceReference(
                ref_id="outside",
                block_key=block.block_key,
                excerpt=excerpt,
                excerpt_start=excerpt_start,
                excerpt_end=excerpt_start + len(excerpt),
            )
        ],
        claims=[],
        objective_coverage=[
            BundleObjectiveCoverage(
                objective=ClaimObjective.APPLICATION_TIMELINE,
                coverage_state=ObjectiveCoverageState.PARTIAL,
                unknown_objectives=[],
            )
        ],
    )
    service = object.__new__(ProductionCatalogueIngestionService)

    with pytest.raises(ExtractionSchemaError) as exc_info:
        service._expand_bundle(raw_output, job=left, blocks=[block])

    assert "invalid_evidence_span:outside" in str(exc_info.value)


def test_truncation_recovery_keeps_all_objectives_on_each_bounded_slice() -> None:
    job, block, timeline_route = _single_block_job()
    text = ("Funding stipend tuition benefits. " * 220) + "\n\n" + (
        "Eligibility age nationality language requirements. " * 180
    )
    block.block_text = text
    block.end_offset = len(text)
    block.block_hash = hashlib.sha256(text.encode()).hexdigest()
    evidence = replace(job.evidence[0], end_offset=len(text), block_hash=block.block_hash)

    def route(objective: ClaimObjective, marker: str) -> CatalogueEvidenceRoute:
        return CatalogueEvidenceRoute(
            id=uuid.uuid4(),
            route_key=marker * 64,
            candidate_id=timeline_route.candidate_id,
            evidence_block_id=block.id,
            coverage_cell_id=None,
            scope_node_id=None,
            objective=objective,
            scope_type="opportunity",
            scope_key="root",
            relevance_score=100,
            relevance_reasons=["objective match"],
            selected=True,
            coverage_input_fingerprint=marker * 64,
        )

    funding_route = route(ClaimObjective.FUNDING, "f")
    eligibility_route = route(ClaimObjective.ELIGIBILITY, "e")
    job = replace(
        job,
        evidence=(evidence,),
        objectives=(ClaimObjective.ELIGIBILITY, ClaimObjective.FUNDING),
        evidence_text=text,
        evidence_character_count=len(text),
    )

    left, right = split_extraction_job(
        job,
        blocks_by_id={block.id: block},
        routes=[funding_route, eligibility_route],
        run_max_output_tokens=6_000,
        input_cost_per_million=Decimal("0.25"),
        output_cost_per_million=Decimal("2.00"),
    )

    assert left.objectives == (ClaimObjective.ELIGIBILITY, ClaimObjective.FUNDING)
    assert right.objectives == (ClaimObjective.ELIGIBILITY, ClaimObjective.FUNDING)


def test_primary_planner_extracts_each_block_once_across_all_objectives() -> None:
    job, block, timeline_route = _single_block_job()

    def route(objective: ClaimObjective, marker: str) -> CatalogueEvidenceRoute:
        return CatalogueEvidenceRoute(
            id=uuid.uuid4(),
            route_key=marker * 64,
            candidate_id=timeline_route.candidate_id,
            evidence_block_id=block.id,
            coverage_cell_id=None,
            scope_node_id=None,
            objective=objective,
            scope_type="scholarship_family",
            scope_key="scholarship",
            relevance_score=100,
            relevance_reasons=["objective_lexicon_match"],
            selected=True,
            coverage_input_fingerprint=marker * 64,
        )

    routes = [
        route(ClaimObjective.IDENTITY, "i"),
        route(ClaimObjective.ELIGIBILITY, "e"),
        route(ClaimObjective.FUNDING, "f"),
        timeline_route,
    ]

    jobs = _build_artifact_jobs(
        [block],
        routes_by_block={block.id: routes},
        max_evidence_chars=20_000,
        run_max_output_tokens=6_000,
        input_cost_per_million=Decimal("0.25"),
        output_cost_per_million=Decimal("2.00"),
    )

    assert len(jobs) == 1
    assert jobs[0].evidence == (job.evidence[0],)
    assert jobs[0].objectives == tuple(ClaimObjective)
    assert jobs[0].max_output_tokens == 6_000


def test_primary_planner_does_not_drop_an_unrouted_official_block() -> None:
    _job, block, _route = _single_block_job()

    jobs = _build_artifact_jobs(
        [block],
        routes_by_block={},
        max_evidence_chars=20_000,
        run_max_output_tokens=6_000,
        input_cost_per_million=Decimal("0.25"),
        output_cost_per_million=Decimal("2.00"),
    )

    assert len(jobs) == 1
    assert jobs[0].evidence[0].block_id == block.id
    assert jobs[0].objectives == tuple(ClaimObjective)
    assert jobs[0].scopes == ()


def test_open_doors_sized_page_does_not_multiply_packets_by_objective() -> None:
    candidate_id = uuid.uuid4()
    source_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    text = "\n\n".join(
        f"SECTION {index}:\n" + ("Official scholarship information. " * 120)
        for index in range(8)
    )
    specs = build_evidence_blocks(
        text,
        source_artifact_id=artifact_id,
        source_content_hash="c" * 64,
        source_role="primary",
    )
    blocks = [
        CatalogueEvidenceBlock(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            source_id=source_id,
            source_artifact_id=artifact_id,
            block_index=spec.block_index,
            block_key=spec.block_key,
            block_hash=spec.block_hash,
            source_content_hash=spec.source_content_hash,
            start_offset=spec.start_offset,
            end_offset=spec.end_offset,
            block_text=spec.block_text,
            heading=spec.heading,
            section_key=spec.section_key,
            coordinate_json=[],
            topology_hints=[],
            language_hints=["en"],
            source_role="primary",
            builder_version=spec.builder_version,
        )
        for spec in specs
    ]
    routes_by_block: dict[uuid.UUID, list[CatalogueEvidenceRoute]] = {}
    for block in blocks:
        routes_by_block[block.id] = [
            CatalogueEvidenceRoute(
                id=uuid.uuid4(),
                route_key=hashlib.sha256(f"{block.id}|{objective.value}".encode()).hexdigest(),
                candidate_id=candidate_id,
                evidence_block_id=block.id,
                coverage_cell_id=None,
                scope_node_id=None,
                objective=objective,
                scope_type="scholarship_family",
                scope_key="scholarship",
                relevance_score=100,
                relevance_reasons=["objective_lexicon_match"],
                selected=True,
                coverage_input_fingerprint=hashlib.sha256(
                    objective.value.encode()
                ).hexdigest(),
            )
            for objective in ClaimObjective
        ]

    jobs = _build_artifact_jobs(
        blocks,
        routes_by_block=routes_by_block,
        max_evidence_chars=48_000,
        run_max_output_tokens=6_000,
        input_cost_per_million=Decimal("0.25"),
        output_cost_per_million=Decimal("2.00"),
    )

    planned_block_ids = [ref.block_id for job in jobs for ref in job.evidence]
    assert len(jobs) == 1
    assert planned_block_ids == [block.id for block in blocks]
    assert all(job.objectives == tuple(ClaimObjective) for job in jobs)
