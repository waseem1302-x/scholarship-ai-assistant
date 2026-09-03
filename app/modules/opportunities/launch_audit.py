"""Read-only, deterministic launch audit for the reviewed scholarship catalogue."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ScopedCoverageState
from app.modules.catalogue_ingestion.models import CatalogueCandidate
from app.modules.catalogue_ingestion.review_models import (
    CatalogueCandidateReview,
    CatalogueProposalState,
)
from app.modules.catalogue_ingestion.topology_models import CatalogueCoverageCell
from app.modules.opportunities.evidence_policy import EvidencePolicy
from app.modules.opportunities.lifecycle import SOURCE_FRESHNESS_DAYS
from app.modules.opportunities.models import (
    IndependenceStatus,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    Source,
    SourceType,
    VerificationStatus,
)
from app.modules.opportunities.public_projection import build_public_projection
from app.modules.opportunities.schemas import DecisionSummaryState

_TERMINAL_COVERAGE_STATES = {
    ScopedCoverageState.COMPLETE,
    ScopedCoverageState.NOT_APPLICABLE,
}
_CRITICAL_OBJECTIVES = {
    ClaimObjective.IDENTITY,
    ClaimObjective.ROUTES,
    ClaimObjective.ELIGIBILITY,
    ClaimObjective.FUNDING,
    ClaimObjective.APPLICATION_TIMELINE,
}
_MATERIALIZED_REVIEW_STATES = {
    CatalogueProposalState.MATERIALIZED,
    CatalogueProposalState.PUBLICATION_READY,
    CatalogueProposalState.PUBLISHED,
}
_SUMMARY_STATES_REQUIRING_EVIDENCE = {
    DecisionSummaryState.CONFIRMED,
    DecisionSummaryState.NOT_APPLICABLE,
}


class OpenCoverageCell(BaseModel):
    objective: ClaimObjective
    scope_node_id: uuid.UUID
    state: ScopedCoverageState
    reason: str
    missing_frontier_reasons: list[str] = Field(default_factory=list)


class PublishableWithGapsRecord(BaseModel):
    opportunity_id: uuid.UUID
    open_coverage_cells: list[OpenCoverageCell]


class LaunchCatalogueAudit(BaseModel):
    ready: bool
    minimum_records: int
    active_reviewed_count: int
    complete_core_count: int
    publishable_with_gaps_count: int
    publishable_count: int
    stale_source_count: int
    unresolved_conflict_count: int
    blockers_by_code: dict[str, int]
    opportunity_ids_by_blocker: dict[str, list[uuid.UUID]]
    curator_action_opportunity_ids: list[uuid.UUID]
    complete_core_opportunity_ids: list[uuid.UUID]
    publishable_with_gaps: list[PublishableWithGapsRecord]


def audit_launch_catalogue(
    session: Session,
    *,
    minimum_records: int,
) -> LaunchCatalogueAudit:
    """Audit persisted launch evidence without evaluating or changing catalogue state."""

    if minimum_records < 1:
        raise ValueError("minimum_records must be at least 1")

    with session.no_autoflush:
        reviewed_records = _active_reviewed_records(session)
        blocker_ids: dict[str, set[uuid.UUID]] = defaultdict(set)
        complete_core_ids: list[uuid.UUID] = []
        publishable_with_gaps: list[PublishableWithGapsRecord] = []
        publishable_ids: list[uuid.UUID] = []

        for opportunity, candidate in reviewed_records:
            cells = list(
                session.scalars(
                    select(CatalogueCoverageCell)
                    .where(
                        CatalogueCoverageCell.candidate_id == candidate.id,
                        CatalogueCoverageCell.required.is_(True),
                    )
                    .order_by(
                        CatalogueCoverageCell.objective,
                        CatalogueCoverageCell.scope_node_id,
                    )
                )
            )
            sources = list(
                session.scalars(
                    select(Source)
                    .where(Source.opportunity_id == opportunity.id)
                    .order_by(Source.id)
                )
            )
            cycles = list(
                session.scalars(
                    select(OpportunityCycle)
                    .where(OpportunityCycle.opportunity_id == opportunity.id)
                    .order_by(OpportunityCycle.id)
                )
            )
            record_blockers = _record_blockers(
                opportunity,
                candidate,
                cells=cells,
                sources=sources,
                cycles=cycles,
                session=session,
            )
            for code in record_blockers:
                blocker_ids[code].add(opportunity.id)

            open_cells = [cell for cell in cells if cell.state not in _TERMINAL_COVERAGE_STATES]
            critical_is_terminal = all(
                _objective_is_terminal(cells, objective) for objective in _CRITICAL_OBJECTIVES
            )
            if not critical_is_terminal:
                continue
            publishable_ids.append(opportunity.id)
            if open_cells:
                publishable_with_gaps.append(
                    PublishableWithGapsRecord(
                        opportunity_id=opportunity.id,
                        open_coverage_cells=[_open_cell(cell) for cell in open_cells],
                    )
                )
            else:
                complete_core_ids.append(opportunity.id)

    publishable_ids.sort(key=str)
    complete_core_ids.sort(key=str)
    publishable_with_gaps.sort(key=lambda item: str(item.opportunity_id))
    shortfall = max(0, minimum_records - len(publishable_ids))
    blockers_by_code = {
        code: len(opportunity_ids)
        for code, opportunity_ids in sorted(blocker_ids.items())
        if opportunity_ids
    }
    if shortfall:
        blockers_by_code["minimum_records"] = shortfall
    sorted_blocker_ids = {
        code: sorted(opportunity_ids, key=str)
        for code, opportunity_ids in sorted(blocker_ids.items())
        if opportunity_ids
    }
    curator_ids = sorted(
        {opportunity_id for ids in blocker_ids.values() for opportunity_id in ids},
        key=str,
    )
    return LaunchCatalogueAudit(
        ready=not blockers_by_code,
        minimum_records=minimum_records,
        active_reviewed_count=len(reviewed_records),
        complete_core_count=len(complete_core_ids),
        publishable_with_gaps_count=len(publishable_with_gaps),
        publishable_count=len(publishable_ids),
        stale_source_count=len(blocker_ids["stale_official_source"]),
        unresolved_conflict_count=len(blocker_ids["unresolved_conflict"]),
        blockers_by_code=blockers_by_code,
        opportunity_ids_by_blocker=sorted_blocker_ids,
        curator_action_opportunity_ids=curator_ids,
        complete_core_opportunity_ids=complete_core_ids,
        publishable_with_gaps=publishable_with_gaps,
    )


def _active_reviewed_records(
    session: Session,
) -> list[tuple[Opportunity, CatalogueCandidate]]:
    rows = session.execute(
        select(Opportunity, CatalogueCandidate, CatalogueCandidateReview)
        .join(CatalogueCandidate, CatalogueCandidate.opportunity_id == Opportunity.id)
        .join(
            CatalogueCandidateReview,
            CatalogueCandidateReview.candidate_id == CatalogueCandidate.id,
        )
        .where(
            Opportunity.status == OpportunityStatus.ACTIVE,
            CatalogueCandidateReview.state.in_(_MATERIALIZED_REVIEW_STATES),
            CatalogueCandidateReview.reviewed_by_user_id.is_not(None),
            CatalogueCandidateReview.reviewed_at.is_not(None),
            CatalogueCandidateReview.materialized_at.is_not(None),
        )
    ).all()
    state_rank = {
        CatalogueProposalState.MATERIALIZED: 0,
        CatalogueProposalState.PUBLICATION_READY: 1,
        CatalogueProposalState.PUBLISHED: 2,
    }
    selected: dict[uuid.UUID, tuple[Opportunity, CatalogueCandidate, CatalogueCandidateReview]] = {}
    for opportunity, candidate, review in rows:
        current = selected.get(opportunity.id)
        rank = (state_rank[review.state], _as_utc(review.reviewed_at), str(candidate.id))
        if current is None:
            selected[opportunity.id] = (opportunity, candidate, review)
            continue
        current_review = current[2]
        current_rank = (
            state_rank[current_review.state],
            _as_utc(current_review.reviewed_at),
            str(current[1].id),
        )
        if rank > current_rank:
            selected[opportunity.id] = (opportunity, candidate, review)
    return [
        (opportunity, candidate)
        for opportunity, candidate, _review in sorted(
            selected.values(), key=lambda item: str(item[0].id)
        )
    ]


def _record_blockers(
    opportunity: Opportunity,
    candidate: CatalogueCandidate,
    *,
    cells: list[CatalogueCoverageCell],
    sources: list[Source],
    cycles: list[OpportunityCycle],
    session: Session,
) -> set[str]:
    blockers: set[str] = set()
    dimensions = {
        "missing_identity": ClaimObjective.IDENTITY,
        "missing_route": ClaimObjective.ROUTES,
        "missing_eligibility": ClaimObjective.ELIGIBILITY,
        "missing_funding": ClaimObjective.FUNDING,
        "missing_deadline": ClaimObjective.APPLICATION_TIMELINE,
    }
    for code, objective in dimensions.items():
        if not _objective_is_terminal(cells, objective):
            blockers.add(code)

    current_cycle = next(
        (
            cycle
            for cycle in cycles
            if cycle.id == opportunity.current_cycle_id
            and cycle.is_current
            and not cycle.is_archived
        ),
        None,
    )
    if current_cycle is None:
        blockers.add("missing_current_cycle")
    elif (
        _objective_is_terminal(cells, ClaimObjective.APPLICATION_TIMELINE)
        and not _objective_is_not_applicable(cells, ClaimObjective.APPLICATION_TIMELINE)
        and current_cycle.application_deadline is None
        and not current_cycle.is_rolling
    ):
        blockers.add("missing_deadline")

    official_sources = [source for source in sources if source.source_type is SourceType.OFFICIAL]
    has_source_conflict = any(
        source.verification_status is VerificationStatus.CONFLICTING_INFORMATION
        for source in official_sources
    )
    has_coverage_conflict = any(cell.state is ScopedCoverageState.CONFLICTING for cell in cells)
    if candidate.conflicts or has_source_conflict or has_coverage_conflict:
        blockers.add("unresolved_conflict")

    verified_sources = [
        source for source in official_sources if EvidencePolicy.source_can_publish(source)
    ]
    current_source = EvidencePolicy.select_current_official_source(
        official_sources,
        require_fresh_days=SOURCE_FRESHNESS_DAYS,
    )
    has_expired_source = any(
        source.verification_status in {VerificationStatus.EXPIRED, VerificationStatus.ARCHIVED}
        for source in official_sources
    )
    if has_expired_source or (
        verified_sources
        and not any(
            EvidencePolicy.source_is_fresh(
                source,
                freshness_days=SOURCE_FRESHNESS_DAYS,
            )
            for source in verified_sources
        )
    ):
        blockers.add("stale_official_source")

    identity_is_terminal = _objective_is_terminal(cells, ClaimObjective.IDENTITY)
    provider_is_identified = bool(opportunity.provider and opportunity.provider.name.strip())
    tier_zero_complete = (
        identity_is_terminal
        and provider_is_identified
        and opportunity.independence_status is IndependenceStatus.CONFIRMED_INDEPENDENT
        and current_source is not None
    )
    if not tier_zero_complete:
        blockers.add("missing_tier0_evidence")

    critical_cells = [cell for cell in cells if cell.objective in _CRITICAL_OBJECTIVES]
    if not tier_zero_complete or any(
        cell.state in _TERMINAL_COVERAGE_STATES and not cell.supporting_evidence_ids
        for cell in critical_cells
    ):
        blockers.add("missing_evidence")

    if not all(_objective_is_terminal(cells, objective) for objective in _CRITICAL_OBJECTIVES):
        blockers.add("incomplete_record")

    projection = build_public_projection(session, opportunity)
    if not _summary_is_supported(projection):
        blockers.add("unsupported_public_summary_claim")
    return blockers


def _objective_is_terminal(
    cells: list[CatalogueCoverageCell],
    objective: ClaimObjective,
) -> bool:
    objective_cells = [cell for cell in cells if cell.objective is objective]
    return bool(objective_cells) and all(
        cell.state in _TERMINAL_COVERAGE_STATES for cell in objective_cells
    )


def _objective_is_not_applicable(
    cells: list[CatalogueCoverageCell],
    objective: ClaimObjective,
) -> bool:
    objective_cells = [cell for cell in cells if cell.objective is objective]
    return bool(objective_cells) and all(
        cell.state is ScopedCoverageState.NOT_APPLICABLE for cell in objective_cells
    )


def _summary_is_supported(projection: object) -> bool:
    summary = getattr(projection, "summary", None)
    if summary is None:
        return False
    projection_evidence_ids = {item.id for item in projection.evidence}
    for block in (
        summary.overview,
        summary.funding,
        summary.eligibility,
        summary.application_route,
    ):
        evidence_ids = set(block.evidence_ids)
        if block.state in _SUMMARY_STATES_REQUIRING_EVIDENCE:
            if not evidence_ids or not evidence_ids.issubset(projection_evidence_ids):
                return False
        elif block.state is DecisionSummaryState.UNKNOWN and evidence_ids:
            return False
    return True


def _open_cell(cell: CatalogueCoverageCell) -> OpenCoverageCell:
    return OpenCoverageCell(
        objective=cell.objective,
        scope_node_id=cell.scope_node_id,
        state=cell.state,
        reason=cell.reason,
        missing_frontier_reasons=sorted(cell.missing_frontier_reasons or []),
    )


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "LaunchCatalogueAudit",
    "OpenCoverageCell",
    "PublishableWithGapsRecord",
    "audit_launch_catalogue",
]
