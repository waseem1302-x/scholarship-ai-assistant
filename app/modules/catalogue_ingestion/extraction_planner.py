"""Deterministic multi-objective extraction jobs over complete evidence-block boundaries."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective
from app.modules.catalogue_ingestion.evidence_block_models import (
    CatalogueEvidenceBlock,
    CatalogueEvidenceRoute,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CatalogueCandidateSource,
)
from app.modules.catalogue_ingestion.topology_models import CatalogueCoverageCell

EXTRACTION_JOB_PLANNER_VERSION = "catalogue-extraction-jobs.v1"
_DEFAULT_PROMPT_RESERVE_CHARS = 8_000
_DEFAULT_MAX_EVIDENCE_CHARS = 48_000

_COMPATIBLE_OBJECTIVE_GROUPS: tuple[tuple[ClaimObjective, ...], ...] = (
    (
        ClaimObjective.IDENTITY,
        ClaimObjective.PROGRAMMES,
        ClaimObjective.PROGRAMME_DETAILS,
        ClaimObjective.ROUTES,
    ),
    (
        ClaimObjective.ELIGIBILITY,
        ClaimObjective.ELIGIBILITY_CONTEXT,
    ),
    (
        ClaimObjective.DOCUMENTS_CORE,
        ClaimObjective.DOCUMENTS_REQUIREMENTS,
        ClaimObjective.DOCUMENTS_COUNTS,
        ClaimObjective.DOCUMENTS_FORMAT,
    ),
    (ClaimObjective.FUNDING,),
    (ClaimObjective.APPLICATION_TIMELINE,),
)


@dataclass(frozen=True, slots=True)
class ExtractionScopeTarget:
    objective: ClaimObjective
    scope_type: str
    scope_key: str
    coverage_input_fingerprint: str


@dataclass(frozen=True, slots=True)
class ExtractionEvidenceRef:
    block_id: uuid.UUID
    block_key: str
    block_index: int
    block_hash: str
    start_offset: int
    end_offset: int
    heading: str | None


@dataclass(frozen=True, slots=True)
class ExtractionJobPlan:
    job_key: str
    source_id: uuid.UUID
    source_artifact_id: uuid.UUID
    source_content_hash: str
    evidence: tuple[ExtractionEvidenceRef, ...]
    objectives: tuple[ClaimObjective, ...]
    scopes: tuple[ExtractionScopeTarget, ...]
    evidence_text: str
    evidence_character_count: int
    estimated_input_tokens: int
    max_output_tokens: int
    estimated_cost_upper: Decimal
    planner_version: str = EXTRACTION_JOB_PLANNER_VERSION


@dataclass(frozen=True, slots=True)
class CandidateExtractionPlan:
    candidate_id: uuid.UUID
    jobs: tuple[ExtractionJobPlan, ...]
    estimated_calls: int
    estimated_input_tokens: int
    max_output_tokens: int
    estimated_cost_upper: Decimal
    refusal_reasons: tuple[str, ...] = ()


class CatalogueExtractionPlanner:
    """Create bounded paid-work jobs only from selected deterministic relevance routes."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def plan_candidate(
        self,
        candidate_id: uuid.UUID,
        *,
        max_input_characters: int,
        run_max_output_tokens: int,
        input_cost_per_million: Decimal,
        output_cost_per_million: Decimal,
    ) -> CandidateExtractionPlan:
        if max_input_characters <= _DEFAULT_PROMPT_RESERVE_CHARS:
            return CandidateExtractionPlan(
                candidate_id=candidate_id,
                jobs=(),
                estimated_calls=0,
                estimated_input_tokens=0,
                max_output_tokens=0,
                estimated_cost_upper=Decimal("0"),
                refusal_reasons=("input_budget_too_small_for_evidence_bundle",),
            )
        max_evidence_chars = min(
            _DEFAULT_MAX_EVIDENCE_CHARS,
            max_input_characters - _DEFAULT_PROMPT_RESERVE_CHARS,
        )
        blocks = list(
            self.session.scalars(
                select(CatalogueEvidenceBlock)
                .join(
                    CatalogueCandidateSource,
                    CatalogueCandidateSource.id == CatalogueEvidenceBlock.source_id,
                )
                .where(
                    CatalogueEvidenceBlock.candidate_id == candidate_id,
                    CatalogueCandidateSource.candidate_id == candidate_id,
                    CatalogueCandidateSource.is_official.is_(True),
                    CatalogueCandidateSource.status == CandidateSourceStatus.FETCHED,
                    CatalogueCandidateSource.content_hash.is_not(None),
                    CatalogueEvidenceBlock.source_content_hash
                    == CatalogueCandidateSource.content_hash,
                )
                .order_by(
                    CatalogueEvidenceBlock.source_artifact_id,
                    CatalogueEvidenceBlock.block_index,
                )
            )
        )
        has_current_coverage = self.session.scalar(
            select(CatalogueCoverageCell.id)
            .where(CatalogueCoverageCell.candidate_id == candidate_id)
            .limit(1)
        ) is not None
        route_query = select(CatalogueEvidenceRoute).where(
            CatalogueEvidenceRoute.candidate_id == candidate_id,
            CatalogueEvidenceRoute.selected.is_(True),
        )
        if has_current_coverage:
            route_query = route_query.where(CatalogueEvidenceRoute.coverage_cell_id.is_not(None))
        else:
            route_query = route_query.where(CatalogueEvidenceRoute.coverage_cell_id.is_(None))
        routes = list(self.session.scalars(route_query))
        if not blocks or not routes:
            return CandidateExtractionPlan(
                candidate_id=candidate_id,
                jobs=(),
                estimated_calls=0,
                estimated_input_tokens=0,
                max_output_tokens=0,
                estimated_cost_upper=Decimal("0"),
                refusal_reasons=("insufficient_routed_evidence",),
            )

        block_by_id = {block.id: block for block in blocks}
        routes_by_block: dict[uuid.UUID, list[CatalogueEvidenceRoute]] = {}
        for route in routes:
            if route.evidence_block_id in block_by_id:
                routes_by_block.setdefault(route.evidence_block_id, []).append(route)
        jobs: list[ExtractionJobPlan] = []
        for objective_group in _COMPATIBLE_OBJECTIVE_GROUPS:
            group_set = set(objective_group)
            by_artifact: dict[uuid.UUID, list[CatalogueEvidenceBlock]] = {}
            for block_id, block_routes in routes_by_block.items():
                if any(route.objective in group_set for route in block_routes):
                    block = block_by_id[block_id]
                    by_artifact.setdefault(block.source_artifact_id, []).append(block)
            for artifact_blocks in by_artifact.values():
                artifact_blocks.sort(key=lambda block: block.block_index)
                for chunk in _chunk_blocks(artifact_blocks, max_evidence_chars=max_evidence_chars):
                    chunk_ids = {block.id for block in chunk}
                    chunk_routes = [
                        route
                        for block_id in chunk_ids
                        for route in routes_by_block.get(block_id, [])
                        if route.objective in group_set
                    ]
                    objectives = tuple(
                        objective
                        for objective in objective_group
                        if any(route.objective is objective for route in chunk_routes)
                    )
                    if not objectives:
                        continue
                    jobs.append(
                        _build_job(
                            chunk,
                            chunk_routes,
                            objectives=objectives,
                            run_max_output_tokens=run_max_output_tokens,
                            input_cost_per_million=input_cost_per_million,
                            output_cost_per_million=output_cost_per_million,
                        )
                    )

        jobs.sort(
            key=lambda job: (
                str(job.source_artifact_id),
                job.evidence[0].block_index,
                tuple(objective.value for objective in job.objectives),
            )
        )
        return CandidateExtractionPlan(
            candidate_id=candidate_id,
            jobs=tuple(jobs),
            estimated_calls=len(jobs),
            estimated_input_tokens=sum(job.estimated_input_tokens for job in jobs),
            max_output_tokens=sum(job.max_output_tokens for job in jobs),
            estimated_cost_upper=sum(
                (job.estimated_cost_upper for job in jobs),
                start=Decimal("0"),
            ),
            refusal_reasons=() if jobs else ("insufficient_routed_evidence",),
        )


