"""Zero-model evidence routing from immutable blocks to unresolved scoped coverage cells."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ScopedCoverageState
from app.modules.catalogue_ingestion.crawler import AcquisitionLexicon
from app.modules.catalogue_ingestion.evidence_block_models import (
    EVIDENCE_ROUTER_VERSION,
    CatalogueEvidenceBlock,
    CatalogueEvidenceRoute,
)
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueCoverageCell,
    CatalogueScopeNode,
    CatalogueSourceScopeLink,
    ScopeNodeType,
)

_OPEN_COVERAGE_STATES = frozenset(
    {
        ScopedCoverageState.UNKNOWN,
        ScopedCoverageState.NOT_YET_ACQUIRED,
        ScopedCoverageState.BLOCKED,
        ScopedCoverageState.PARTIAL,
        ScopedCoverageState.CONFLICTING,
        ScopedCoverageState.QUARANTINED,
        ScopedCoverageState.FAILED,
    }
)
_DEFAULT_SELECTION_THRESHOLD = 18


@dataclass(frozen=True, slots=True)
class EvidenceRouteDecision:
    route_key: str
    block_id: uuid.UUID
    coverage_cell_id: uuid.UUID
    scope_node_id: uuid.UUID
    objective: ClaimObjective
    scope_type: str
    scope_key: str
    relevance_score: int
    relevance_reasons: tuple[str, ...]
    selected: bool
    coverage_input_fingerprint: str
    router_version: str = EVIDENCE_ROUTER_VERSION


class CatalogueEvidenceRouter:
    """Build and persist the block × scope × objective relevance matrix without a model call."""

    def __init__(
        self,
        session: Session,
        *,
        lexicon_overrides: Mapping[str, Sequence[str]] | None = None,
        selection_threshold: int = _DEFAULT_SELECTION_THRESHOLD,
    ) -> None:
        if selection_threshold < 0:
            raise ValueError("selection_threshold cannot be negative")
        self.session = session
        self.lexicon = AcquisitionLexicon.from_mapping(lexicon_overrides)
        self.selection_threshold = selection_threshold

    def decisions_for_candidate(self, candidate_id: uuid.UUID) -> tuple[EvidenceRouteDecision, ...]:
        blocks = list(
            self.session.scalars(
                select(CatalogueEvidenceBlock)
                .where(CatalogueEvidenceBlock.candidate_id == candidate_id)
                .order_by(
                    CatalogueEvidenceBlock.source_artifact_id,
                    CatalogueEvidenceBlock.block_index,
                )
            )
        )
        if not blocks:
            return ()

        cells = list(
            self.session.scalars(
                select(CatalogueCoverageCell)
                .where(
                    CatalogueCoverageCell.candidate_id == candidate_id,
                    CatalogueCoverageCell.required.is_(True),
                    CatalogueCoverageCell.state.in_(_OPEN_COVERAGE_STATES),
                )
                .order_by(CatalogueCoverageCell.objective, CatalogueCoverageCell.scope_node_id)
            )
        )
        if not cells:
            return ()

        scope_ids = {cell.scope_node_id for cell in cells}
        scopes = {
            scope.id: scope
            for scope in self.session.scalars(
                select(CatalogueScopeNode).where(CatalogueScopeNode.id.in_(scope_ids))
            )
        }
        links = list(
            self.session.scalars(
                select(CatalogueSourceScopeLink).where(
                    CatalogueSourceScopeLink.candidate_id == candidate_id,
                    CatalogueSourceScopeLink.scope_node_id.in_(scope_ids),
                )
            )
        )
        linked_scopes = {(link.source_id, link.scope_node_id) for link in links}
        explicit_scopes = {
            (link.source_id, link.scope_node_id)
            for link in links
            if link.applicability_is_explicit
        }

        decisions: list[EvidenceRouteDecision] = []
        for block in blocks:
            for cell in cells:
                scope = scopes.get(cell.scope_node_id)
                if scope is None:
                    continue
                score, reasons, scope_signal = _score_block(
                    block,
                    cell,
                    scope,
                    terms=self.lexicon.terms_by_objective.get(cell.objective.value, ()),
                    source_linked=(block.source_id, scope.id) in linked_scopes,
                    applicability_explicit=(block.source_id, scope.id) in explicit_scopes,
                )
                selected = score >= self.selection_threshold and (
                    scope.node_type is ScopeNodeType.SCHOLARSHIP_FAMILY
                    or scope_signal
                    or cell.state is ScopedCoverageState.CONFLICTING
                )
                fingerprint = _coverage_route_fingerprint(cell, scope)
                decisions.append(
                    EvidenceRouteDecision(
                        route_key=_route_key(block.block_key, cell.id, fingerprint),
                        block_id=block.id,
                        coverage_cell_id=cell.id,
                        scope_node_id=scope.id,
                        objective=cell.objective,
                        scope_type=scope.node_type.value,
                        scope_key=scope.canonical_key,
                        relevance_score=score,
                        relevance_reasons=tuple(sorted(reasons)),
                        selected=selected,
                        coverage_input_fingerprint=fingerprint,
                    )
                )
        return tuple(decisions)

    def persist_candidate(self, candidate_id: uuid.UUID) -> list[CatalogueEvidenceRoute]:
        decisions = self.decisions_for_candidate(candidate_id)
        if not decisions:
            return []
        route_keys = [decision.route_key for decision in decisions]
        existing = set(
            self.session.scalars(
                select(CatalogueEvidenceRoute.route_key).where(
                    CatalogueEvidenceRoute.route_key.in_(route_keys)
                )
            )
        )
        records = [
            CatalogueEvidenceRoute(
                route_key=decision.route_key,
                candidate_id=candidate_id,
                evidence_block_id=decision.block_id,
                coverage_cell_id=decision.coverage_cell_id,
                scope_node_id=decision.scope_node_id,
                objective=decision.objective,
                scope_type=decision.scope_type,
                scope_key=decision.scope_key,
                relevance_score=decision.relevance_score,
                relevance_reasons=list(decision.relevance_reasons),
                selected=decision.selected,
                router_version=decision.router_version,
                coverage_input_fingerprint=decision.coverage_input_fingerprint,
            )
            for decision in decisions
            if decision.route_key not in existing
        ]
        self.session.add_all(records)
        self.session.flush()
        return records


def _score_block(
    block: CatalogueEvidenceBlock,
    cell: CatalogueCoverageCell,
    scope: CatalogueScopeNode,
    *,
    terms: Iterable[str],
    source_linked: bool,
    applicability_explicit: bool,
) -> tuple[int, set[str], bool]:
    text = " ".join(
        value
        for value in (
            block.heading or "",
            block.section_key or "",
            block.block_text,
            " ".join(block.topology_hints or []),
        )
        if value
    ).casefold()
    heading = (block.heading or "").casefold()
    score = 0
    reasons: set[str] = set()

    objective_matches = 0
    heading_matches = 0
    for raw_term in terms:
        term = raw_term.casefold().strip()
        if not term:
            continue
        if term in text:
            objective_matches += 1
        if term in heading:
            heading_matches += 1
    if objective_matches:
        score += min(objective_matches, 5) * 9
        reasons.add("objective_lexicon_match")
    if heading_matches:
        score += min(heading_matches, 3) * 8
        reasons.add("objective_heading_match")

    scope_tokens = _scope_tokens(scope)
    matched_scope_tokens = {token for token in scope_tokens if token in text}
    scope_signal = False
    if matched_scope_tokens:
        score += min(len(matched_scope_tokens), 4) * 8
        reasons.add("scope_text_match")
        scope_signal = True
    if source_linked:
        score += 18
        reasons.add("source_scope_link")
        scope_signal = True
    if applicability_explicit:
        score += 28
        reasons.add("explicit_scope_applicability")
        scope_signal = True
    if scope.node_type is ScopeNodeType.SCHOLARSHIP_FAMILY:
        score += 6
        reasons.add("scholarship_family_scope")
        scope_signal = True
    if cell.state is ScopedCoverageState.PARTIAL:
        score += 6
        reasons.add("partial_coverage")
    if cell.state is ScopedCoverageState.CONFLICTING:
        score += 16
        reasons.add("conflict_resolution")
    if cell.missing_frontier_reasons:
        missing_terms = _reason_tokens(cell.missing_frontier_reasons)
        if any(token in text for token in missing_terms):
            score += 12
            reasons.add("missing_frontier_match")
    if block.source_role in {"primary", "supporting"}:
        score += 3
        reasons.add("explicit_source_role")
    if block.language_hints:
        reasons.add("language_metadata_available")
    return score, reasons, scope_signal


def _scope_tokens(scope: CatalogueScopeNode) -> set[str]:
    values = [scope.canonical_key, scope.display_label, scope.lifecycle_key]
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue
        normalized = value.casefold().strip()
        if len(normalized) >= 2:
            tokens.add(normalized)
        tokens.update(
            item
            for item in re.split(r"[^\w]+", normalized, flags=re.UNICODE)
            if len(item) >= 3
        )
    return tokens


def _reason_tokens(reasons: Iterable[str]) -> set[str]:
    return {
        token
        for reason in reasons
        for token in re.split(r"[^\w]+", reason.casefold(), flags=re.UNICODE)
        if len(token) >= 4
    }


def _coverage_route_fingerprint(
    cell: CatalogueCoverageCell,
    scope: CatalogueScopeNode,
) -> str:
    payload = "|".join(
        (
            cell.input_fingerprint,
            cell.objective.value,
            cell.state.value,
            str(cell.required),
            str(cell.expected_item_count or ""),
            str(cell.resolved_item_count),
            scope.node_type.value,
            scope.canonical_key,
            scope.lifecycle_key,
            EVIDENCE_ROUTER_VERSION,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _route_key(block_key: str, coverage_cell_id: uuid.UUID, fingerprint: str) -> str:
    payload = f"{block_key}|{coverage_cell_id}|{fingerprint}|{EVIDENCE_ROUTER_VERSION}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "CatalogueEvidenceRouter",
    "EvidenceRouteDecision",
]
