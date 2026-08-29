"""Transactional helpers for reviewed or deterministic topology declarations."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueScopeEdge,
    CatalogueScopeNode,
    CatalogueSourceScopeLink,
    ScopeDiscoveryConfidence,
    ScopeEdgeType,
    ScopeNodeType,
    SourceScopeRelationship,
)


class CatalogueTopologyService:
    """Persist explicit topology without committing the caller's transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_scope(
        self,
        *,
        candidate_id: uuid.UUID,
        node_type: ScopeNodeType,
        canonical_key: str,
        display_label: str,
        lifecycle_key: str = "",
        confidence: ScopeDiscoveryConfidence = ScopeDiscoveryConfidence.ASSERTED,
        source_id: uuid.UUID | None = None,
        source_artifact_id: uuid.UUID | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> CatalogueScopeNode:
        key = canonical_key.strip()
        if not key:
            raise ValueError("scope canonical_key must be non-empty")
        existing = self.session.scalar(
            select(CatalogueScopeNode).where(
                CatalogueScopeNode.candidate_id == candidate_id,
                CatalogueScopeNode.node_type == node_type,
                CatalogueScopeNode.canonical_key == key,
                CatalogueScopeNode.lifecycle_key == lifecycle_key,
            )
        )
        if existing is None:
            existing = CatalogueScopeNode(
                candidate_id=candidate_id,
                node_type=node_type,
                canonical_key=key,
                display_label=display_label.strip()[:255] or key,
                lifecycle_key=lifecycle_key,
                source_id=source_id,
                source_artifact_id=source_artifact_id,
                discovery_confidence=confidence,
                provenance_json=dict(provenance or {}),
            )
            self.session.add(existing)
            self.session.flush()
            return existing
        existing.display_label = display_label.strip()[:255] or existing.display_label
        existing.discovery_confidence = confidence
        existing.source_id = source_id or existing.source_id
        existing.source_artifact_id = source_artifact_id or existing.source_artifact_id
        if provenance:
            merged = dict(existing.provenance_json or {})
            merged.update(provenance)
            existing.provenance_json = merged
        existing.version += 1
        self.session.flush()
        return existing

    def declare_edge(
        self,
        *,
        candidate_id: uuid.UUID,
        parent_node_id: uuid.UUID,
        child_node_id: uuid.UUID,
        relationship_type: ScopeEdgeType,
        objectives: Iterable[ClaimObjective | str] = (),
        source_artifact_id: uuid.UUID | None = None,
        evidence_excerpt: str | None = None,
        evidence_start: int | None = None,
        evidence_end: int | None = None,
        confidence: ScopeDiscoveryConfidence = ScopeDiscoveryConfidence.ASSERTED,
        provenance: dict[str, Any] | None = None,
    ) -> CatalogueScopeEdge:
        if parent_node_id == child_node_id:
            raise ValueError("scope edge cannot point to itself")
        objective_keys = sorted(
            {
                item.value if isinstance(item, ClaimObjective) else str(item)
                for item in objectives
            }
        )
        existing = self.session.scalar(
            select(CatalogueScopeEdge).where(
                CatalogueScopeEdge.candidate_id == candidate_id,
                CatalogueScopeEdge.parent_node_id == parent_node_id,
                CatalogueScopeEdge.child_node_id == child_node_id,
                CatalogueScopeEdge.relationship_type == relationship_type,
            )
        )
        merged_provenance = dict(provenance or {})
        if objective_keys:
            merged_provenance["objectives"] = objective_keys
        if existing is None:
            existing = CatalogueScopeEdge(
                candidate_id=candidate_id,
                parent_node_id=parent_node_id,
                child_node_id=child_node_id,
                relationship_type=relationship_type,
                objective_keys=objective_keys,
                source_artifact_id=source_artifact_id,
                evidence_excerpt=evidence_excerpt,
                evidence_start=evidence_start,
                evidence_end=evidence_end,
                confidence=confidence,
                provenance_json=merged_provenance,
            )
            self.session.add(existing)
            self.session.flush()
            return existing
        existing.objective_keys = objective_keys
        existing.source_artifact_id = source_artifact_id or existing.source_artifact_id
        existing.evidence_excerpt = evidence_excerpt or existing.evidence_excerpt
        existing.evidence_start = evidence_start if evidence_start is not None else existing.evidence_start
        existing.evidence_end = evidence_end if evidence_end is not None else existing.evidence_end
        existing.confidence = confidence
        provenance_json = dict(existing.provenance_json or {})
        provenance_json.update(merged_provenance)
        existing.provenance_json = provenance_json
        self.session.flush()
        return existing

    def declare_inheritance(
        self,
        *,
        candidate_id: uuid.UUID,
        parent_node_id: uuid.UUID,
        child_node_id: uuid.UUID,
        objectives: Iterable[ClaimObjective | str],
        source_artifact_id: uuid.UUID | None = None,
        evidence_excerpt: str | None = None,
        evidence_start: int | None = None,
        evidence_end: int | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> CatalogueScopeEdge:
        objective_list = list(objectives)
        if not objective_list:
            raise ValueError("inheritance requires at least one explicit objective")
        return self.declare_edge(
            candidate_id=candidate_id,
            parent_node_id=parent_node_id,
            child_node_id=child_node_id,
            relationship_type=ScopeEdgeType.INHERITS_TO,
            objectives=objective_list,
            source_artifact_id=source_artifact_id,
            evidence_excerpt=evidence_excerpt,
            evidence_start=evidence_start,
            evidence_end=evidence_end,
            provenance=provenance,
        )

    def declare_source_scope(
        self,
        *,
        candidate_id: uuid.UUID,
        source_id: uuid.UUID,
        scope_node_id: uuid.UUID,
        relationship_type: SourceScopeRelationship,
        source_artifact_id: uuid.UUID | None = None,
        confidence: ScopeDiscoveryConfidence = ScopeDiscoveryConfidence.ASSERTED,
        applicability_is_explicit: bool = True,
        evidence_excerpt: str | None = None,
        evidence_start: int | None = None,
        evidence_end: int | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> CatalogueSourceScopeLink:
        existing = self.session.scalar(
            select(CatalogueSourceScopeLink).where(
                CatalogueSourceScopeLink.source_id == source_id,
                CatalogueSourceScopeLink.scope_node_id == scope_node_id,
                CatalogueSourceScopeLink.relationship_type == relationship_type,
                CatalogueSourceScopeLink.source_artifact_id == source_artifact_id,
            )
        )
        if existing is None:
            existing = CatalogueSourceScopeLink(
                candidate_id=candidate_id,
                source_id=source_id,
                source_artifact_id=source_artifact_id,
                scope_node_id=scope_node_id,
                relationship_type=relationship_type,
                confidence=confidence,
                applicability_is_explicit=applicability_is_explicit,
                evidence_excerpt=evidence_excerpt,
                evidence_start=evidence_start,
                evidence_end=evidence_end,
                provenance_json=dict(provenance or {}),
            )
            self.session.add(existing)
            self.session.flush()
            return existing
        existing.confidence = confidence
        existing.applicability_is_explicit = (
            existing.applicability_is_explicit or applicability_is_explicit
        )
        existing.evidence_excerpt = evidence_excerpt or existing.evidence_excerpt
        existing.evidence_start = evidence_start if evidence_start is not None else existing.evidence_start
        existing.evidence_end = evidence_end if evidence_end is not None else existing.evidence_end
        if provenance:
            merged = dict(existing.provenance_json or {})
            merged.update(provenance)
            existing.provenance_json = merged
        self.session.flush()
        return existing

    def set_expected_child_count(
        self,
        node_id: uuid.UUID,
        *,
        child_type: ScopeNodeType,
        expected_count: int,
        provenance: dict[str, Any],
    ) -> CatalogueScopeNode:
        return self._set_expectation(
            node_id,
            key=child_type.value,
            expected_count=expected_count,
            provenance=provenance,
        )

    def set_expected_objective_count(
        self,
        node_id: uuid.UUID,
        *,
        objective: ClaimObjective,
        expected_count: int,
        provenance: dict[str, Any],
    ) -> CatalogueScopeNode:
        return self._set_expectation(
            node_id,
            key=f"objective:{objective.value}",
            expected_count=expected_count,
            provenance=provenance,
        )

    def set_objective_applicability(
        self,
        node_id: uuid.UUID,
        *,
        objective: ClaimObjective,
        applicability: str,
        provenance: dict[str, Any],
    ) -> CatalogueScopeNode:
        if applicability not in {"required", "not_applicable"}:
            raise ValueError("applicability must be required or not_applicable")
        node = self.session.get(CatalogueScopeNode, node_id)
        if node is None:
            raise ValueError("scope node not found")
        node_provenance = dict(node.provenance_json or {})
        objective_applicability = dict(node_provenance.get("objective_applicability") or {})
        objective_applicability[objective.value] = applicability
        node_provenance["objective_applicability"] = objective_applicability
        evidence = dict(node_provenance.get("objective_applicability_provenance") or {})
        evidence[objective.value] = dict(provenance)
        node_provenance["objective_applicability_provenance"] = evidence
        node.provenance_json = node_provenance
        node.version += 1
        self.session.flush()
        return node

    def _set_expectation(
        self,
        node_id: uuid.UUID,
        *,
        key: str,
        expected_count: int,
        provenance: dict[str, Any],
    ) -> CatalogueScopeNode:
        if expected_count < 0:
            raise ValueError("expected count cannot be negative")
        node = self.session.get(CatalogueScopeNode, node_id)
        if node is None:
            raise ValueError("scope node not found")
        counts = dict(node.expected_child_counts or {})
        counts[key] = expected_count
        node.expected_child_counts = counts
        expectation_provenance = dict(node.expectation_provenance or {})
        expectation_provenance[key] = dict(provenance)
        node.expectation_provenance = expectation_provenance
        node.version += 1
        self.session.flush()
        return node
