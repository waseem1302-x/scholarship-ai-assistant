"""Read-only, deterministic launch audit for the reviewed scholarship catalogue."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl, unquote, urlsplit

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ScopedCoverageState
from app.modules.catalogue_ingestion.models import CatalogueCandidate
from app.modules.catalogue_ingestion.review_models import (
    CatalogueCandidateReview,
    CatalogueProposalState,
)
from app.modules.catalogue_ingestion.review_workflow import proposal_payload_hash
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


class LaunchManifestEntry(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=255)
    official_root_url: str = Field(pattern=r"^https://", max_length=2048)


class LaunchManifestMatch(LaunchManifestEntry):
    opportunity_id: uuid.UUID
    source_url: str


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
    manifest_required_count: int = 0
    manifest_matched_count: int = 0
    manifest_matches: list[LaunchManifestMatch] = Field(default_factory=list)
    missing_manifest_entries: list[str] = Field(default_factory=list)
    ambiguous_manifest_entries: list[str] = Field(default_factory=list)


def audit_launch_catalogue(
    session: Session,
    *,
    minimum_records: int,
    manifest_entries: list[LaunchManifestEntry] | None = None,
) -> LaunchCatalogueAudit:
    """Audit persisted launch evidence without evaluating or changing catalogue state."""

    if minimum_records < 1:
        raise ValueError("minimum_records must be at least 1")

    audit_now = datetime.now(UTC)
    with session.no_autoflush:
        blocker_ids: dict[str, set[uuid.UUID]] = defaultdict(set)
        active_opportunities = list(
            session.scalars(
                select(Opportunity)
                .where(Opportunity.status == OpportunityStatus.ACTIVE)
                .order_by(Opportunity.id)
            )
        )
        review_rows_by_opportunity = _review_rows_by_opportunity(
            session,
            opportunity_ids={opportunity.id for opportunity in active_opportunities},
        )
        reviewed_records: list[
            tuple[Opportunity, CatalogueCandidate, CatalogueCandidateReview]
        ] = []
        for opportunity in active_opportunities:
            review_rows = review_rows_by_opportunity.get(opportunity.id, [])
            materialized_rows = [
                row for row in review_rows if _has_materialization_receipt(*row)
            ]
            current_rows = [
                row for row in materialized_rows if _review_matches_current_proposal(*row)
            ]
            if len(current_rows) == 1:
                candidate, review = current_rows[0]
                reviewed_records.append((opportunity, candidate, review))
            elif len(current_rows) > 1:
                blocker_ids["ambiguous_reviewed_materialization"].add(opportunity.id)
            elif materialized_rows:
                blocker_ids["stale_current_proposal"].add(opportunity.id)
            else:
                blocker_ids["unreviewed_active_opportunity"].add(opportunity.id)

        complete_core_ids: list[uuid.UUID] = []
        publishable_with_gaps: list[PublishableWithGapsRecord] = []
        publishable_ids: list[uuid.UUID] = []
        publishable_records: list[tuple[Opportunity, list[Source]]] = []

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
                audit_now=audit_now,
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
            if record_blockers or not critical_is_terminal or has_impermissible_gap:
                continue
            publishable_ids.append(opportunity.id)
            publishable_records.append((opportunity, sources))
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
    manifest_matches, missing_manifest_entries, ambiguous_manifest_entries = _match_manifest(
        manifest_entries or [], publishable_records, audit_now=audit_now
    )
    if missing_manifest_entries:
        blockers_by_code["missing_manifest_scholarship"] = len(missing_manifest_entries)
    if ambiguous_manifest_entries:
        blockers_by_code["ambiguous_manifest_scholarship"] = len(ambiguous_manifest_entries)
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
        manifest_required_count=len(manifest_entries or []),
        manifest_matched_count=len(manifest_matches),
        manifest_matches=manifest_matches,
        missing_manifest_entries=missing_manifest_entries,
        ambiguous_manifest_entries=ambiguous_manifest_entries,
    )


def _match_manifest(
    entries: list[LaunchManifestEntry],
    publishable_records: list[tuple[Opportunity, list[Source]]],
    *,
    audit_now: datetime,
) -> tuple[list[LaunchManifestMatch], list[str], list[str]]:
    matches: list[LaunchManifestMatch] = []
    missing: list[str] = []
    ambiguous: list[str] = []
    for entry in entries:
        candidates: list[LaunchManifestMatch] = []
        for opportunity, sources in publishable_records:
            if not _manifest_name_matches(entry.canonical_name, opportunity.name):
                continue
            matching_sources = sorted(
                {
                    source_url
                    for source in sources
                    if source.source_type is SourceType.OFFICIAL
                    and source.is_active
                    and EvidencePolicy.source_can_publish(source)
                    and EvidencePolicy.source_is_fresh(
                        source,
                        freshness_days=SOURCE_FRESHNESS_DAYS,
                        now=audit_now,
                    )
                    for source_url in (source.canonical_url or source.normalized_url or source.url,)
                    if _url_belongs_to_root(source_url, entry.official_root_url)
                }
            )
            if matching_sources:
                candidates.append(
                    LaunchManifestMatch(
                        canonical_name=entry.canonical_name,
                        official_root_url=entry.official_root_url,
                        opportunity_id=opportunity.id,
                        source_url=matching_sources[0],
                    )
                )
        if len(candidates) == 1:
            matches.append(candidates[0])
        elif candidates:
            ambiguous.append(entry.canonical_name)
        else:
            missing.append(entry.canonical_name)
    return matches, missing, ambiguous


def _manifest_name_matches(canonical_name: str, opportunity_name: str) -> bool:
    required_tokens = set(_normalized_words(canonical_name))
    return bool(required_tokens) and required_tokens.issubset(_normalized_words(opportunity_name))


def _normalized_words(value: str) -> set[str]:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]+", ascii_value.casefold()))


def _url_belongs_to_root(source_url: str, root_url: str) -> bool:
    source = urlsplit(source_url)
    root = urlsplit(root_url)
    source_host = (source.hostname or "").casefold().removeprefix("www.")
    root_host = (root.hostname or "").casefold().removeprefix("www.")
    if source.scheme != "https" or root.scheme != "https" or source_host != root_host:
        return False
    source_path = unquote(source.path).rstrip("/") or "/"
    root_path = unquote(root.path).rstrip("/") or "/"
    if root_path != "/" and not (
        source_path == root_path or source_path.startswith(f"{root_path}/")
    ):
        return False
    return not root.query or sorted(parse_qsl(source.query)) == sorted(parse_qsl(root.query))


def _review_rows_by_opportunity(
    session: Session,
    *,
    opportunity_ids: set[uuid.UUID],
) -> dict[uuid.UUID, list[tuple[CatalogueCandidate, CatalogueCandidateReview]]]:
    if not opportunity_ids:
        return {}
    rows = session.execute(
        select(CatalogueCandidate, CatalogueCandidateReview)
        .join(
            CatalogueCandidateReview,
            CatalogueCandidateReview.candidate_id == CatalogueCandidate.id,
        )
        .where(
            CatalogueCandidate.opportunity_id.in_(opportunity_ids),
        )
    ).all()
    grouped: dict[uuid.UUID, list[tuple[CatalogueCandidate, CatalogueCandidateReview]]] = (
        defaultdict(list)
    )
    for candidate, review in rows:
        if candidate.opportunity_id is not None:
            grouped[candidate.opportunity_id].append((candidate, review))
    for review_rows in grouped.values():
        review_rows.sort(key=lambda row: str(row[0].id))
    return dict(grouped)


def _has_materialization_receipt(
    candidate: CatalogueCandidate,
    review: CatalogueCandidateReview,
) -> bool:
    return (
        review.state in _MATERIALIZED_REVIEW_STATES
        and review.reviewed_by_user_id is not None
        and review.reviewed_at is not None
        and review.materialized_at is not None
        and review.materialization_revision is not None
        and candidate.opportunity_id is not None
    )


def _review_matches_current_proposal(
    candidate: CatalogueCandidate,
    review: CatalogueCandidateReview,
) -> bool:
    current_hash = proposal_payload_hash(candidate.proposed_payload)
    return (
        current_hash is not None
        and review.proposal_hash == current_hash
        and review.approved_proposal_hash == current_hash
    )


def _record_blockers(
    opportunity: Opportunity,
    candidate: CatalogueCandidate,
    review: CatalogueCandidateReview,
    *,
    cells: list[CatalogueCoverageCell],
    sources: list[Source],
    cycles: list[OpportunityCycle],
    session: Session,
    audit_now: datetime,
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
        now=audit_now,
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
                now=audit_now,
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
        current_cycle=current_cycle,
        audit_now=audit_now,
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

    projection = build_public_projection(session, opportunity, now=audit_now)
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
    current_cycle: OpportunityCycle | None,
    audit_now: datetime,
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
            now=audit_now,
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
        if node is None or not _scope_matches_current_cycle(node, current_cycle):
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
                    current_cycle=current_cycle,
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
    current_cycle: OpportunityCycle | None,
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
        or source.content_hash is None
        or snapshot.content_hash != source.content_hash
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
    return (
        _entity_belongs_to_opportunity(
            session,
            entity_type=link.entity_type,
            entity_id=link.entity_id,
            opportunity_id=opportunity.id,
        )
        and _entity_matches_current_cycle(
            session,
            entity_type=link.entity_type,
            entity_id=link.entity_id,
            current_cycle=current_cycle,
        )
        and _claim_matches_scope(link, node)
        and _provenance_matches_current_cycle(link, current_cycle)
    )


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


def _entity_matches_current_cycle(
    session: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    current_cycle: OpportunityCycle | None,
) -> bool:
    if entity_type in {"scholarship", "opportunity", "institution"}:
        return True
    if entity_type in {"cycle", "opportunity_cycle"}:
        return current_cycle is not None and entity_id == current_cycle.id
    model = _SCHOLARSHIP_OWNED_EVIDENCE_MODELS.get(entity_type)
    if model is None:
        return False
    entity = session.get(model, entity_id)
    if entity is None:
        return False
    cycle_id = getattr(entity, "cycle_id", None)
    return cycle_id is None or (current_cycle is not None and cycle_id == current_cycle.id)


def _scope_matches_current_cycle(
    node: CatalogueScopeNode,
    current_cycle: OpportunityCycle | None,
) -> bool:
    return not node.lifecycle_key or _is_current_cycle_key(node.lifecycle_key, current_cycle)


def _provenance_matches_current_cycle(
    link: CatalogueMaterializedClaimLink,
    current_cycle: OpportunityCycle | None,
) -> bool:
    scope = (link.provenance_json or {}).get("scope")
    if not isinstance(scope, dict) or not scope.get("cycle_key"):
        return True
    return _is_current_cycle_key(str(scope["cycle_key"]), current_cycle)


def _is_current_cycle_key(value: str, current_cycle: OpportunityCycle | None) -> bool:
    if current_cycle is None:
        return False
    normalized = _canonical_key(value)
    exact_keys = {
        _canonical_key(str(item))
        for item in (current_cycle.id, current_cycle.label, current_cycle.intake_year)
        if item is not None and str(item).strip()
    }
    if normalized in exact_keys:
        return True
    return current_cycle.intake_year is not None and re.search(
        rf"(?<!\d){current_cycle.intake_year}(?!\d)",
        value,
    ) is not None


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
        elif block.state is DecisionSummaryState.UNKNOWN:
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


__all__ = [
    "LaunchCatalogueAudit",
    "LaunchManifestEntry",
    "LaunchManifestMatch",
    "OpenCoverageCell",
    "PublishableWithGapsRecord",
    "audit_launch_catalogue",
]
