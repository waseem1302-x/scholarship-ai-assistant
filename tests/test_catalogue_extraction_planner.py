import hashlib
import uuid
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
from app.modules.catalogue_ingestion.extraction_cache import CatalogueExtractionCache
from app.modules.catalogue_ingestion.extraction_planner import (
    ExtractionEvidenceRef,
    ExtractionJobPlan,
    ExtractionScopeTarget,
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
    left_text = left.evidence_text.split("\n", 1)[1].rsplit("\n</EVIDENCE_BLOCK>", 1)[0]
    right_text = right.evidence_text.split("\n", 1)[1].rsplit("\n</EVIDENCE_BLOCK>", 1)[0]
    assert left_text + right_text == block.block_text


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

    with pytest.raises(ExtractionSchemaError):
        service._expand_bundle(raw_output, job=left, blocks=[block])
