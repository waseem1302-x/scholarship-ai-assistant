"""Deterministic acquisition planning from unresolved scoped coverage.

The planner performs no network I/O and makes no semantic completeness decisions. It converts
persisted coverage cells into a bounded, inspectable frontier hint set that the crawler can use to
rank already-permitted official links. Provider self-reported coverage is deliberately absent from
this boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ScopedCoverageState
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueCoverageCell,
    CatalogueScopeNode,
)

_TERMINAL_COVERAGE_STATES = {
    ScopedCoverageState.COMPLETE,
    ScopedCoverageState.NOT_APPLICABLE,
}
_STATE_PRIORITY = {
    ScopedCoverageState.CONFLICTING: 0,
    ScopedCoverageState.QUARANTINED: 1,
    ScopedCoverageState.FAILED: 2,
    ScopedCoverageState.BLOCKED: 3,
    ScopedCoverageState.PARTIAL: 4,
    ScopedCoverageState.NOT_YET_ACQUIRED: 5,
    ScopedCoverageState.NOT_STATED: 6,
    ScopedCoverageState.UNKNOWN: 7,
}
_DEFAULT_FRONTIER_OBJECTIVES = (
    ClaimObjective.IDENTITY,
    ClaimObjective.PROGRAMMES,
    ClaimObjective.PROGRAMME_DETAILS,
    ClaimObjective.ROUTES,
    ClaimObjective.ELIGIBILITY,
    ClaimObjective.ELIGIBILITY_CONTEXT,
    ClaimObjective.DOCUMENTS_CORE,
    ClaimObjective.DOCUMENTS_REQUIREMENTS,
    ClaimObjective.DOCUMENTS_COUNTS,
    ClaimObjective.DOCUMENTS_FORMAT,
    ClaimObjective.FUNDING,
    ClaimObjective.APPLICATION_TIMELINE,
)


@dataclass(frozen=True, slots=True)
class AcquisitionFrontierNeed:
    objective: str
    scope_type: str
    scope_key: str
    lifecycle_key: str | None
    coverage_state: str
    reasons: tuple[str, ...]
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AcquisitionPlan:
    candidate_id: uuid.UUID
    needs: tuple[AcquisitionFrontierNeed, ...]
    coverage_revision: str | None

    @property
    def unresolved_reasons(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    reason
                    for need in self.needs
                    for reason in need.reasons
                }
            )
        )

    @property
    def objectives(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(need.objective for need in self.needs))


class CatalogueAcquisitionPlanner:
    """Project unresolved coverage into deterministic crawl-frontier hints."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def plan(
        self,
        candidate_id: uuid.UUID,
        *,
        seed_keywords: tuple[str, ...] | list[str] = (),
    ) -> AcquisitionPlan:
        rows = list(
            self.session.execute(
                select(CatalogueCoverageCell, CatalogueScopeNode)
                .join(CatalogueScopeNode, CatalogueScopeNode.id == CatalogueCoverageCell.scope_node_id)
                .where(
                    CatalogueCoverageCell.candidate_id == candidate_id,
                    CatalogueCoverageCell.required.is_(True),
                )
            )
        )
        if not rows:
            return AcquisitionPlan(
                candidate_id=candidate_id,
                needs=tuple(
                    AcquisitionFrontierNeed(
                        objective=objective.value,
                        scope_type="scholarship_family",
                        scope_key="scholarship",
                        lifecycle_key=None,
                        coverage_state=ScopedCoverageState.UNKNOWN.value,
                        reasons=("initial_acquisition_frontier",),
                        keywords=_normalized_keywords(seed_keywords),
                    )
                    for objective in _DEFAULT_FRONTIER_OBJECTIVES
                ),
                coverage_revision=None,
            )

        unresolved = [
            (cell, node)
            for cell, node in rows
            if cell.state not in _TERMINAL_COVERAGE_STATES
        ]
        revisions = {
            cell.evaluator_version
            for cell, _node in rows
            if cell.evaluator_version
        }
        coverage_revision = next(iter(revisions)) if len(revisions) == 1 else None
        if not unresolved:
            return AcquisitionPlan(
                candidate_id=candidate_id,
                needs=(),
                coverage_revision=coverage_revision,
            )

        unresolved.sort(
            key=lambda item: (
                _STATE_PRIORITY.get(item[0].state, 99),
                item[0].objective.value,
                item[1].node_type.value,
                item[1].lifecycle_key,
                item[1].canonical_key,
            )
        )
        needs = tuple(
            AcquisitionFrontierNeed(
                objective=cell.objective.value,
                scope_type=node.node_type.value,
                scope_key=node.canonical_key,
                lifecycle_key=node.lifecycle_key or None,
                coverage_state=cell.state.value,
                reasons=tuple(cell.missing_frontier_reasons or [cell.reason]),
                keywords=_normalized_keywords(
                    [
                        *seed_keywords,
                        node.display_label,
                        node.canonical_key.replace("_", " "),
                    ]
                ),
            )
            for cell, node in unresolved
        )
        return AcquisitionPlan(
            candidate_id=candidate_id,
            needs=needs,
            coverage_revision=coverage_revision,
        )


def _normalized_keywords(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = " ".join(str(value).split()).strip()
        if not item:
            continue
        folded = item.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        normalized.append(item[:160])
    return tuple(normalized[:32])


__all__ = [
    "AcquisitionFrontierNeed",
    "AcquisitionPlan",
    "CatalogueAcquisitionPlanner",
]