def split_extraction_job(
    job: ExtractionJobPlan,
    *,
    blocks_by_id: Mapping[uuid.UUID, CatalogueEvidenceBlock],
    routes: Sequence[CatalogueEvidenceRoute],
    run_max_output_tokens: int,
    input_cost_per_million: Decimal,
    output_cost_per_million: Decimal,
) -> tuple[ExtractionJobPlan, ...]:
    """Deterministically split one truncated job on existing evidence-block boundaries."""

    blocks = tuple(blocks_by_id[item.block_id] for item in job.evidence)
    if len(blocks) <= 1:
        return ()
    midpoint = len(blocks) // 2
    parts = (blocks[:midpoint], blocks[midpoint:])
    children: list[ExtractionJobPlan] = []
    objective_set = set(job.objectives)
    for part in parts:
        part_ids = {block.id for block in part}
        part_routes = [
            route
            for route in routes
            if route.selected
            and route.evidence_block_id in part_ids
            and route.objective in objective_set
        ]
        objectives = tuple(
            objective
            for objective in job.objectives
            if any(route.objective is objective for route in part_routes)
        )
        if not objectives:
            continue
        children.append(
            _build_job(
                part,
                part_routes,
                objectives=objectives,
                run_max_output_tokens=run_max_output_tokens,
                input_cost_per_million=input_cost_per_million,
                output_cost_per_million=output_cost_per_million,
            )
        )
    return tuple(children)


