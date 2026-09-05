"""Zero-model evidence routing from immutable blocks to unresolved scoped coverage cells."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

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
        ScopedCoverageState.NOT_STATED,
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
    coverage_cell_id: uuid.UUID | None
    scope_node_id: uuid.UUID | None
    objective: ClaimObjective
    scope_type: str
    scope_key: str
    relevance_score: int
    relevance_reasons: tuple[str, ...]
    selected: bool
    coverage_input_fingerprint: str
    router_version: str = EVIDENCE_ROUTER_VERSION


@dataclass(frozen=True, slots=True)
class _RouteTarget:
    coverage_cell_id: uuid.UUID | None
    scope_node_id: uuid.UUID | None
    objective: ClaimObjective
    state: ScopedCoverageState
    scope_type: str
    scope_key: str
    display_label: str
    lifecycle_key: str
    missing_frontier_reasons: tuple[str, ...]
    expected_item_count: int | None
    resolved_item_count: int
    input_fingerprint: str

    @property
    def identity(self) -> str:
        if self.coverage_cell_id is not None:
            return str(self.coverage_cell_id)
        return f"initial:{self.objective.value}:{self.scope_type}:{self.scope_key}"


class CatalogueEvidenceRouter:
    """Build and persist the block x scope x objective relevance matrix without a model call."""

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

        targets = self._targets(candidate_id)
        if not targets:
            return ()
        scope_ids = {target.scope_node_id for target in targets if target.scope_node_id is not None}
        links = (
            list(
                self.session.scalars(
                    select(CatalogueSourceScopeLink).where(
                        CatalogueSourceScopeLink.candidate_id == candidate_id,
                        CatalogueSourceScopeLink.scope_node_id.in_(scope_ids),
                    )
                )
            )
            if scope_ids
            else []
        )
        linked_scopes = {(link.source_id, link.scope_node_id) for link in links}
        explicit_scopes = {
            (link.source_id, link.scope_node_id) for link in links if link.applicability_is_explicit
        }

        decisions: list[EvidenceRouteDecision] = []
        for block in blocks:
            for target in targets:
                link_key = (block.source_id, target.scope_node_id)
                score, reasons, scope_signal = _score_block(
                    block,
                    target,
                    terms=self.lexicon.terms_by_objective.get(target.objective.value, ()),
                    source_linked=target.scope_node_id is not None and link_key in linked_scopes,
                    applicability_explicit=(
                        target.scope_node_id is not None and link_key in explicit_scopes
                    ),
                )
                selected = _route_is_selected(
                    score=score,
                    reasons=reasons,
                    target=target,
                    scope_signal=scope_signal,
                    selection_threshold=self.selection_threshold,
                )
                fingerprint = _coverage_route_fingerprint(target)
                decisions.append(
                    EvidenceRouteDecision(
                        route_key=_route_key(block.block_key, target.identity, fingerprint),
                        block_id=block.id,
                        coverage_cell_id=target.coverage_cell_id,
                        scope_node_id=target.scope_node_id,
                        objective=target.objective,
                        scope_type=target.scope_type,
                        scope_key=target.scope_key,
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

    def _targets(self, candidate_id: uuid.UUID) -> tuple[_RouteTarget, ...]:
        all_cells = list(
            self.session.scalars(
                select(CatalogueCoverageCell)
                .where(
                    CatalogueCoverageCell.candidate_id == candidate_id,
                    CatalogueCoverageCell.required.is_(True),
                )
                .order_by(CatalogueCoverageCell.objective, CatalogueCoverageCell.scope_node_id)
            )
        )
        if not all_cells:
            return tuple(_initial_target(candidate_id, objective) for objective in ClaimObjective)

        cells = [cell for cell in all_cells if cell.state in _OPEN_COVERAGE_STATES]
        if not cells:
            return ()
        scope_ids = {cell.scope_node_id for cell in cells}
        scopes = {
            scope.id: scope
            for scope in self.session.scalars(
                select(CatalogueScopeNode).where(CatalogueScopeNode.id.in_(scope_ids))
            )
        }
        targets: list[_RouteTarget] = []
        for cell in cells:
            scope = scopes.get(cell.scope_node_id)
            if scope is None:
                continue
            targets.append(
                _RouteTarget(
                    coverage_cell_id=cell.id,
                    scope_node_id=scope.id,
                    objective=cell.objective,
                    state=cell.state,
                    scope_type=scope.node_type.value,
                    scope_key=scope.canonical_key,
                    display_label=scope.display_label,
                    lifecycle_key=scope.lifecycle_key,
                    missing_frontier_reasons=tuple(cell.missing_frontier_reasons or (cell.reason,)),
                    expected_item_count=cell.expected_item_count,
                    resolved_item_count=cell.resolved_item_count,
                    input_fingerprint=cell.input_fingerprint,
                )
            )
        return tuple(targets)


def _initial_target(candidate_id: uuid.UUID, objective: ClaimObjective) -> _RouteTarget:
    seed = f"{candidate_id}|{objective.value}|initial_unknown|{EVIDENCE_ROUTER_VERSION}"
    return _RouteTarget(
        coverage_cell_id=None,
        scope_node_id=None,
        objective=objective,
        state=ScopedCoverageState.UNKNOWN,
        scope_type=ScopeNodeType.SCHOLARSHIP_FAMILY.value,
        scope_key="scholarship",
        display_label="Scholarship",
        lifecycle_key="",
        missing_frontier_reasons=("initial_extraction_frontier",),
        expected_item_count=None,
        resolved_item_count=0,
        input_fingerprint=hashlib.sha256(seed.encode("utf-8")).hexdigest(),
    )


def _score_block(
    block: CatalogueEvidenceBlock,
    target: _RouteTarget,
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

    scope_tokens = _scope_tokens(target)
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
    if target.scope_type == ScopeNodeType.SCHOLARSHIP_FAMILY.value:
        score += 6
        reasons.add("scholarship_family_scope")
        scope_signal = True
    if target.state is ScopedCoverageState.PARTIAL:
        score += 6
        reasons.add("partial_coverage")
    if target.state is ScopedCoverageState.CONFLICTING:
        score += 16
        reasons.add("conflict_resolution")
    missing_terms = _reason_tokens(target.missing_frontier_reasons)
    if missing_terms and any(token in text for token in missing_terms):
        score += 12
        reasons.add("missing_frontier_match")
    if block.source_role in {"primary", "supporting"}:
        score += 3
        reasons.add("explicit_source_role")
    if block.language_hints:
        reasons.add("language_metadata_available")
    return score, reasons, scope_signal


def _route_is_selected(
    *,
    score: int,
    reasons: set[str],
    target: _RouteTarget,
    scope_signal: bool,
    selection_threshold: int,
) -> bool:
    topic_signal = bool(
        reasons
        & {
            "objective_lexicon_match",
            "objective_heading_match",
            "missing_frontier_match",
        }
    )
    if target.state is ScopedCoverageState.CONFLICTING:
        topic_signal = True
    return bool(
        score >= selection_threshold
        and topic_signal
        and (
            target.scope_type == ScopeNodeType.SCHOLARSHIP_FAMILY.value
            or scope_signal
            or target.state is ScopedCoverageState.CONFLICTING
        )
    )


def _scope_tokens(target: _RouteTarget) -> set[str]:
    values = [target.scope_key, target.display_label, target.lifecycle_key]
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue
        normalized = value.casefold().strip()
        if len(normalized) >= 2:
            tokens.add(normalized)
        tokens.update(
            item for item in re.split(r"[^\w]+", normalized, flags=re.UNICODE) if len(item) >= 3
        )
    return tokens


def _reason_tokens(reasons: Iterable[str]) -> set[str]:
    return {
        token
        for reason in reasons
        for token in re.split(r"[^\w]+", reason.casefold(), flags=re.UNICODE)
        if len(token) >= 4
    }


def _coverage_route_fingerprint(target: _RouteTarget) -> str:
    payload = "|".join(
        (
            target.input_fingerprint,
            target.objective.value,
            target.state.value,
            str(target.expected_item_count or ""),
            str(target.resolved_item_count),
            target.scope_type,
            target.scope_key,
            target.lifecycle_key,
            EVIDENCE_ROUTER_VERSION,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _route_key(block_key: str, target_identity: str, fingerprint: str) -> str:
    payload = f"{block_key}|{target_identity}|{fingerprint}|{EVIDENCE_ROUTER_VERSION}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "CatalogueEvidenceRouter",
    "EvidenceRouteDecision",
]
