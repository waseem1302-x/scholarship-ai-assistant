"""Read-only, deterministic launch audit for the reviewed scholarship catalogue."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
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
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueCoverageCell,
    CatalogueScopeNode,
    ScopeNodeType,
)
from app.modules.catalogue_ingestion.trust_domains import OFFICIAL_FACTUAL_DOMAINS
from app.modules.opportunities.evidence_models import (
    ApplicationStep,
    EvidenceSupportType,
    EvidenceValidatorStatus,
    FieldEvidence,
    FundingComponent,
    RequiredDocument,
    ScopedDeadline,
    SourceSnapshot,
)
from app.modules.opportunities.evidence_policy import EvidencePolicy
from app.modules.opportunities.graph_models import (
    ApplicationTrack,
    Institution,
    InstitutionParticipation,
)
from app.modules.opportunities.lifecycle import SOURCE_FRESHNESS_DAYS
from app.modules.opportunities.materialization_models import (
    CatalogueMaterializedClaimLink,
    OpportunityEvent,
    OpportunityResource,
    ScholarshipEligibilityRule,
    ScholarshipProgramme,
)
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
_SUMMARY_OBJECTIVES = {
    "overview": {
        ClaimObjective.IDENTITY,
        ClaimObjective.PROGRAMMES,
        ClaimObjective.PROGRAMME_DETAILS,
    },
    "funding": {ClaimObjective.FUNDING},
    "eligibility": {
        ClaimObjective.ELIGIBILITY,
        ClaimObjective.ELIGIBILITY_CONTEXT,
    },
    "application_route": {ClaimObjective.ROUTES},
}
_SCOPE_FIELD_TYPES = {
    "scholarship_family_key": ScopeNodeType.SCHOLARSHIP_FAMILY,
    "cycle_key": ScopeNodeType.CYCLE,
    "country_key": ScopeNodeType.COUNTRY,
    "institution_key": ScopeNodeType.INSTITUTION,
    "track_key": ScopeNodeType.ROUTE,
    "programme_key": ScopeNodeType.PROGRAMME,
    "degree_level_key": ScopeNodeType.DEGREE_LEVEL,
    "subject_key": ScopeNodeType.SUBJECT,
    "award_variant_key": ScopeNodeType.AWARD_VARIANT,
    "application_channel_key": ScopeNodeType.APPLICATION_CHANNEL,
}
_ENTITY_NODE_TYPES = {
    "cycle": ScopeNodeType.CYCLE,
    "programme": ScopeNodeType.PROGRAMME,
    "track": ScopeNodeType.ROUTE,
    "institution": ScopeNodeType.INSTITUTION,
}
_SCHOLARSHIP_OWNED_EVIDENCE_MODELS = {
    "track": ApplicationTrack,
    "application_track": ApplicationTrack,
    "programme": ScholarshipProgramme,
    "scholarship_programme": ScholarshipProgramme,
    "eligibility": ScholarshipEligibilityRule,
    "scholarship_eligibility_rule": ScholarshipEligibilityRule,
    "deadline": ScopedDeadline,
    "scoped_deadline": ScopedDeadline,
    "funding": FundingComponent,
    "funding_component": FundingComponent,
    "document": RequiredDocument,
    "required_document": RequiredDocument,
    "step": ApplicationStep,
    "application_step": ApplicationStep,
    "event": OpportunityEvent,
    "opportunity_event": OpportunityEvent,
    "resource": OpportunityResource,
    "opportunity_resource": OpportunityResource,
    "institution_participation": InstitutionParticipation,
}


@dataclass(frozen=True)
class _VerifiedCoverageEvidence:
    fields_by_cell: dict[uuid.UUID, set[str]]
    evidence_ids_by_cell: dict[uuid.UUID, set[uuid.UUID]]
    evidence_ids_by_objective: dict[ClaimObjective, set[uuid.UUID]]


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

        for opportunity, candidate, review in reviewed_records:
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
                review,
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
            has_impermissible_gap = any(
                cell.state not in _TERMINAL_COVERAGE_STATES
                and cell.state is not ScopedCoverageState.UNKNOWN
                for cell in cells
            )
            if not critical_is_terminal or has_impermissible_gap:
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
) -> list[tuple[Opportunity, CatalogueCandidate, CatalogueCandidateReview]]:
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
    return sorted(selected.values(), key=lambda item: str(item[0].id))


def _record_blockers(
    opportunity: Opportunity,
    candidate: CatalogueCandidate,
    review: CatalogueCandidateReview,
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

    verified_coverage = _verified_coverage_fields(
        session,
        opportunity=opportunity,
        candidate=candidate,
        review=review,
        cells=cells,
        sources=official_sources,
    )
    identity_cells = [cell for cell in cells if cell.objective is ClaimObjective.IDENTITY]
    identity_is_terminal = _objective_is_terminal(cells, ClaimObjective.IDENTITY)
    identity_fields = {
        field_path
        for cell in identity_cells
        for field_path in verified_coverage.fields_by_cell.get(cell.id, set())
    }
    identity_evidence_is_complete = bool(identity_cells) and all(
        cell.id in verified_coverage.fields_by_cell for cell in identity_cells
    )
    provider_is_identified = bool(opportunity.provider and opportunity.provider.name.strip())
    tier_zero_complete = (
        identity_is_terminal
        and identity_evidence_is_complete
        and {"name", "provider_name"}.issubset(identity_fields)
        and provider_is_identified
        and opportunity.independence_status is IndependenceStatus.CONFIRMED_INDEPENDENT
        and current_source is not None
    )
    if not tier_zero_complete:
        blockers.add("missing_tier0_evidence")

    critical_cells = [cell for cell in cells if cell.objective in _CRITICAL_OBJECTIVES]
    if not tier_zero_complete or any(
        cell.state in _TERMINAL_COVERAGE_STATES
        and cell.id not in verified_coverage.fields_by_cell
        for cell in critical_cells
    ):
        blockers.add("missing_evidence")

    has_impermissible_gap = any(
        cell.state not in _TERMINAL_COVERAGE_STATES
        and cell.state is not ScopedCoverageState.UNKNOWN
        for cell in cells
    )
    if (
        not all(_objective_is_terminal(cells, objective) for objective in _CRITICAL_OBJECTIVES)
        or has_impermissible_gap
    ):
        blockers.add("incomplete_record")

    projection = build_public_projection(session, opportunity)
    if not _summary_is_supported(
        projection,
        verified_coverage.evidence_ids_by_objective,
    ):
        blockers.add("unsupported_public_summary_claim")
    return blockers


def _verified_coverage_fields(
    session: Session,
    *,
    opportunity: Opportunity,
    candidate: CatalogueCandidate,
    review: CatalogueCandidateReview,
    cells: list[CatalogueCoverageCell],
    sources: list[Source],
) -> _VerifiedCoverageEvidence:
    claim_ids = {
        claim_id
        for cell in cells
        if cell.state in _TERMINAL_COVERAGE_STATES
        for claim_id in cell.supporting_claim_ids
    }
    if not claim_ids or not review.proposal_hash:
        return _VerifiedCoverageEvidence({}, {}, {})
    rows = session.execute(
        select(CatalogueMaterializedClaimLink, FieldEvidence, SourceSnapshot, Source)
        .join(FieldEvidence, FieldEvidence.id == CatalogueMaterializedClaimLink.field_evidence_id)
        .join(SourceSnapshot, SourceSnapshot.id == FieldEvidence.source_snapshot_id)
        .join(Source, Source.id == SourceSnapshot.source_id)
        .where(
            CatalogueMaterializedClaimLink.candidate_id == candidate.id,
            CatalogueMaterializedClaimLink.review_id == review.id,
            CatalogueMaterializedClaimLink.proposal_hash == review.proposal_hash,
            CatalogueMaterializedClaimLink.claim_id.in_(claim_ids),
        )
    ).all()
    fresh_source_ids = {
        source.id
        for source in sources
        if EvidencePolicy.source_can_publish(source)
        and EvidencePolicy.source_is_fresh(
            source,
            freshness_days=SOURCE_FRESHNESS_DAYS,
        )
    }
    if EvidencePolicy.has_disqualifying_official_source(sources):
        fresh_source_ids.clear()
    rows_by_claim: dict[
        str,
        list[tuple[CatalogueMaterializedClaimLink, FieldEvidence, SourceSnapshot, Source]],
    ] = defaultdict(list)
    for link, evidence, snapshot, source in rows:
        rows_by_claim[link.claim_id].append((link, evidence, snapshot, source))

    nodes = {
        node.id: node
        for node in session.scalars(
            select(CatalogueScopeNode).where(CatalogueScopeNode.candidate_id == candidate.id)
        )
    }
    fields_by_cell: dict[uuid.UUID, set[str]] = {}
    evidence_ids_by_cell: dict[uuid.UUID, set[uuid.UUID]] = {}
    evidence_ids_by_objective: dict[ClaimObjective, set[uuid.UUID]] = defaultdict(set)
    for cell in cells:
        if cell.state not in _TERMINAL_COVERAGE_STATES or not cell.supporting_claim_ids:
            continue
        node = nodes.get(cell.scope_node_id)
        if node is None:
            continue
        fields: set[str] = set()
        field_evidence_ids: set[uuid.UUID] = set()
        derived_evidence_ids: set[str] = set()
        all_claims_valid = True
        for claim_id in set(cell.supporting_claim_ids):
            candidates = [
                row
                for row in rows_by_claim.get(claim_id, [])
                if _coverage_evidence_row_is_valid(
                    session,
                    opportunity=opportunity,
                    node=node,
                    fresh_source_ids=fresh_source_ids,
                    row=row,
                )
            ]
            if len(candidates) != 1:
                all_claims_valid = False
                break
            link, evidence, _snapshot, _source = candidates[0]
            derived_id = _coverage_evidence_id(link, evidence)
            if derived_id is None:
                all_claims_valid = False
                break
            fields.add(link.field_path)
            field_evidence_ids.add(evidence.id)
            derived_evidence_ids.add(derived_id)
        if all_claims_valid and derived_evidence_ids == set(cell.supporting_evidence_ids):
            fields_by_cell[cell.id] = fields
            evidence_ids_by_cell[cell.id] = field_evidence_ids
            evidence_ids_by_objective[cell.objective].update(field_evidence_ids)
    return _VerifiedCoverageEvidence(
        fields_by_cell=fields_by_cell,
        evidence_ids_by_cell=evidence_ids_by_cell,
        evidence_ids_by_objective=dict(evidence_ids_by_objective),
    )


def _coverage_evidence_row_is_valid(
    session: Session,
    *,
    opportunity: Opportunity,
    node: CatalogueScopeNode,
    fresh_source_ids: set[uuid.UUID],
    row: tuple[CatalogueMaterializedClaimLink, FieldEvidence, SourceSnapshot, Source],
) -> bool:
    link, evidence, snapshot, source = row
    if (
        evidence.entity_type != link.entity_type
        or evidence.entity_id != link.entity_id
        or evidence.field_path != link.field_path
        or evidence.support_type is not EvidenceSupportType.EXPLICIT
        or evidence.validator_status is not EvidenceValidatorStatus.PASSED
        or source.id not in fresh_source_ids
        or source.opportunity_id != opportunity.id
    ):
        return False
    provenance = link.provenance_json or {}
    if (
        provenance.get("source_snapshot_id") != str(snapshot.id)
        or provenance.get("content_hash") != snapshot.content_hash
        or provenance.get("source_url") != source.url
    ):
        return False
    trust_domain = link.trust_domain or evidence.trust_domain
    trusted_domain = trust_domain in {domain.value for domain in OFFICIAL_FACTUAL_DOMAINS}
    if not trusted_domain and provenance.get("trust_tier") not in {1, 2, 3}:
        return False
    return _entity_belongs_to_opportunity(
        session,
        entity_type=link.entity_type,
        entity_id=link.entity_id,
        opportunity_id=opportunity.id,
    ) and _claim_matches_scope(link, node)


def _entity_belongs_to_opportunity(
    session: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    opportunity_id: uuid.UUID,
) -> bool:
    if entity_type in {"scholarship", "opportunity"}:
        return entity_id == opportunity_id
    if entity_type in {"cycle", "opportunity_cycle"}:
        cycle = session.get(OpportunityCycle, entity_id)
        return cycle is not None and cycle.opportunity_id == opportunity_id
    if entity_type == "institution":
        institution = session.get(Institution, entity_id)
        if institution is None:
            return False
        participation = session.scalar(
            select(InstitutionParticipation.id).where(
                InstitutionParticipation.scholarship_id == opportunity_id,
                InstitutionParticipation.institution_id == entity_id,
            )
        )
        return participation is not None
    model = _SCHOLARSHIP_OWNED_EVIDENCE_MODELS.get(entity_type)
    if model is None:
        return False
    entity = session.get(model, entity_id)
    return entity is not None and entity.scholarship_id == opportunity_id


def _claim_matches_scope(link: CatalogueMaterializedClaimLink, node: CatalogueScopeNode) -> bool:
    if node.node_type is ScopeNodeType.SCHOLARSHIP_FAMILY:
        return True
    provenance = link.provenance_json or {}
    claim_entity_type = str(provenance.get("claim_entity_type") or link.entity_type)
    claim_entity_key = provenance.get("claim_entity_key")
    mapped_type = _ENTITY_NODE_TYPES.get(claim_entity_type)
    if (
        mapped_type is node.node_type
        and isinstance(claim_entity_key, str)
        and _canonical_key(claim_entity_key) == node.canonical_key
    ):
        return True
    scope = provenance.get("scope")
    if not isinstance(scope, dict):
        return False
    return any(
        node_type is node.node_type
        and isinstance(scope.get(field_name), str)
        and _canonical_key(scope[field_name]) == node.canonical_key
        for field_name, node_type in _SCOPE_FIELD_TYPES.items()
    )


def _coverage_evidence_id(
    link: CatalogueMaterializedClaimLink,
    evidence: FieldEvidence,
) -> str | None:
    provenance = link.provenance_json or {}
    artifact_id = provenance.get("artifact_id")
    content_hash = provenance.get("content_hash")
    if not isinstance(artifact_id, str) or not isinstance(content_hash, str):
        return None
    return hashlib.sha256(
        f"{artifact_id}:{content_hash}:{evidence.excerpt_start}:{evidence.excerpt_end}".encode()
    ).hexdigest()


def _canonical_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return normalized[:255] or hashlib.sha256(value.encode()).hexdigest()[:32]


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


def _summary_is_supported(
    projection: object,
    evidence_ids_by_objective: dict[ClaimObjective, set[uuid.UUID]],
) -> bool:
    summary = getattr(projection, "summary", None)
    if summary is None:
        return False
    projection_evidence_ids = {item.id for item in projection.evidence}
    for block_name, objectives in _SUMMARY_OBJECTIVES.items():
        block = getattr(summary, block_name)
        evidence_ids = set(block.evidence_ids)
        if block.state in _SUMMARY_STATES_REQUIRING_EVIDENCE:
            reviewed_evidence_ids = {
                evidence_id
                for objective in objectives
                for evidence_id in evidence_ids_by_objective.get(objective, set())
            }
            if (
                not evidence_ids
                or not evidence_ids.issubset(projection_evidence_ids)
                or not evidence_ids.issubset(reviewed_evidence_ids)
            ):
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