def _chunk_blocks(
    blocks: list[CatalogueEvidenceBlock],
    *,
    max_evidence_chars: int,
) -> tuple[tuple[CatalogueEvidenceBlock, ...], ...]:
    chunks: list[tuple[CatalogueEvidenceBlock, ...]] = []
    current: list[CatalogueEvidenceBlock] = []
    current_chars = 0
    for block in blocks:
        block_chars = len(_render_block(block))
        if block_chars > max_evidence_chars:
            raise ValueError("evidence block exceeds configured provider evidence budget")
        if current and current_chars + block_chars > max_evidence_chars:
            chunks.append(tuple(current))
            current = []
            current_chars = 0
        current.append(block)
        current_chars += block_chars
    if current:
        chunks.append(tuple(current))
    return tuple(chunks)


def _build_job(
    blocks: tuple[CatalogueEvidenceBlock, ...],
    routes: list[CatalogueEvidenceRoute],
    *,
    objectives: tuple[ClaimObjective, ...],
    run_max_output_tokens: int,
    input_cost_per_million: Decimal,
    output_cost_per_million: Decimal,
) -> ExtractionJobPlan:
    first = blocks[0]
    if any(block.source_artifact_id != first.source_artifact_id for block in blocks):
        raise ValueError("one extraction job cannot cross source artifacts")
    evidence = tuple(
        ExtractionEvidenceRef(
            block_id=block.id,
            block_key=block.block_key,
            block_index=block.block_index,
            block_hash=block.block_hash,
            start_offset=block.start_offset,
            end_offset=block.end_offset,
            heading=block.heading,
        )
        for block in blocks
    )
    evidence_text = "\n\n".join(_render_block(block) for block in blocks)
    scopes = tuple(
        sorted(
            {
                ExtractionScopeTarget(
                    objective=route.objective,
                    scope_type=route.scope_type,
                    scope_key=route.scope_key,
                    coverage_input_fingerprint=route.coverage_input_fingerprint,
                )
                for route in routes
            },
            key=lambda target: (
                target.objective.value,
                target.scope_type,
                target.scope_key,
                target.coverage_input_fingerprint,
            ),
        )
    )
    entity_estimate = max(1, len(scopes), len(blocks))
    max_output_tokens = min(
        run_max_output_tokens,
        max(600, 500 + len(objectives) * 450 + min(entity_estimate, 24) * 120),
    )
    estimated_input_tokens = max(1, (len(evidence_text) + _DEFAULT_PROMPT_RESERVE_CHARS) // 4)
    estimated_cost_upper = (
        Decimal(estimated_input_tokens) * input_cost_per_million
        + Decimal(max_output_tokens) * output_cost_per_million
    ) / Decimal(1_000_000)
    job_key = _job_key(first, evidence, scopes, objectives)
    return ExtractionJobPlan(
        job_key=job_key,
        source_id=first.source_id,
        source_artifact_id=first.source_artifact_id,
        source_content_hash=first.source_content_hash,
        evidence=evidence,
        objectives=objectives,
        scopes=scopes,
        evidence_text=evidence_text,
        evidence_character_count=len(evidence_text),
        estimated_input_tokens=estimated_input_tokens,
        max_output_tokens=max_output_tokens,
        estimated_cost_upper=estimated_cost_upper,
    )


def _render_block(block: CatalogueEvidenceBlock) -> str:
    metadata = {
        "block_key": block.block_key,
        "end_offset": block.end_offset,
        "heading": block.heading,
        "language_hints": block.language_hints,
        "section_key": block.section_key,
        "source_role": block.source_role,
        "start_offset": block.start_offset,
        "topology_hints": block.topology_hints,
    }
    header = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"<EVIDENCE_BLOCK {header}>\n{block.block_text}\n</EVIDENCE_BLOCK>"


def _job_key(
    first: CatalogueEvidenceBlock,
    evidence: tuple[ExtractionEvidenceRef, ...],
    scopes: tuple[ExtractionScopeTarget, ...],
    objectives: tuple[ClaimObjective, ...],
) -> str:
    payload = {
        "artifact_content_hash": first.source_content_hash,
        "evidence": [
            {
                "block_hash": item.block_hash,
                "end_offset": item.end_offset,
                "start_offset": item.start_offset,
            }
            for item in evidence
        ],
        "objectives": [objective.value for objective in objectives],
        "planner_version": EXTRACTION_JOB_PLANNER_VERSION,
        "scopes": [
            {
                "coverage_input_fingerprint": target.coverage_input_fingerprint,
                "objective": target.objective.value,
                "scope_key": target.scope_key,
                "scope_type": target.scope_type,
            }
            for target in scopes
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "EXTRACTION_JOB_PLANNER_VERSION",
    "CandidateExtractionPlan",
    "CatalogueExtractionPlanner",
    "ExtractionEvidenceRef",
    "ExtractionJobPlan",
    "ExtractionScopeTarget",
    "split_extraction_job",
]
