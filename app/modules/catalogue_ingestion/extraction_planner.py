"""Deterministic multi-objective extraction jobs over complete evidence-block boundaries."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective
from app.modules.catalogue_ingestion.crawler import AcquisitionLexicon
from app.modules.catalogue_ingestion.evidence_block_models import (
    CatalogueEvidenceBlock,
    CatalogueEvidenceRoute,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CatalogueCandidateSource,
)
from app.modules.catalogue_ingestion.topology_models import CatalogueCoverageCell

EXTRACTION_JOB_PLANNER_VERSION = "catalogue-extraction-jobs.v2"
_DEFAULT_PROMPT_RESERVE_CHARS = 8_000
_DEFAULT_MAX_EVIDENCE_CHARS = 48_000
_MIN_RECOVERY_SPAN_CHARS = 1_500

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
        has_current_coverage = (
            self.session.scalar(
                select(CatalogueCoverageCell.id)
                .where(CatalogueCoverageCell.candidate_id == candidate_id)
                .limit(1)
            )
            is not None
        )
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
    """Deterministically split a truncated job without losing evidence coverage."""

    split_single_block = len(job.evidence) == 1
    if not split_single_block:
        midpoint = len(job.evidence) // 2
        parts = (job.evidence[:midpoint], job.evidence[midpoint:])
    else:
        evidence = job.evidence[0]
        block = blocks_by_id[evidence.block_id]
        split_offset = _recovery_split_offset(block, evidence)
        if split_offset is None:
            return ()
        parts = (
            (_slice_evidence_ref(evidence, end_offset=split_offset),),
            (_slice_evidence_ref(evidence, start_offset=split_offset),),
        )
    children: list[ExtractionJobPlan] = []
    objective_set = set(job.objectives)
    slice_objectives = (
        _objectives_for_slices(parts, job.objectives, blocks_by_id)
        if split_single_block
        else None
    )
    for part_index, part in enumerate(parts):
        part_ids = {item.block_id for item in part}
        part_routes = [
            route
            for route in routes
            if route.selected
            and route.evidence_block_id in part_ids
            and route.objective in objective_set
            and (slice_objectives is None or route.objective in slice_objectives[part_index])
        ]
        objectives = tuple(
            objective
            for objective in job.objectives
            if any(route.objective is objective for route in part_routes)
        )
        if not objectives:
            continue
        children.append(
            _build_job_from_evidence(
                part,
                part_routes,
                blocks_by_id=blocks_by_id,
                objectives=objectives,
                run_max_output_tokens=run_max_output_tokens,
                input_cost_per_million=input_cost_per_million,
                output_cost_per_million=output_cost_per_million,
                output_token_floor=run_max_output_tokens,
            )
        )
    return tuple(children)


def _objectives_for_slices(
    parts: tuple[tuple[ExtractionEvidenceRef, ...], ...],
    objectives: tuple[ClaimObjective, ...],
    blocks_by_id: Mapping[uuid.UUID, CatalogueEvidenceBlock],
) -> tuple[set[ClaimObjective], ...]:
    """Route a split block by terms in each actual slice, retaining a safe tie fallback."""

    lexicon = AcquisitionLexicon.defaults()
    assigned = [set() for _part in parts]
    texts: list[str] = []
    for part in parts:
        fragments: list[str] = []
        for evidence in part:
            block = blocks_by_id[evidence.block_id]
            start = evidence.start_offset - block.start_offset
            end = evidence.end_offset - block.start_offset
            fragments.append(block.block_text[start:end].casefold())
        texts.append("\n".join(fragments))
    for objective in objectives:
        terms = lexicon.terms_by_objective.get(objective.value, ())
        scores = [sum(text.count(term.casefold()) for term in terms) for text in texts]
        best = max(scores, default=0)
        if best == 0:
            for target in assigned:
                target.add(objective)
            continue
        for index, score in enumerate(scores):
            if score == best:
                assigned[index].add(objective)
    return tuple(assigned)


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
    return _build_job_from_evidence(
        evidence,
        routes,
        blocks_by_id={block.id: block for block in blocks},
        objectives=objectives,
        run_max_output_tokens=run_max_output_tokens,
        input_cost_per_million=input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
    )


def _build_job_from_evidence(
    evidence: tuple[ExtractionEvidenceRef, ...],
    routes: list[CatalogueEvidenceRoute],
    *,
    blocks_by_id: Mapping[uuid.UUID, CatalogueEvidenceBlock],
    objectives: tuple[ClaimObjective, ...],
    run_max_output_tokens: int,
    input_cost_per_million: Decimal,
    output_cost_per_million: Decimal,
    output_token_floor: int = 0,
) -> ExtractionJobPlan:
    if not evidence:
        raise ValueError("one extraction job requires evidence")
    blocks = tuple(blocks_by_id[item.block_id] for item in evidence)
    first = blocks[0]
    if any(block.source_artifact_id != first.source_artifact_id for block in blocks):
        raise ValueError("one extraction job cannot cross source artifacts")
    evidence_text = "\n\n".join(
        _render_evidence_span(block, item) for block, item in zip(blocks, evidence, strict=True)
    )
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
    entity_estimate = max(1, len(scopes), len(blocks), _enumerated_row_estimate(evidence_text))
    max_output_tokens = min(
        run_max_output_tokens,
        max(
            output_token_floor,
            600,
            500 + len(objectives) * 450 + entity_estimate * 120,
        ),
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


def _enumerated_row_estimate(text: str) -> int:
    rows = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if re.match(r"^(?:[-*•]|\d{1,3}[.)]|\|)\s*\S", line):
            rows += 1
    return rows


def _render_block(block: CatalogueEvidenceBlock) -> str:
    evidence = ExtractionEvidenceRef(
        block_id=block.id,
        block_key=block.block_key,
        block_index=block.block_index,
        block_hash=block.block_hash,
        start_offset=block.start_offset,
        end_offset=block.end_offset,
        heading=block.heading,
    )
    return _render_evidence_span(block, evidence)


def _render_evidence_span(
    block: CatalogueEvidenceBlock,
    evidence: ExtractionEvidenceRef,
) -> str:
    local_start = evidence.start_offset - block.start_offset
    local_end = evidence.end_offset - block.start_offset
    if local_start < 0 or local_end > len(block.block_text) or local_start >= local_end:
        raise ValueError("evidence span falls outside its persisted block")
    metadata = {
        "block_key": evidence.block_key,
        "end_offset": evidence.end_offset,
        "heading": evidence.heading,
        "language_hints": block.language_hints,
        "section_key": block.section_key,
        "source_role": block.source_role,
        "start_offset": evidence.start_offset,
        "topology_hints": block.topology_hints,
    }
    header = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (
        f"<EVIDENCE_BLOCK {header}>\n"
        f"{block.block_text[local_start:local_end]}\n"
        "</EVIDENCE_BLOCK>"
    )


def _recovery_split_offset(
    block: CatalogueEvidenceBlock,
    evidence: ExtractionEvidenceRef,
) -> int | None:
    span_length = evidence.end_offset - evidence.start_offset
    if span_length < _MIN_RECOVERY_SPAN_CHARS * 2:
        return None
    local_start = evidence.start_offset - block.start_offset
    local_end = evidence.end_offset - block.start_offset
    if local_start < 0 or local_end > len(block.block_text) or local_start >= local_end:
        raise ValueError("evidence span falls outside its persisted block")

    midpoint = local_start + span_length // 2
    minimum = local_start + _MIN_RECOVERY_SPAN_CHARS
    maximum = local_end - _MIN_RECOVERY_SPAN_CHARS
    candidates: list[int] = []
    for separator in ("\n\n", "\n", ". ", " "):
        position = block.block_text.find(separator, minimum, maximum)
        while position >= 0:
            candidates.append(position + len(separator))
            position = block.block_text.find(separator, position + 1, maximum)
        if candidates:
            break
    local_split = (
        min(candidates, key=lambda value: abs(value - midpoint)) if candidates else midpoint
    )
    return block.start_offset + local_split


def _slice_evidence_ref(
    evidence: ExtractionEvidenceRef,
    *,
    start_offset: int | None = None,
    end_offset: int | None = None,
) -> ExtractionEvidenceRef:
    return ExtractionEvidenceRef(
        block_id=evidence.block_id,
        block_key=evidence.block_key,
        block_index=evidence.block_index,
        block_hash=evidence.block_hash,
        start_offset=evidence.start_offset if start_offset is None else start_offset,
        end_offset=evidence.end_offset if end_offset is None else end_offset,
        heading=evidence.heading,
    )


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
