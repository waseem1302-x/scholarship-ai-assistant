"""Deterministic topology construction and scoped completeness evaluation."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimConflictRecord,
    ClaimEntityType,
    ClaimObjective,
    ClaimRejectionRecord,
    ClaimResolution,
    ExtractedClaim,
    ObjectiveCoverageState,
    ResolvedClaim,
    ScopeCoverageDecision,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceRole,
    CandidateSourceStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueSourceArtifact,
)
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueCoverageCell,
    CatalogueScopeEdge,
    CatalogueScopeNode,
    CatalogueSourceScopeLink,
    ScopeDiscoveryConfidence,
    ScopeEdgeType,
    ScopeNodeType,
    ScopedCoverageState,
    SourceScopeRelationship,
)

COVERAGE_EVALUATOR_VERSION = "catalogue-scoped-coverage.v1"

_SCOPE_FIELD_TYPES: dict[str, ScopeNodeType] = {
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
_ENTITY_NODE_TYPES: dict[ClaimEntityType, ScopeNodeType] = {
    ClaimEntityType.CYCLE: ScopeNodeType.CYCLE,
    ClaimEntityType.PROGRAMME: ScopeNodeType.PROGRAMME,
    ClaimEntityType.TRACK: ScopeNodeType.ROUTE,
    ClaimEntityType.INSTITUTION: ScopeNodeType.INSTITUTION,
}
_BRANCH_SCOPE_TYPES = {
    ScopeNodeType.CYCLE,
    ScopeNodeType.INSTITUTION,
    ScopeNodeType.ROUTE,
    ScopeNodeType.PROGRAMME,
    ScopeNodeType.DEGREE_LEVEL,
    ScopeNodeType.SUBJECT,
    ScopeNodeType.AWARD_VARIANT,
    ScopeNodeType.APPLICATION_CHANNEL,
}
_OBJECTIVE_SCOPE_TYPES: dict[ClaimObjective, set[ScopeNodeType]] = {
    ClaimObjective.IDENTITY: {
        ScopeNodeType.CYCLE,
        ScopeNodeType.COUNTRY,
        ScopeNodeType.INSTITUTION,
    },
    ClaimObjective.PROGRAMMES: {ScopeNodeType.CYCLE, ScopeNodeType.PROGRAMME},
    ClaimObjective.PROGRAMME_DETAILS: {
        ScopeNodeType.CYCLE,
        ScopeNodeType.PROGRAMME,
        ScopeNodeType.DEGREE_LEVEL,
        ScopeNodeType.SUBJECT,
    },
    ClaimObjective.ROUTES: {
        ScopeNodeType.CYCLE,
        ScopeNodeType.PROGRAMME,
        ScopeNodeType.ROUTE,
        ScopeNodeType.INSTITUTION,
        ScopeNodeType.APPLICATION_CHANNEL,
    },
    ClaimObjective.ELIGIBILITY: set(_BRANCH_SCOPE_TYPES),
    ClaimObjective.ELIGIBILITY_CONTEXT: set(_BRANCH_SCOPE_TYPES),
    ClaimObjective.DOCUMENTS_CORE: set(_BRANCH_SCOPE_TYPES),
    ClaimObjective.DOCUMENTS_REQUIREMENTS: set(_BRANCH_SCOPE_TYPES),
    ClaimObjective.DOCUMENTS_COUNTS: set(_BRANCH_SCOPE_TYPES),
    ClaimObjective.DOCUMENTS_FORMAT: set(_BRANCH_SCOPE_TYPES),
    ClaimObjective.FUNDING: set(_BRANCH_SCOPE_TYPES),
    ClaimObjective.APPLICATION_TIMELINE: set(_BRANCH_SCOPE_TYPES),
}
_FINITE_SCOPE_REQUIREMENTS: dict[
    tuple[ClaimObjective, ScopeNodeType], set[tuple[ClaimEntityType, str]]
] = {
    (ClaimObjective.IDENTITY, ScopeNodeType.SCHOLARSHIP_FAMILY): {
        (ClaimEntityType.SCHOLARSHIP, "name"),
        (ClaimEntityType.SCHOLARSHIP, "provider_name"),
        (ClaimEntityType.SCHOLARSHIP, "country_code"),
    },
    (ClaimObjective.IDENTITY, ScopeNodeType.CYCLE): {
        (ClaimEntityType.CYCLE, "intake_year")
    },
    (ClaimObjective.IDENTITY, ScopeNodeType.COUNTRY): {
        (ClaimEntityType.SCHOLARSHIP, "country_code")
    },
    (ClaimObjective.IDENTITY, ScopeNodeType.INSTITUTION): {
        (ClaimEntityType.INSTITUTION, "canonical_name")
    },
    (ClaimObjective.PROGRAMMES, ScopeNodeType.PROGRAMME): {
        (ClaimEntityType.PROGRAMME, "name")
    },
    (ClaimObjective.ROUTES, ScopeNodeType.ROUTE): {
        (ClaimEntityType.TRACK, "name")
    },
}
_ENUMERATED_BRANCH_OBJECTIVES: dict[ClaimObjective, ScopeNodeType] = {
    ClaimObjective.PROGRAMMES: ScopeNodeType.PROGRAMME,
    ClaimObjective.ROUTES: ScopeNodeType.ROUTE,
}


@dataclass(frozen=True)
class _ScopeRef:
    node_type: ScopeNodeType
    canonical_key: str
    display_label: str
    lifecycle_key: str
    source_id: uuid.UUID | None
    artifact_id: uuid.UUID | None
    confidence: ScopeDiscoveryConfidence


@dataclass(frozen=True)
class _CoverageResult:
    state: ScopedCoverageState
    reason: str
    missing_frontier_reasons: list[str]
    supporting_claim_ids: list[str]
    supporting_evidence_ids: list[str]
    expected_item_count: int | None
    resolved_item_count: int


def evaluate_scoped_completeness(
    *,
    artifacts: Iterable[CatalogueSourceArtifact],
    resolution: ClaimResolution,
    provider_objective_coverage: dict[str, str] | None = None,
) -> ClaimResolution:
    """Evaluate every objective at explicit topology scopes and persist when attached.

    Provider coverage is retained as an observation only. It may force a conservative state such
    as partial, but it never proves ``complete`` or ``not_applicable``.
    """

    artifact_list = list(artifacts)
    provider_signals = dict(provider_objective_coverage or {})
    session, candidate_id = _attached_candidate_context(artifact_list)
    if session is None or candidate_id is None:
        return _detached_evaluation(resolution, provider_signals)
    return _PersistentCoverageEvaluator(session).evaluate(
        candidate_id=candidate_id,
        resolution=resolution,
        provider_signals=provider_signals,
    )


class _PersistentCoverageEvaluator:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate(
        self,
        *,
        candidate_id: uuid.UUID,
        resolution: ClaimResolution,
        provider_signals: dict[str, str],
    ) -> ClaimResolution:
        candidate = self.session.get(CatalogueCandidate, candidate_id)
        if candidate is None:
            return _detached_evaluation(resolution, provider_signals)
        sources = list(
            self.session.scalars(
                select(CatalogueCandidateSource).where(
                    CatalogueCandidateSource.candidate_id == candidate_id
                )
            )
        )
        source_by_id = {item.id: item for item in sources}
        artifact_ids = {uuid.UUID(item.artifact_id) for item in resolution.resolved}
        artifacts = (
            list(
                self.session.scalars(
                    select(CatalogueSourceArtifact).where(
                        CatalogueSourceArtifact.id.in_(artifact_ids)
                    )
                )
            )
            if artifact_ids
            else []
        )
        artifact_by_id = {item.id: item for item in artifacts}

        root = self._root_node(candidate)
        nodes: dict[tuple[ScopeNodeType, str, str], CatalogueScopeNode] = {
            (root.node_type, root.canonical_key, root.lifecycle_key): root
        }
        self._link_candidate_sources_to_root(candidate, root, sources, artifacts)

        claim_nodes: dict[str, set[uuid.UUID]] = defaultdict(set)
        for item in resolution.resolved:
            claim_id = item.claim_id or _claim_id(item)
            refs = _scope_refs_for_claim(candidate, item, artifact_by_id)
            resolved_nodes: list[CatalogueScopeNode] = []
            for ref in refs:
                node = self._upsert_node(candidate, ref)
                nodes[(node.node_type, node.canonical_key, node.lifecycle_key)] = node
                resolved_nodes.append(node)
                claim_nodes[claim_id].add(node.id)
                if node.id != root.id:
                    self._upsert_edge(
                        candidate_id=candidate.id,
                        parent=root,
                        child=node,
                        relationship_type=ScopeEdgeType.CONTAINS,
                        item=item,
                    )
                self._upsert_source_scope_link(
                    candidate_id=candidate.id,
                    node=node,
                    item=item,
                    relationship_type=SourceScopeRelationship.SUPPORTS,
                    explicit=node.id != root.id,
                )
            entity_node = _entity_node_for_claim(item.claim, resolved_nodes)
            if entity_node is not None:
                for node in resolved_nodes:
                    if node.id == entity_node.id or node.id == root.id:
                        continue
                    self._upsert_edge(
                        candidate_id=candidate.id,
                        parent=entity_node,
                        child=node,
                        relationship_type=ScopeEdgeType.APPLIES_TO,
                        item=item,
                    )
            self._topology_edges_from_value(candidate, item, nodes)

        self.session.flush()
        all_nodes = list(
            self.session.scalars(
                select(CatalogueScopeNode).where(CatalogueScopeNode.candidate_id == candidate.id)
            )
        )
        edges = list(
            self.session.scalars(
                select(CatalogueScopeEdge).where(CatalogueScopeEdge.candidate_id == candidate.id)
            )
        )
        links = list(
            self.session.scalars(
                select(CatalogueSourceScopeLink).where(
                    CatalogueSourceScopeLink.candidate_id == candidate.id
                )
            )
        )
        links_by_node: dict[uuid.UUID, list[CatalogueSourceScopeLink]] = defaultdict(list)
        for link in links:
            links_by_node[link.scope_node_id].append(link)

        decisions: list[ScopeCoverageDecision] = []
        cells_by_objective: dict[ClaimObjective, list[tuple[CatalogueScopeNode, _CoverageResult]]] = (
            defaultdict(list)
        )
        non_root_nodes = [node for node in all_nodes if node.id != root.id]
        for objective in ClaimObjective:
            target_nodes = [root]
            target_nodes.extend(
                node
                for node in non_root_nodes
                if node.node_type in _OBJECTIVE_SCOPE_TYPES[objective]
            )
            seen_node_ids: set[uuid.UUID] = set()
            for node in target_nodes:
                if node.id in seen_node_ids:
                    continue
                seen_node_ids.add(node.id)
                result = self._evaluate_cell(
                    candidate=candidate,
                    root=root,
                    node=node,
                    objective=objective,
                    all_nodes=all_nodes,
                    resolution=resolution,
                    claim_nodes=claim_nodes,
                    links=links_by_node.get(node.id, []),
                    source_by_id=source_by_id,
                    provider_signal=provider_signals.get(objective.value),
                )
                cells_by_objective[objective].append((node, result))

        root_results: dict[ClaimObjective, _CoverageResult] = {}
        for objective, scoped in cells_by_objective.items():
            direct_root = next(result for node, result in scoped if node.id == root.id)
            children = [(node, result) for node, result in scoped if node.id != root.id]
            root_result = self._aggregate_root(
                root=root,
                objective=objective,
                direct=direct_root,
                children=children,
            )
            root_results[objective] = root_result
            for node, result in scoped:
                effective = root_result if node.id == root.id else result
                fingerprint = _coverage_input_fingerprint(
                    candidate_id=candidate.id,
                    node=node,
                    objective=objective,
                    resolution=resolution,
                    links=links_by_node.get(node.id, []),
                    edges=edges,
                    provider_signal=provider_signals.get(objective.value),
                )
                cell = self._upsert_cell(
                    candidate_id=candidate.id,
                    node=node,
                    objective=objective,
                    result=effective,
                    input_fingerprint=fingerprint,
                )
                decisions.append(
                    ScopeCoverageDecision(
                        scope_node_id=str(node.id),
                        scope_type=node.node_type.value,
                        scope_key=node.canonical_key,
                        lifecycle_key=node.lifecycle_key or None,
                        objective=objective,
                        state=effective.state.value,
                        required=cell.required,
                        supporting_claim_ids=effective.supporting_claim_ids,
                        supporting_evidence_ids=effective.supporting_evidence_ids,
                        expected_item_count=effective.expected_item_count,
                        resolved_item_count=effective.resolved_item_count,
                        reason=effective.reason,
                        missing_frontier_reasons=effective.missing_frontier_reasons,
                    )
                )

        self.session.flush()
        completeness_errors = sorted(
            {
                f"coverage:{decision.scope_type}:{decision.scope_key}:"
                f"{decision.objective.value}:{decision.state}"
                for decision in decisions
                if decision.required
                and decision.state
                not in {
                    ScopedCoverageState.COMPLETE.value,
                    ScopedCoverageState.NOT_APPLICABLE.value,
                }
            }
        )
        root_summary = {
            objective.value: root_results[objective].state.value for objective in ClaimObjective
        }
        return resolution.model_copy(
            update={
                "completeness_errors": completeness_errors,
                "provider_objective_coverage": provider_signals,
                "objective_coverage": root_summary,
                "scope_coverage": decisions,
                "coverage_revision": COVERAGE_EVALUATOR_VERSION,
            }
        )

    def _root_node(self, candidate: CatalogueCandidate) -> CatalogueScopeNode:
        lifecycle = candidate.seed_cycle or (
            str(candidate.seed_intake_year) if candidate.seed_intake_year is not None else ""
        )
        existing = self.session.scalar(
            select(CatalogueScopeNode).where(
                CatalogueScopeNode.candidate_id == candidate.id,
                CatalogueScopeNode.node_type == ScopeNodeType.SCHOLARSHIP_FAMILY,
                CatalogueScopeNode.canonical_key == "scholarship",
                CatalogueScopeNode.lifecycle_key == lifecycle,
            )
        )
        if existing is not None:
            return existing
        node = CatalogueScopeNode(
            candidate_id=candidate.id,
            node_type=ScopeNodeType.SCHOLARSHIP_FAMILY,
            canonical_key="scholarship",
            display_label=candidate.seed_name,
            lifecycle_key=lifecycle,
            discovery_confidence=ScopeDiscoveryConfidence.COMPATIBILITY,
            provenance_json={"adapter": "candidate_root"},
        )
        self.session.add(node)
        self.session.flush()
        return node

    def _upsert_node(self, candidate: CatalogueCandidate, ref: _ScopeRef) -> CatalogueScopeNode:
        existing = self.session.scalar(
            select(CatalogueScopeNode).where(
                CatalogueScopeNode.candidate_id == candidate.id,
                CatalogueScopeNode.node_type == ref.node_type,
                CatalogueScopeNode.canonical_key == ref.canonical_key,
                CatalogueScopeNode.lifecycle_key == ref.lifecycle_key,
            )
        )
        if existing is None:
            existing = CatalogueScopeNode(
                candidate_id=candidate.id,
                node_type=ref.node_type,
                canonical_key=ref.canonical_key,
                display_label=ref.display_label,
                lifecycle_key=ref.lifecycle_key,
                source_id=ref.source_id,
                source_artifact_id=ref.artifact_id,
                discovery_confidence=ref.confidence,
                provenance_json={"derived_from": "resolved_claim"},
            )
            self.session.add(existing)
            self.session.flush()
        elif existing.discovery_confidence in {
            ScopeDiscoveryConfidence.UNRESOLVED,
            ScopeDiscoveryConfidence.COMPATIBILITY,
        }:
            existing.discovery_confidence = ref.confidence
            existing.display_label = ref.display_label
            existing.source_id = existing.source_id or ref.source_id
            existing.source_artifact_id = existing.source_artifact_id or ref.artifact_id
        return existing

    def _upsert_edge(
        self,
        *,
        candidate_id: uuid.UUID,
        parent: CatalogueScopeNode,
        child: CatalogueScopeNode,
        relationship_type: ScopeEdgeType,
        item: ResolvedClaim,
    ) -> None:
        if parent.id == child.id:
            return
        existing = self.session.scalar(
            select(CatalogueScopeEdge).where(
                CatalogueScopeEdge.candidate_id == candidate_id,
                CatalogueScopeEdge.parent_node_id == parent.id,
                CatalogueScopeEdge.child_node_id == child.id,
                CatalogueScopeEdge.relationship_type == relationship_type,
            )
        )
        if existing is not None:
            return
        self.session.add(
            CatalogueScopeEdge(
                candidate_id=candidate_id,
                parent_node_id=parent.id,
                child_node_id=child.id,
                relationship_type=relationship_type,
                source_artifact_id=uuid.UUID(item.artifact_id),
                evidence_excerpt=item.claim.excerpt,
                evidence_start=item.claim.excerpt_start,
                evidence_end=item.claim.excerpt_end,
                confidence=ScopeDiscoveryConfidence.HIGH,
                provenance_json={"claim_id": item.claim_id or _claim_id(item)},
            )
        )

    def _upsert_source_scope_link(
        self,
        *,
        candidate_id: uuid.UUID,
        node: CatalogueScopeNode,
        item: ResolvedClaim,
        relationship_type: SourceScopeRelationship,
        explicit: bool,
    ) -> None:
        source_id = uuid.UUID(item.source_id)
        artifact_id = uuid.UUID(item.artifact_id)
        existing = self.session.scalar(
            select(CatalogueSourceScopeLink).where(
                CatalogueSourceScopeLink.source_id == source_id,
                CatalogueSourceScopeLink.scope_node_id == node.id,
                CatalogueSourceScopeLink.relationship_type == relationship_type,
                CatalogueSourceScopeLink.source_artifact_id == artifact_id,
            )
        )
        if existing is not None:
            existing.applicability_is_explicit = existing.applicability_is_explicit or explicit
            return
        self.session.add(
            CatalogueSourceScopeLink(
                candidate_id=candidate_id,
                source_id=source_id,
                source_artifact_id=artifact_id,
                scope_node_id=node.id,
                relationship_type=relationship_type,
                confidence=ScopeDiscoveryConfidence.HIGH,
                applicability_is_explicit=explicit,
                evidence_excerpt=item.claim.excerpt,
                evidence_start=item.claim.excerpt_start,
                evidence_end=item.claim.excerpt_end,
                provenance_json={"claim_id": item.claim_id or _claim_id(item)},
            )
        )

    def _link_candidate_sources_to_root(
        self,
        candidate: CatalogueCandidate,
        root: CatalogueScopeNode,
        sources: list[CatalogueCandidateSource],
        artifacts: list[CatalogueSourceArtifact],
    ) -> None:
        artifacts_by_source: dict[uuid.UUID, list[CatalogueSourceArtifact]] = defaultdict(list)
        for artifact in artifacts:
            artifacts_by_source[artifact.source_id].append(artifact)
        for source in sources:
            relationship = (
                SourceScopeRelationship.AUTHORITATIVE_FOR
                if source.is_official and source.source_role is CandidateSourceRole.PRIMARY
                else SourceScopeRelationship.SUPPORTS
            )
            source_artifacts = artifacts_by_source.get(source.id) or [None]
            for artifact in source_artifacts:
                artifact_id = artifact.id if artifact is not None else None
                existing = self.session.scalar(
                    select(CatalogueSourceScopeLink).where(
                        CatalogueSourceScopeLink.source_id == source.id,
                        CatalogueSourceScopeLink.scope_node_id == root.id,
                        CatalogueSourceScopeLink.relationship_type == relationship,
                        CatalogueSourceScopeLink.source_artifact_id == artifact_id,
                    )
                )
                if existing is not None:
                    continue
                self.session.add(
                    CatalogueSourceScopeLink(
                        candidate_id=candidate.id,
                        source_id=source.id,
                        source_artifact_id=artifact_id,
                        scope_node_id=root.id,
                        relationship_type=relationship,
                        confidence=(
                            ScopeDiscoveryConfidence.ASSERTED
                            if source.source_role
                            in {CandidateSourceRole.PRIMARY, CandidateSourceRole.SUPPORTING}
                            else ScopeDiscoveryConfidence.HIGH
                        ),
                        applicability_is_explicit=True,
                        provenance_json={"source_role": source.source_role.value},
                    )
                )

    def _topology_edges_from_value(
        self,
        candidate: CatalogueCandidate,
        item: ResolvedClaim,
        nodes: dict[tuple[ScopeNodeType, str, str], CatalogueScopeNode],
    ) -> None:
        claim = item.claim
        lifecycle = claim.scope.cycle_key or (
            candidate.seed_cycle
            or (str(candidate.seed_intake_year) if candidate.seed_intake_year is not None else "")
        )
        if claim.entity_type is ClaimEntityType.TRACK and claim.field_path == "parent_track_key":
            parent_key = _canonical_key(str(claim.value.primitive()))
            child_key = _canonical_key(claim.entity_key)
            parent = nodes.get((ScopeNodeType.ROUTE, parent_key, lifecycle))
            child = nodes.get((ScopeNodeType.ROUTE, child_key, lifecycle))
            if parent is not None and child is not None:
                self._upsert_edge(
                    candidate_id=candidate.id,
                    parent=parent,
                    child=child,
                    relationship_type=ScopeEdgeType.PARENT_CHILD,
                    item=item,
                )
        if (
            claim.entity_type is ClaimEntityType.PROGRAMME
            and claim.field_path == "application_route_keys"
        ):
            programme = nodes.get(
                (ScopeNodeType.PROGRAMME, _canonical_key(claim.entity_key), lifecycle)
            )
            value = claim.value.primitive()
            routes = value if isinstance(value, list) else [str(value)]
            for route_value in routes:
                route = nodes.get(
                    (ScopeNodeType.ROUTE, _canonical_key(str(route_value)), lifecycle)
                )
                if programme is not None and route is not None:
                    self._upsert_edge(
                        candidate_id=candidate.id,
                        parent=programme,
                        child=route,
                        relationship_type=ScopeEdgeType.APPLIES_TO,
                        item=item,
                    )

    def _evaluate_cell(
        self,
        *,
        candidate: CatalogueCandidate,
        root: CatalogueScopeNode,
        node: CatalogueScopeNode,
        objective: ClaimObjective,
        all_nodes: list[CatalogueScopeNode],
        resolution: ClaimResolution,
        claim_nodes: dict[str, set[uuid.UUID]],
        links: list[CatalogueSourceScopeLink],
        source_by_id: dict[uuid.UUID, CatalogueCandidateSource],
        provider_signal: str | None,
    ) -> _CoverageResult:
        supporting = [
            item
            for item in resolution.resolved
            if objective in _objectives_for_resolved_claim(item)
            and _resolved_claim_supports_node(
                item,
                node=node,
                root=root,
                claim_nodes=claim_nodes,
            )
        ]
        support_ids = sorted({item.claim_id or _claim_id(item) for item in supporting})
        evidence_ids = sorted({_evidence_id(item) for item in supporting})
        conflicts = [
            record
            for record in resolution.conflict_records
            if objective in _objectives_for_record(record.entity_type, record.field_path, record.scope)
            and _record_matches_node(record.entity_type, record.entity_key, record.scope, node, root)
        ]
        rejections = [
            record
            for record in resolution.rejection_records
            if objective in _objectives_for_record(record.entity_type, record.field_path, record.scope)
            and _record_matches_node(record.entity_type, record.entity_key, record.scope, node, root)
        ]
        if conflicts:
            return _CoverageResult(
                state=ScopedCoverageState.CONFLICTING,
                reason="resolved claims contain an unresolved conflict at this scope",
                missing_frontier_reasons=["resolve_conflicting_claims"],
                supporting_claim_ids=support_ids,
                supporting_evidence_ids=evidence_ids,
                expected_item_count=None,
                resolved_item_count=len(support_ids),
            )
        if rejections:
            return _CoverageResult(
                state=ScopedCoverageState.QUARANTINED,
                reason="one or more candidate claims at this scope failed deterministic validation",
                missing_frontier_reasons=["review_quarantined_claims"],
                supporting_claim_ids=support_ids,
                supporting_evidence_ids=evidence_ids,
                expected_item_count=None,
                resolved_item_count=len(support_ids),
            )

        applicable_sources = [
            source_by_id[link.source_id]
            for link in links
            if link.source_id in source_by_id
            and link.relationship_type
            in {
                SourceScopeRelationship.AUTHORITATIVE_FOR,
                SourceScopeRelationship.SUPPORTS,
                SourceScopeRelationship.APPLIES_TO,
                SourceScopeRelationship.ENUMERATES,
            }
        ]
        if not applicable_sources:
            return _CoverageResult(
                state=ScopedCoverageState.NOT_YET_ACQUIRED,
                reason="no acquired source is linked to this topology scope",
                missing_frontier_reasons=["acquire_official_source_for_scope"],
                supporting_claim_ids=support_ids,
                supporting_evidence_ids=evidence_ids,
                expected_item_count=None,
                resolved_item_count=len(support_ids),
            )
        if not any(source.status is CandidateSourceStatus.FETCHED for source in applicable_sources):
            return _CoverageResult(
                state=ScopedCoverageState.BLOCKED,
                reason="linked sources exist but none currently has an accepted fetched artifact",
                missing_frontier_reasons=["resolve_source_acquisition_block"],
                supporting_claim_ids=support_ids,
                supporting_evidence_ids=evidence_ids,
                expected_item_count=None,
                resolved_item_count=len(support_ids),
            )

        explicit_applicability = _explicit_objective_applicability(node, objective)
        if explicit_applicability == "not_applicable":
            return _CoverageResult(
                state=ScopedCoverageState.NOT_APPLICABLE,
                reason="deterministic topology applicability marks this objective not applicable",
                missing_frontier_reasons=[],
                supporting_claim_ids=support_ids,
                supporting_evidence_ids=evidence_ids,
                expected_item_count=0,
                resolved_item_count=0,
            )

        requirements = _FINITE_SCOPE_REQUIREMENTS.get((objective, node.node_type))
        if requirements is not None:
            present = {(item.claim.entity_type, item.claim.field_path) for item in supporting}
            missing = sorted(
                f"{entity_type.value}.{field_path}"
                for entity_type, field_path in requirements
                if (entity_type, field_path) not in present
            )
            if not missing:
                if provider_signal == ObjectiveCoverageState.PARTIAL.value:
                    return _CoverageResult(
                        state=ScopedCoverageState.PARTIAL,
                        reason="finite required fields are present but provider reported an incomplete pass",
                        missing_frontier_reasons=["repeat_or_expand_objective_extraction"],
                        supporting_claim_ids=support_ids,
                        supporting_evidence_ids=evidence_ids,
                        expected_item_count=len(requirements),
                        resolved_item_count=len(requirements),
                    )
                return _CoverageResult(
                    state=ScopedCoverageState.COMPLETE,
                    reason="all deterministic required fields for this finite scope are resolved",
                    missing_frontier_reasons=[],
                    supporting_claim_ids=support_ids,
                    supporting_evidence_ids=evidence_ids,
                    expected_item_count=len(requirements),
                    resolved_item_count=len(requirements),
                )
            return _CoverageResult(
                state=ScopedCoverageState.PARTIAL if supporting else ScopedCoverageState.UNKNOWN,
                reason="finite required fields remain unresolved at this scope",
                missing_frontier_reasons=[f"missing_required_field:{item}" for item in missing],
                supporting_claim_ids=support_ids,
                supporting_evidence_ids=evidence_ids,
                expected_item_count=len(requirements),
                resolved_item_count=len(requirements) - len(missing),
            )

        expected_items = _expected_objective_items(node, objective)
        if supporting and expected_items is not None:
            resolved_items = len({_claim_entity_identity(item) for item in supporting})
            if resolved_items >= expected_items and provider_signal != ObjectiveCoverageState.PARTIAL.value:
                return _CoverageResult(
                    state=ScopedCoverageState.COMPLETE,
                    reason="resolved scoped items satisfy the deterministic expected item count",
                    missing_frontier_reasons=[],
                    supporting_claim_ids=support_ids,
                    supporting_evidence_ids=evidence_ids,
                    expected_item_count=expected_items,
                    resolved_item_count=resolved_items,
                )
            return _CoverageResult(
                state=ScopedCoverageState.PARTIAL,
                reason="resolved scoped items do not yet satisfy the deterministic expected item count",
                missing_frontier_reasons=["acquire_or_resolve_expected_items"],
                supporting_claim_ids=support_ids,
                supporting_evidence_ids=evidence_ids,
                expected_item_count=expected_items,
                resolved_item_count=resolved_items,
            )
        if supporting:
            return _CoverageResult(
                state=ScopedCoverageState.PARTIAL,
                reason="validated claims exist but no deterministic expected item count closes this scope",
                missing_frontier_reasons=["establish_expected_item_count_or_applicability"],
                supporting_claim_ids=support_ids,
                supporting_evidence_ids=evidence_ids,
                expected_item_count=None,
                resolved_item_count=len({_claim_entity_identity(item) for item in supporting}),
            )
        if node.id == root.id and provider_signal == ObjectiveCoverageState.NOT_STATED.value:
            return _CoverageResult(
                state=ScopedCoverageState.NOT_STATED,
                reason="provider reported no requested facts, retained as an absence signal only",
                missing_frontier_reasons=["verify_absence_with_deterministic_source_coverage"],
                supporting_claim_ids=[],
                supporting_evidence_ids=[],
                expected_item_count=None,
                resolved_item_count=0,
            )
        if node.id == root.id and provider_signal == ObjectiveCoverageState.NOT_APPLICABLE.value:
            return _CoverageResult(
                state=ScopedCoverageState.UNKNOWN,
                reason="provider not-applicable output is not accepted without explicit applicability proof",
                missing_frontier_reasons=["establish_explicit_not_applicable_relationship"],
                supporting_claim_ids=[],
                supporting_evidence_ids=[],
                expected_item_count=None,
                resolved_item_count=0,
            )
        return _CoverageResult(
            state=ScopedCoverageState.UNKNOWN,
            reason="accepted sources exist but deterministic scoped evidence is insufficient",
            missing_frontier_reasons=["resolve_scoped_evidence"],
            supporting_claim_ids=[],
            supporting_evidence_ids=[],
            expected_item_count=None,
            resolved_item_count=0,
        )

    def _aggregate_root(
        self,
        *,
        root: CatalogueScopeNode,
        objective: ClaimObjective,
        direct: _CoverageResult,
        children: list[tuple[CatalogueScopeNode, _CoverageResult]],
    ) -> _CoverageResult:
        enumerated_type = _ENUMERATED_BRANCH_OBJECTIVES.get(objective)
        relevant_children = (
            [(node, result) for node, result in children if node.node_type is enumerated_type]
            if enumerated_type is not None
            else children
        )
        if not relevant_children:
            return direct
        child_states = [result.state for _node, result in relevant_children]
        for state in (
            ScopedCoverageState.CONFLICTING,
            ScopedCoverageState.QUARANTINED,
            ScopedCoverageState.FAILED,
            ScopedCoverageState.BLOCKED,
        ):
            if state in child_states:
                return _aggregate_result(
                    direct,
                    state=state,
                    reason=f"one or more required child scopes are {state.value}",
                    frontier=[f"resolve_child_scope:{state.value}"],
                )
        unresolved = [
            state
            for state in child_states
            if state not in {ScopedCoverageState.COMPLETE, ScopedCoverageState.NOT_APPLICABLE}
        ]
        if unresolved:
            return _aggregate_result(
                direct,
                state=ScopedCoverageState.PARTIAL,
                reason="one or more required topology branches remain incomplete",
                frontier=["resolve_required_child_scopes"],
            )

        if enumerated_type is not None:
            expected = _expected_child_count(root, enumerated_type)
            actual = len({node.canonical_key for node, _result in relevant_children})
            if expected is None:
                return _aggregate_result(
                    direct,
                    state=ScopedCoverageState.PARTIAL,
                    reason="resolved branches are complete but the authoritative expected branch count is unknown",
                    frontier=[f"establish_expected_child_count:{enumerated_type.value}"],
                    expected=None,
                    resolved=actual,
                )
            if actual < expected:
                return _aggregate_result(
                    direct,
                    state=ScopedCoverageState.PARTIAL,
                    reason="fewer topology branches are resolved than the authoritative expected count",
                    frontier=[f"acquire_missing_child_scope:{enumerated_type.value}"],
                    expected=expected,
                    resolved=actual,
                )
            return _aggregate_result(
                direct,
                state=ScopedCoverageState.COMPLETE,
                reason="all expected topology branches are complete",
                frontier=[],
                expected=expected,
                resolved=actual,
            )

        expected_scope_types = {
            node.node_type for node, _result in relevant_children if node.node_type in _BRANCH_SCOPE_TYPES
        }
        open_types = [
            node_type.value
            for node_type in sorted(expected_scope_types, key=lambda item: item.value)
            if _expected_child_count(root, node_type) is None
        ]
        if open_types:
            return _aggregate_result(
                direct,
                state=ScopedCoverageState.PARTIAL,
                reason="child scopes are individually resolved but the topology frontier is not closed",
                frontier=[f"establish_expected_child_count:{item}" for item in open_types],
            )
        return _aggregate_result(
            direct,
            state=ScopedCoverageState.COMPLETE,
            reason="all required closed child scopes are complete",
            frontier=[],
        )

    def _upsert_cell(
        self,
        *,
        candidate_id: uuid.UUID,
        node: CatalogueScopeNode,
        objective: ClaimObjective,
        result: _CoverageResult,
        input_fingerprint: str,
    ) -> CatalogueCoverageCell:
        cell = self.session.scalar(
            select(CatalogueCoverageCell).where(
                CatalogueCoverageCell.candidate_id == candidate_id,
                CatalogueCoverageCell.objective == objective,
                CatalogueCoverageCell.scope_node_id == node.id,
            )
        )
        if cell is None:
            cell = CatalogueCoverageCell(
                candidate_id=candidate_id,
                objective=objective,
                scope_node_id=node.id,
                state=result.state,
                required=True,
                supporting_claim_ids=result.supporting_claim_ids,
                supporting_evidence_ids=result.supporting_evidence_ids,
                expected_item_count=result.expected_item_count,
                resolved_item_count=result.resolved_item_count,
                reason=result.reason,
                missing_frontier_reasons=result.missing_frontier_reasons,
                evaluator_version=COVERAGE_EVALUATOR_VERSION,
                input_fingerprint=input_fingerprint,
            )
            self.session.add(cell)
            return cell
        cell.state = result.state
        cell.supporting_claim_ids = result.supporting_claim_ids
        cell.supporting_evidence_ids = result.supporting_evidence_ids
        cell.expected_item_count = result.expected_item_count
        cell.resolved_item_count = result.resolved_item_count
        cell.reason = result.reason
        cell.missing_frontier_reasons = result.missing_frontier_reasons
        cell.evaluator_version = COVERAGE_EVALUATOR_VERSION
        cell.input_fingerprint = input_fingerprint
        return cell


def _attached_candidate_context(
    artifacts: list[CatalogueSourceArtifact],
) -> tuple[Session | None, uuid.UUID | None]:
    sessions = {object_session(item) for item in artifacts if object_session(item) is not None}
    if len(sessions) != 1:
        return None, None
    session = next(iter(sessions))
    assert session is not None
    source_ids = {item.source_id for item in artifacts}
    if not source_ids:
        return session, None
    candidate_ids = set(
        session.scalars(
            select(CatalogueCandidateSource.candidate_id).where(
                CatalogueCandidateSource.id.in_(source_ids)
            )
        )
    )
    if len(candidate_ids) != 1:
        return session, None
    return session, next(iter(candidate_ids))


def _detached_evaluation(
    resolution: ClaimResolution,
    provider_signals: dict[str, str],
) -> ClaimResolution:
    """Fail closed when no persistence context exists instead of asserting global completeness."""

    present_by_objective: dict[ClaimObjective, int] = defaultdict(int)
    for item in resolution.resolved:
        for objective in _objectives_for_resolved_claim(item):
            present_by_objective[objective] += 1
    summary: dict[str, str] = {}
    decisions: list[ScopeCoverageDecision] = []
    for objective in ClaimObjective:
        if objective is ClaimObjective.IDENTITY and _detached_identity_complete(resolution.resolved):
            state = ScopedCoverageState.COMPLETE
            reason = "detached compatibility evaluation resolved finite identity fields"
            frontier: list[str] = []
        elif present_by_objective[objective]:
            state = ScopedCoverageState.PARTIAL
            reason = "claims exist but scoped topology is unavailable in this evaluation context"
            frontier = ["persist_and_evaluate_topology"]
        elif provider_signals.get(objective.value) == ObjectiveCoverageState.NOT_STATED.value:
            state = ScopedCoverageState.NOT_STATED
            reason = "provider absence signal retained without scoped completeness proof"
            frontier = ["persist_and_verify_source_scope"]
        else:
            state = ScopedCoverageState.UNKNOWN
            reason = "scoped topology is unavailable in this evaluation context"
            frontier = ["persist_and_evaluate_topology"]
        summary[objective.value] = state.value
        decisions.append(
            ScopeCoverageDecision(
                scope_node_id=None,
                scope_type=ScopeNodeType.SCHOLARSHIP_FAMILY.value,
                scope_key="scholarship",
                lifecycle_key=None,
                objective=objective,
                state=state.value,
                required=True,
                supporting_claim_ids=[],
                supporting_evidence_ids=[],
                expected_item_count=None,
                resolved_item_count=present_by_objective[objective],
                reason=reason,
                missing_frontier_reasons=frontier,
            )
        )
    errors = sorted(
        f"coverage:scholarship_family:scholarship:{item.objective.value}:{item.state}"
        for item in decisions
        if item.state
        not in {ScopedCoverageState.COMPLETE.value, ScopedCoverageState.NOT_APPLICABLE.value}
    )
    return resolution.model_copy(
        update={
            "completeness_errors": errors,
            "provider_objective_coverage": provider_signals,
            "objective_coverage": summary,
            "scope_coverage": decisions,
            "coverage_revision": COVERAGE_EVALUATOR_VERSION,
        }
    )


def _scope_refs_for_claim(
    candidate: CatalogueCandidate,
    item: ResolvedClaim,
    artifacts: dict[uuid.UUID, CatalogueSourceArtifact],
) -> list[_ScopeRef]:
    claim = item.claim
    artifact_id = uuid.UUID(item.artifact_id)
    artifact = artifacts.get(artifact_id)
    source_id = artifact.source_id if artifact is not None else uuid.UUID(item.source_id)
    lifecycle = claim.scope.cycle_key or candidate.seed_cycle or (
        str(candidate.seed_intake_year) if candidate.seed_intake_year is not None else ""
    )
    refs: dict[tuple[ScopeNodeType, str, str], _ScopeRef] = {}

    entity_type = _ENTITY_NODE_TYPES.get(claim.entity_type)
    if entity_type is not None:
        key = _canonical_key(claim.entity_key)
        refs[(entity_type, key, lifecycle)] = _ScopeRef(
            node_type=entity_type,
            canonical_key=key,
            display_label=_claim_entity_label(claim),
            lifecycle_key=lifecycle,
            source_id=source_id,
            artifact_id=artifact_id,
            confidence=ScopeDiscoveryConfidence.HIGH,
        )

    for field_name, node_type in _SCOPE_FIELD_TYPES.items():
        raw = getattr(claim.scope, field_name, None)
        if not raw:
            continue
        key = _canonical_key(raw)
        node_lifecycle = raw if node_type is ScopeNodeType.CYCLE else lifecycle
        refs[(node_type, key, node_lifecycle)] = _ScopeRef(
            node_type=node_type,
            canonical_key=key,
            display_label=raw,
            lifecycle_key=node_lifecycle,
            source_id=source_id,
            artifact_id=artifact_id,
            confidence=ScopeDiscoveryConfidence.ASSERTED,
        )

    primitive = claim.value.primitive()
    if claim.entity_type is ClaimEntityType.SCHOLARSHIP and claim.field_path == "country_code":
        raw = str(primitive)
        key = _canonical_key(raw)
        refs[(ScopeNodeType.COUNTRY, key, lifecycle)] = _ScopeRef(
            node_type=ScopeNodeType.COUNTRY,
            canonical_key=key,
            display_label=raw.upper(),
            lifecycle_key=lifecycle,
            source_id=source_id,
            artifact_id=artifact_id,
            confidence=ScopeDiscoveryConfidence.HIGH,
        )
    if claim.entity_type is ClaimEntityType.PROGRAMME and claim.field_path in {
        "degree_levels",
        "fields_of_study",
    }:
        node_type = (
            ScopeNodeType.DEGREE_LEVEL
            if claim.field_path == "degree_levels"
            else ScopeNodeType.SUBJECT
        )
        values = primitive if isinstance(primitive, list) else [str(primitive)]
        for raw_value in values:
            raw = str(raw_value)
            key = _canonical_key(raw)
            refs[(node_type, key, lifecycle)] = _ScopeRef(
                node_type=node_type,
                canonical_key=key,
                display_label=raw,
                lifecycle_key=lifecycle,
                source_id=source_id,
                artifact_id=artifact_id,
                confidence=ScopeDiscoveryConfidence.HIGH,
            )
    return list(refs.values())


def _entity_node_for_claim(
    claim: ExtractedClaim,
    nodes: list[CatalogueScopeNode],
) -> CatalogueScopeNode | None:
    expected_type = _ENTITY_NODE_TYPES.get(claim.entity_type)
    if expected_type is None:
        return None
    key = _canonical_key(claim.entity_key)
    return next(
        (node for node in nodes if node.node_type is expected_type and node.canonical_key == key),
        None,
    )


def _resolved_claim_supports_node(
    item: ResolvedClaim,
    *,
    node: CatalogueScopeNode,
    root: CatalogueScopeNode,
    claim_nodes: dict[str, set[uuid.UUID]],
) -> bool:
    claim_id = item.claim_id or _claim_id(item)
    if node.id == root.id:
        return True
    if node.id in claim_nodes.get(claim_id, set()):
        return True
    return False


def _record_matches_node(
    entity_type: ClaimEntityType,
    entity_key: str,
    scope: object,
    node: CatalogueScopeNode,
    root: CatalogueScopeNode,
) -> bool:
    if node.id == root.id:
        return True
    mapped_type = _ENTITY_NODE_TYPES.get(entity_type)
    if mapped_type is node.node_type and _canonical_key(entity_key) == node.canonical_key:
        return True
    for field_name, node_type in _SCOPE_FIELD_TYPES.items():
        if node_type is not node.node_type:
            continue
        value = getattr(scope, field_name, None)
        if value and _canonical_key(value) == node.canonical_key:
            return True
    return False


def _objectives_for_resolved_claim(item: ResolvedClaim) -> set[ClaimObjective]:
    if item.objectives:
        return set(item.objectives)
    return _objectives_for_record(item.claim.entity_type, item.claim.field_path, item.claim.scope)


def _objectives_for_record(
    entity_type: ClaimEntityType,
    field_path: str,
    scope: object,
) -> set[ClaimObjective]:
    if entity_type in {ClaimEntityType.SCHOLARSHIP, ClaimEntityType.CYCLE}:
        return {ClaimObjective.IDENTITY}
    if entity_type is ClaimEntityType.PROGRAMME:
        if field_path in {"name", "programme_type", "degree_levels", "display_order"}:
            return {ClaimObjective.PROGRAMMES}
        return {ClaimObjective.PROGRAMME_DETAILS}
    if entity_type is ClaimEntityType.TRACK:
        return {ClaimObjective.ROUTES}
    if entity_type is ClaimEntityType.INSTITUTION:
        return (
            {ClaimObjective.ROUTES}
            if getattr(scope, "track_key", None)
            else {ClaimObjective.IDENTITY}
        )
    if entity_type is ClaimEntityType.ELIGIBILITY:
        if field_path in {"condition", "is_exclusion", "notes"}:
            return {ClaimObjective.ELIGIBILITY_CONTEXT}
        return {ClaimObjective.ELIGIBILITY}
    if entity_type is ClaimEntityType.DOCUMENT:
        if field_path in {"name", "display_order"}:
            return {ClaimObjective.DOCUMENTS_CORE}
        if field_path in {"required", "condition", "submission_stage"}:
            return {ClaimObjective.DOCUMENTS_REQUIREMENTS}
        if field_path in {"original_count", "copy_count", "form_year"}:
            return {ClaimObjective.DOCUMENTS_COUNTS}
        return {ClaimObjective.DOCUMENTS_FORMAT}
    if entity_type is ClaimEntityType.FUNDING:
        return {ClaimObjective.FUNDING}
    if entity_type in {
        ClaimEntityType.DEADLINE,
        ClaimEntityType.EVENT,
        ClaimEntityType.STEP,
        ClaimEntityType.RESOURCE,
    }:
        return {ClaimObjective.APPLICATION_TIMELINE}
    return set()


def _detached_identity_complete(claims: list[ResolvedClaim]) -> bool:
    present = {
        (item.claim.entity_type, item.claim.field_path)
        for item in claims
        if ClaimObjective.IDENTITY in _objectives_for_resolved_claim(item)
    }
    return _FINITE_SCOPE_REQUIREMENTS[
        (ClaimObjective.IDENTITY, ScopeNodeType.SCHOLARSHIP_FAMILY)
    ].issubset(present)


def _claim_entity_label(claim: ExtractedClaim) -> str:
    if claim.field_path in {"name", "canonical_name"}:
        primitive = claim.value.primitive()
        if isinstance(primitive, str):
            return primitive[:255]
    return claim.entity_key.replace("_", " ").strip().title()[:255]


def _canonical_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return normalized[:255] or hashlib.sha256(value.encode()).hexdigest()[:32]


def _claim_id(item: ResolvedClaim) -> str:
    payload = {
        "artifact_id": item.artifact_id,
        "entity_type": item.claim.entity_type.value,
        "entity_key": item.claim.entity_key,
        "field_path": item.claim.field_path,
        "scope": item.claim.scope.model_dump(mode="json"),
        "value": item.claim.value.model_dump(mode="json"),
        "excerpt_start": item.claim.excerpt_start,
        "excerpt_end": item.claim.excerpt_end,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _evidence_id(item: ResolvedClaim) -> str:
    return hashlib.sha256(
        f"{item.artifact_id}:{item.content_hash}:{item.claim.excerpt_start}:"
        f"{item.claim.excerpt_end}".encode()
    ).hexdigest()


def _claim_entity_identity(item: ResolvedClaim) -> str:
    return f"{item.claim.entity_type.value}:{item.claim.entity_key}"


def _expected_child_count(node: CatalogueScopeNode, node_type: ScopeNodeType) -> int | None:
    raw = (node.expected_child_counts or {}).get(node_type.value)
    return int(raw) if raw is not None else None


def _expected_objective_items(
    node: CatalogueScopeNode,
    objective: ClaimObjective,
) -> int | None:
    raw = (node.expected_child_counts or {}).get(f"objective:{objective.value}")
    return int(raw) if raw is not None else None


def _explicit_objective_applicability(
    node: CatalogueScopeNode,
    objective: ClaimObjective,
) -> str | None:
    raw = (node.provenance_json or {}).get("objective_applicability", {})
    if not isinstance(raw, dict):
        return None
    value = raw.get(objective.value)
    return str(value) if value is not None else None


def _aggregate_result(
    direct: _CoverageResult,
    *,
    state: ScopedCoverageState,
    reason: str,
    frontier: list[str],
    expected: int | None = None,
    resolved: int | None = None,
) -> _CoverageResult:
    return _CoverageResult(
        state=state,
        reason=reason,
        missing_frontier_reasons=sorted(
            set(direct.missing_frontier_reasons + frontier)
        ),
        supporting_claim_ids=direct.supporting_claim_ids,
        supporting_evidence_ids=direct.supporting_evidence_ids,
        expected_item_count=expected if expected is not None else direct.expected_item_count,
        resolved_item_count=resolved if resolved is not None else direct.resolved_item_count,
    )


def _coverage_input_fingerprint(
    *,
    candidate_id: uuid.UUID,
    node: CatalogueScopeNode,
    objective: ClaimObjective,
    resolution: ClaimResolution,
    links: list[CatalogueSourceScopeLink],
    edges: list[CatalogueScopeEdge],
    provider_signal: str | None,
) -> str:
    payload = {
        "evaluator": COVERAGE_EVALUATOR_VERSION,
        "candidate_id": str(candidate_id),
        "scope": {
            "id": str(node.id),
            "type": node.node_type.value,
            "key": node.canonical_key,
            "lifecycle": node.lifecycle_key,
            "expected_child_counts": node.expected_child_counts,
            "provenance": node.provenance_json,
        },
        "objective": objective.value,
        "claims": sorted(item.claim_id or _claim_id(item) for item in resolution.resolved),
        "conflicts": sorted(resolution.conflicts),
        "rejected": sorted(resolution.rejected),
        "links": sorted(
            (
                str(item.source_id),
                str(item.source_artifact_id or ""),
                item.relationship_type.value,
                item.applicability_is_explicit,
            )
            for item in links
        ),
        "edges": sorted(
            (
                str(item.parent_node_id),
                str(item.child_node_id),
                item.relationship_type.value,
                str(item.source_artifact_id or ""),
            )
            for item in edges
        ),
        "provider_signal": provider_signal,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
