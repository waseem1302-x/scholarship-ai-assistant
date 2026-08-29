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
    ClaimEntityType,
    ClaimObjective,
    ClaimResolution,
    ExtractedClaim,
    ObjectiveCoverageState,
    ResolvedClaim,
    ScopeCoverageDecision,
    ScopedCoverageState,
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
_OBJECTIVE_BRANCH_TYPES: dict[ClaimObjective, set[ScopeNodeType]] = {
    ClaimObjective.PROGRAMMES: {ScopeNodeType.PROGRAMME},
    ClaimObjective.PROGRAMME_DETAILS: {ScopeNodeType.PROGRAMME},
    ClaimObjective.ROUTES: {ScopeNodeType.ROUTE},
}
_ENUMERATED_BRANCH_OBJECTIVES: dict[ClaimObjective, ScopeNodeType] = {
    ClaimObjective.PROGRAMMES: ScopeNodeType.PROGRAMME,
    ClaimObjective.ROUTES: ScopeNodeType.ROUTE,
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
_TERMINAL_COMPLETE_STATES = {
    ScopedCoverageState.COMPLETE,
    ScopedCoverageState.NOT_APPLICABLE,
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
    """Compute scoped coverage from validated claims and persisted topology.

    Provider coverage is retained only as a conservative signal. It can keep a cell open, but it
    cannot by itself establish ``complete`` or ``not_applicable``.
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
                    CatalogueCandidateSource.candidate_id == candidate.id
                )
            )
        )
        source_by_id = {source.id: source for source in sources}
        all_artifacts = (
            list(
                self.session.scalars(
                    select(CatalogueSourceArtifact).where(
                        CatalogueSourceArtifact.source_id.in_(source_by_id)
                    )
                )
            )
            if source_by_id
            else []
        )
        artifact_by_id = {artifact.id: artifact for artifact in all_artifacts}
        latest_artifact_by_source: dict[uuid.UUID, CatalogueSourceArtifact] = {}
        for artifact in all_artifacts:
            current = latest_artifact_by_source.get(artifact.source_id)
            if current is None or artifact.created_at > current.created_at:
                latest_artifact_by_source[artifact.source_id] = artifact

        root = self._root_node(candidate)
        nodes: dict[tuple[ScopeNodeType, str, str], CatalogueScopeNode] = {
            (root.node_type, root.canonical_key, root.lifecycle_key): root
        }
        self._link_candidate_sources_to_root(
            candidate,
            root,
            sources,
            latest_artifact_by_source,
        )

        claim_nodes: dict[str, set[uuid.UUID]] = defaultdict(set)
        claim_item_by_id: dict[str, ResolvedClaim] = {}
        for item in resolution.resolved:
            claim_id = item.claim_id or _claim_id(item)
            claim_item_by_id[claim_id] = item
            claim_nodes[claim_id].add(root.id)
            refs = _scope_refs_for_claim(candidate, item, artifact_by_id)
            for ref in refs:
                node = self._upsert_node(candidate, ref)
                nodes[(node.node_type, node.canonical_key, node.lifecycle_key)] = node
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
                    relationship_type=_source_relationship_for_claim(item.claim),
                    explicit=node.id != root.id,
                )

        self.session.flush()
        for item in resolution.resolved:
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
        root_results: dict[ClaimObjective, _CoverageResult] = {}
        for objective in ClaimObjective:
            target_nodes = self._target_nodes(
                root=root,
                nodes=all_nodes,
                edges=edges,
                claim_nodes=claim_nodes,
                claim_item_by_id=claim_item_by_id,
                objective=objective,
            )
            scoped_results: list[tuple[CatalogueScopeNode, _CoverageResult]] = []
            for node in target_nodes:
                result = self._evaluate_cell(
                    root=root,
                    node=node,
                    objective=objective,
                    resolution=resolution,
                    claim_nodes=claim_nodes,
                    claim_item_by_id=claim_item_by_id,
                    links=links_by_node.get(node.id, []),
                    edges=edges,
                    source_by_id=source_by_id,
                    provider_signal=provider_signals.get(objective.value),
                )
                scoped_results.append((node, result))

            direct_root = next(result for node, result in scoped_results if node.id == root.id)
            children = [(node, result) for node, result in scoped_results if node.id != root.id]
            root_result = self._aggregate_root(
                root=root,
                objective=objective,
                direct=direct_root,
                children=children,
            )
            root_results[objective] = root_result

            for node, result in scoped_results:
                effective = root_result if node.id == root.id else result
                fingerprint = _coverage_input_fingerprint(
                    candidate_id=candidate.id,
                    node=node,
                    objective=objective,
                    resolution=resolution,
                    links=links_by_node.get(node.id, []),
                    edges=edges,
                    sources=source_by_id,
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
                        state=effective.state,
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
                f"{decision.objective.value}:{decision.state.value}"
                for decision in decisions
                if decision.required and decision.state not in _TERMINAL_COMPLETE_STATES
            }
        )
        return resolution.model_copy(
            update={
                "completeness_errors": completeness_errors,
                "provider_objective_coverage": provider_signals,
                "objective_coverage": {
                    objective.value: root_results[objective].state.value
                    for objective in ClaimObjective
                },
                "scope_coverage": decisions,
                "coverage_revision": COVERAGE_EVALUATOR_VERSION,
            }
        )

    def _target_nodes(
        self,
        *,
        root: CatalogueScopeNode,
        nodes: list[CatalogueScopeNode],
        edges: list[CatalogueScopeEdge],
        claim_nodes: dict[str, set[uuid.UUID]],
        claim_item_by_id: dict[str, ResolvedClaim],
        objective: ClaimObjective,
    ) -> list[CatalogueScopeNode]:
        selected: dict[uuid.UUID, CatalogueScopeNode] = {root.id: root}
        branch_types = _OBJECTIVE_BRANCH_TYPES.get(objective, set())
        for node in nodes:
            if node.id == root.id:
                continue
            if node.node_type in branch_types:
                selected[node.id] = node
                continue
            if _explicit_objective_applicability(node, objective) is not None:
                selected[node.id] = node
                continue
            if _node_has_direct_objective_claim(
                node.id,
                objective=objective,
                claim_nodes=claim_nodes,
                claim_item_by_id=claim_item_by_id,
            ):
                selected[node.id] = node
                continue
            if _node_has_objective_inheritance(node.id, objective=objective, edges=edges):
                selected[node.id] = node
        return sorted(
            selected.values(),
            key=lambda node: (
                0 if node.id == root.id else 1,
                node.node_type.value,
                node.lifecycle_key,
                node.canonical_key,
            ),
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
                provenance_json={
                    "claim_id": item.claim_id or _claim_id(item),
                    "derived_from": "resolved_claim",
                },
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
                provenance_json={
                    "claim_id": item.claim_id or _claim_id(item),
                    "derived_from": "resolved_claim",
                },
            )
        )

    def _link_candidate_sources_to_root(
        self,
        candidate: CatalogueCandidate,
        root: CatalogueScopeNode,
        sources: list[CatalogueCandidateSource],
        latest_artifact_by_source: dict[uuid.UUID, CatalogueSourceArtifact],
    ) -> None:
        for source in sources:
            relationship = (
                SourceScopeRelationship.AUTHORITATIVE_FOR
                if source.is_official and source.source_role is CandidateSourceRole.PRIMARY
                else SourceScopeRelationship.SUPPORTS
            )
            artifact = latest_artifact_by_source.get(source.id)
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
                    provenance_json={
                        "source_role": source.source_role.value,
                        "derived_from": "candidate_source",
                    },
                )
            )

    def _topology_edges_from_value(
        self,
        candidate: CatalogueCandidate,
        item: ResolvedClaim,
        nodes: dict[tuple[ScopeNodeType, str, str], CatalogueScopeNode],
    ) -> None:
        claim = item.claim
        lifecycle = claim.scope.cycle_key or candidate.seed_cycle or (
            str(candidate.seed_intake_year) if candidate.seed_intake_year is not None else ""
        )
        if claim.entity_type is ClaimEntityType.TRACK and claim.field_path == "parent_track_key":
            parent = nodes.get(
                (
                    ScopeNodeType.ROUTE,
                    _canonical_key(str(claim.value.primitive())),
                    lifecycle,
                )
            )
            child = nodes.get(
                (ScopeNodeType.ROUTE, _canonical_key(claim.entity_key), lifecycle)
            )
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
        root: CatalogueScopeNode,
        node: CatalogueScopeNode,
        objective: ClaimObjective,
        resolution: ClaimResolution,
        claim_nodes: dict[str, set[uuid.UUID]],
        claim_item_by_id: dict[str, ResolvedClaim],
        links: list[CatalogueSourceScopeLink],
        edges: list[CatalogueScopeEdge],
        source_by_id: dict[uuid.UUID, CatalogueCandidateSource],
        provider_signal: str | None,
    ) -> _CoverageResult:
        supporting = [
            item
            for claim_id, item in claim_item_by_id.items()
            if objective in _objectives_for_resolved_claim(item)
            and _claim_supports_node(
                claim_id,
                node=node,
                root=root,
                objective=objective,
                claim_nodes=claim_nodes,
                edges=edges,
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
        if conflicts:
            return _result(
                ScopedCoverageState.CONFLICTING,
                "resolved claims contain an unresolved conflict at this scope",
                ["resolve_conflicting_claims"],
                support_ids,
                evidence_ids,
            )

        rejections = [
            record
            for record in resolution.rejection_records
            if objective in _objectives_for_record(record.entity_type, record.field_path, record.scope)
            and _record_matches_node(record.entity_type, record.entity_key, record.scope, node, root)
        ]
        if rejections:
            return _result(
                ScopedCoverageState.QUARANTINED,
                "one or more candidate claims at this scope failed deterministic validation",
                ["review_quarantined_claims"],
                support_ids,
                evidence_ids,
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
            return _result(
                ScopedCoverageState.NOT_YET_ACQUIRED,
                "no acquired source is linked to this topology scope",
                ["acquire_official_source_for_scope"],
                support_ids,
                evidence_ids,
            )
        if all(source.status is CandidateSourceStatus.FAILED for source in applicable_sources):
            return _result(
                ScopedCoverageState.FAILED,
                "all sources linked to this scope failed acquisition",
                ["retry_or_replace_failed_sources"],
                support_ids,
                evidence_ids,
            )
        if not any(source.status is CandidateSourceStatus.FETCHED for source in applicable_sources):
            return _result(
                ScopedCoverageState.BLOCKED,
                "linked sources exist but none currently has an accepted fetched artifact",
                ["resolve_source_acquisition_block"],
                support_ids,
                evidence_ids,
            )

        applicability = _explicit_objective_applicability(node, objective)
        if applicability == "not_applicable":
            return _CoverageResult(
                state=ScopedCoverageState.NOT_APPLICABLE,
                reason="explicit typed applicability marks this objective not applicable",
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
            if not missing and provider_signal != ObjectiveCoverageState.PARTIAL.value:
                return _CoverageResult(
                    state=ScopedCoverageState.COMPLETE,
                    reason="all deterministic required fields for this finite scope are resolved",
                    missing_frontier_reasons=[],
                    supporting_claim_ids=support_ids,
                    supporting_evidence_ids=evidence_ids,
                    expected_item_count=len(requirements),
                    resolved_item_count=len(requirements),
                )
            frontier = [f"missing_required_field:{item}" for item in missing]
            if not missing:
                frontier.append("repeat_or_expand_objective_extraction")
            return _CoverageResult(
                state=ScopedCoverageState.PARTIAL if supporting else ScopedCoverageState.UNKNOWN,
                reason="finite scope remains open after deterministic validation",
                missing_frontier_reasons=frontier,
                supporting_claim_ids=support_ids,
                supporting_evidence_ids=evidence_ids,
                expected_item_count=len(requirements),
                resolved_item_count=len(requirements) - len(missing),
            )

        expected_items = _expected_objective_items(node, objective)
        resolved_items = len({_claim_entity_identity(item) for item in supporting})
        if expected_items is not None:
            if (
                resolved_items >= expected_items
                and provider_signal != ObjectiveCoverageState.PARTIAL.value
            ):
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
                state=ScopedCoverageState.PARTIAL if supporting else ScopedCoverageState.UNKNOWN,
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
                reason="validated claims exist but no deterministic frontier closure proves completeness",
                missing_frontier_reasons=["establish_expected_item_count_or_applicability"],
                supporting_claim_ids=support_ids,
                supporting_evidence_ids=evidence_ids,
                expected_item_count=None,
                resolved_item_count=resolved_items,
            )
        if provider_signal == ObjectiveCoverageState.NOT_STATED.value:
            return _CoverageResult(
                state=ScopedCoverageState.NOT_STATED,
                reason="provider absence signal is retained but does not prove semantic completeness",
                missing_frontier_reasons=["verify_absence_with_deterministic_source_coverage"],
                supporting_claim_ids=[],
                supporting_evidence_ids=[],
                expected_item_count=None,
                resolved_item_count=0,
            )
        if provider_signal == ObjectiveCoverageState.NOT_APPLICABLE.value:
            return _CoverageResult(
                state=ScopedCoverageState.UNKNOWN,
                reason="provider not-applicable output lacks explicit typed applicability proof",
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
        aggregate_support_ids = sorted(
            set(direct.supporting_claim_ids).union(
                *(set(result.supporting_claim_ids) for _node, result in children)
            )
        )
        aggregate_evidence_ids = sorted(
            set(direct.supporting_evidence_ids).union(
                *(set(result.supporting_evidence_ids) for _node, result in children)
            )
        )
        base = _CoverageResult(
            state=direct.state,
            reason=direct.reason,
            missing_frontier_reasons=list(direct.missing_frontier_reasons),
            supporting_claim_ids=aggregate_support_ids,
            supporting_evidence_ids=aggregate_evidence_ids,
            expected_item_count=direct.expected_item_count,
            resolved_item_count=max(direct.resolved_item_count, len(aggregate_support_ids)),
        )
        if not children:
            return base

        child_states = [result.state for _node, result in children]
        for state in (
            ScopedCoverageState.CONFLICTING,
            ScopedCoverageState.QUARANTINED,
            ScopedCoverageState.FAILED,
            ScopedCoverageState.BLOCKED,
        ):
            if state in child_states:
                return _aggregate_result(
                    base,
                    state=state,
                    reason=f"one or more required child scopes are {state.value}",
                    frontier=[f"resolve_child_scope:{state.value}"],
                )
        if any(state not in _TERMINAL_COMPLETE_STATES for state in child_states):
            return _aggregate_result(
                base,
                state=ScopedCoverageState.PARTIAL,
                reason="one or more required topology branches remain incomplete",
                frontier=["resolve_required_child_scopes"],
            )

        enumerated_type = _ENUMERATED_BRANCH_OBJECTIVES.get(objective)
        if enumerated_type is not None:
            enumerated_children = [
                node for node, _result in children if node.node_type is enumerated_type
            ]
            expected = _expected_child_count(root, enumerated_type)
            actual = len({node.canonical_key for node in enumerated_children})
            if expected is None:
                return _aggregate_result(
                    base,
                    state=ScopedCoverageState.PARTIAL,
                    reason="resolved branches are complete but the authoritative expected branch count is unknown",
                    frontier=[f"establish_expected_child_count:{enumerated_type.value}"],
                    expected=None,
                    resolved=actual,
                )
            if actual < expected:
                return _aggregate_result(
                    base,
                    state=ScopedCoverageState.PARTIAL,
                    reason="fewer topology branches are resolved than the authoritative expected count",
                    frontier=[f"acquire_missing_child_scope:{enumerated_type.value}"],
                    expected=expected,
                    resolved=actual,
                )
            return _aggregate_result(
                base,
                state=ScopedCoverageState.COMPLETE,
                reason="all authoritative expected topology branches are complete",
                frontier=[],
                expected=expected,
                resolved=actual,
            )

        if base.state in _TERMINAL_COMPLETE_STATES:
            return _aggregate_result(
                base,
                state=base.state,
                reason="root evidence and every applicable child scope are complete",
                frontier=[],
            )
        return _aggregate_result(
            base,
            state=ScopedCoverageState.PARTIAL,
            reason="child scopes are complete but root frontier closure remains unresolved",
            frontier=["close_root_objective_frontier"],
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
                state=state,
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
        f"coverage:scholarship_family:scholarship:{item.objective.value}:{item.state.value}"
        for item in decisions
        if item.state not in _TERMINAL_COMPLETE_STATES
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
        _add_ref(
            refs,
            node_type=entity_type,
            raw_key=claim.entity_key,
            display_label=_claim_entity_label(claim),
            lifecycle=lifecycle,
            source_id=source_id,
            artifact_id=artifact_id,
            confidence=ScopeDiscoveryConfidence.HIGH,
        )

    for field_name, node_type in _SCOPE_FIELD_TYPES.items():
        raw = getattr(claim.scope, field_name, None)
        if not raw or node_type is ScopeNodeType.SCHOLARSHIP_FAMILY:
            continue
        _add_ref(
            refs,
            node_type=node_type,
            raw_key=raw,
            display_label=raw,
            lifecycle=raw if node_type is ScopeNodeType.CYCLE else lifecycle,
            source_id=source_id,
            artifact_id=artifact_id,
            confidence=ScopeDiscoveryConfidence.ASSERTED,
        )

    primitive = claim.value.primitive()
    if claim.entity_type is ClaimEntityType.SCHOLARSHIP and claim.field_path == "country_code":
        raw = str(primitive)
        _add_ref(
            refs,
            node_type=ScopeNodeType.COUNTRY,
            raw_key=raw,
            display_label=raw.upper(),
            lifecycle=lifecycle,
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
            _add_ref(
                refs,
                node_type=node_type,
                raw_key=raw,
                display_label=raw,
                lifecycle=lifecycle,
                source_id=source_id,
                artifact_id=artifact_id,
                confidence=ScopeDiscoveryConfidence.HIGH,
            )
    if claim.entity_type is ClaimEntityType.TRACK and claim.field_path == "parent_track_key":
        raw = str(primitive)
        _add_ref(
            refs,
            node_type=ScopeNodeType.ROUTE,
            raw_key=raw,
            display_label=raw.replace("_", " ").title(),
            lifecycle=lifecycle,
            source_id=source_id,
            artifact_id=artifact_id,
            confidence=ScopeDiscoveryConfidence.HIGH,
        )
    if (
        claim.entity_type is ClaimEntityType.PROGRAMME
        and claim.field_path == "application_route_keys"
    ):
        values = primitive if isinstance(primitive, list) else [str(primitive)]
        for raw_value in values:
            raw = str(raw_value)
            _add_ref(
                refs,
                node_type=ScopeNodeType.ROUTE,
                raw_key=raw,
                display_label=raw.replace("_", " ").title(),
                lifecycle=lifecycle,
                source_id=source_id,
                artifact_id=artifact_id,
                confidence=ScopeDiscoveryConfidence.HIGH,
            )
    return list(refs.values())


def _add_ref(
    refs: dict[tuple[ScopeNodeType, str, str], _ScopeRef],
    *,
    node_type: ScopeNodeType,
    raw_key: str,
    display_label: str,
    lifecycle: str,
    source_id: uuid.UUID,
    artifact_id: uuid.UUID,
    confidence: ScopeDiscoveryConfidence,
) -> None:
    key = _canonical_key(raw_key)
    refs[(node_type, key, lifecycle)] = _ScopeRef(
        node_type=node_type,
        canonical_key=key,
        display_label=display_label[:255],
        lifecycle_key=lifecycle,
        source_id=source_id,
        artifact_id=artifact_id,
        confidence=confidence,
    )


def _source_relationship_for_claim(claim: ExtractedClaim) -> SourceScopeRelationship:
    if (
        claim.entity_type is ClaimEntityType.PROGRAMME
        and claim.field_path == "name"
    ) or (
        claim.entity_type is ClaimEntityType.TRACK
        and claim.field_path == "name"
    ):
        return SourceScopeRelationship.ENUMERATES
    return SourceScopeRelationship.SUPPORTS


def _node_has_direct_objective_claim(
    node_id: uuid.UUID,
    *,
    objective: ClaimObjective,
    claim_nodes: dict[str, set[uuid.UUID]],
    claim_item_by_id: dict[str, ResolvedClaim],
) -> bool:
    return any(
        node_id in claim_nodes.get(claim_id, set())
        and objective in _objectives_for_resolved_claim(item)
        for claim_id, item in claim_item_by_id.items()
    )


def _node_has_objective_inheritance(
    node_id: uuid.UUID,
    *,
    objective: ClaimObjective,
    edges: list[CatalogueScopeEdge],
) -> bool:
    return any(
        edge.child_node_id == node_id
        and edge.relationship_type is ScopeEdgeType.INHERITS_TO
        and _edge_allows_objective(edge, objective)
        for edge in edges
    )


def _claim_supports_node(
    claim_id: str,
    *,
    node: CatalogueScopeNode,
    root: CatalogueScopeNode,
    objective: ClaimObjective,
    claim_nodes: dict[str, set[uuid.UUID]],
    edges: list[CatalogueScopeEdge],
) -> bool:
    direct_nodes = claim_nodes.get(claim_id, set())
    if node.id == root.id or node.id in direct_nodes:
        return True
    return any(
        edge.parent_node_id in direct_nodes
        and edge.child_node_id == node.id
        and edge.relationship_type is ScopeEdgeType.INHERITS_TO
        and _edge_allows_objective(edge, objective)
        for edge in edges
    )


def _edge_allows_objective(edge: CatalogueScopeEdge, objective: ClaimObjective) -> bool:
    provenance = edge.provenance_json or {}
    objectives = provenance.get("objectives")
    if not isinstance(objectives, list):
        return False
    values = {str(value) for value in objectives}
    return "*" in values or objective.value in values


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
        objectives = {ClaimObjective.ROUTES}
        if field_path in {"application_url", "application_method"}:
            objectives.add(ClaimObjective.APPLICATION_TIMELINE)
        return objectives
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


def _result(
    state: ScopedCoverageState,
    reason: str,
    frontier: list[str],
    claim_ids: list[str],
    evidence_ids: list[str],
) -> _CoverageResult:
    return _CoverageResult(
        state=state,
        reason=reason,
        missing_frontier_reasons=frontier,
        supporting_claim_ids=claim_ids,
        supporting_evidence_ids=evidence_ids,
        expected_item_count=None,
        resolved_item_count=len(claim_ids),
    )


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
        missing_frontier_reasons=sorted(set(direct.missing_frontier_reasons + frontier)),
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
    sources: dict[uuid.UUID, CatalogueCandidateSource],
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
            "expectation_provenance": node.expectation_provenance,
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
                sources[item.source_id].status.value if item.source_id in sources else "missing",
            )
            for item in links
        ),
        "edges": sorted(
            (
                str(item.parent_node_id),
                str(item.child_node_id),
                item.relationship_type.value,
                str(item.source_artifact_id or ""),
                json.dumps(item.provenance_json or {}, sort_keys=True),
            )
            for item in edges
        ),
        "provider_signal": provider_signal,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
