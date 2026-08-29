"""Transactional helpers for reviewed or deterministic topology declarations."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective
from app.modules.catalogue_ingestion.models import (
    CatalogueCandidateSource,
    CatalogueSourceArtifact,
)
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
    """Persist explicit topology without committing the caller's transaction.

    This is the write boundary for reviewed/evidenced topology. Expected counts, explicit
    applicability, inheritance, and source-scope relationships fail closed unless their evidence
    belongs to the same candidate or the caller records an explicit reviewed/asserted decision.
    """

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
        if source_id is not None:
            self._require_candidate_source(candidate_id, source_id)
        if source_artifact_id is not None:
            artifact = self._require_candidate_artifact(candidate_id, source_artifact_id)
            if source_id is not None and artifact.source_id != source_id:
                raise ValueError("scope source artifact does not belong to source_id")

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
        self._require_scope(candidate_id, parent_node_id)
        self._require_scope(candidate_id, child_node_id)
        if source_artifact_id is not None:
            self._require_candidate_artifact(candidate_id, source_artifact_id)
        self._validate_evidence_span(evidence_start, evidence_end)

        objective_keys = self._objective_keys(objectives)
        merged_provenance = dict(provenance or {})
        if objective_keys:
            merged_provenance["objectives"] = objective_keys
        if relationship_type is ScopeEdgeType.INHERITS_TO:
            if not objective_keys:
                raise ValueError("inheritance requires at least one explicit objective")
            if confidence is ScopeDiscoveryConfidence.UNRESOLVED:
                raise ValueError("inheritance requires resolved confidence")
            if source_artifact_id is None and not self._has_manual_proof(merged_provenance):
                raise ValueError("inheritance requires source evidence or reviewed provenance")

        existing = self.session.scalar(
            select(CatalogueScopeEdge).where(
                CatalogueScopeEdge.candidate_id == candidate_id,
                CatalogueScopeEdge.parent_node_id == parent_node_id,
                CatalogueScopeEdge.child_node_id == child_node_id,
                CatalogueScopeEdge.relationship_type == relationship_type,
            )
        )
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
        existing.evidence_start = (
            evidence_start if evidence_start is not None else existing.evidence_start
        )
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
        confidence: ScopeDiscoveryConfidence = ScopeDiscoveryConfidence.ASSERTED,
        provenance: dict[str, Any] | None = None,
    ) -> CatalogueScopeEdge:
        return self.declare_edge(
            candidate_id=candidate_id,
            parent_node_id=parent_node_id,
            child_node_id=child_node_id,
            relationship_type=ScopeEdgeType.INHERITS_TO,
            objectives=objectives,
            source_artifact_id=source_artifact_id,
            evidence_excerpt=evidence_excerpt,
            evidence_start=evidence_start,
            evidence_end=evidence_end,
            confidence=confidence,
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
        self._require_candidate_source(candidate_id, source_id)
        self._require_scope(candidate_id, scope_node_id)
        if source_artifact_id is not None:
            artifact = self._require_candidate_artifact(candidate_id, source_artifact_id)
            if artifact.source_id != source_id:
                raise ValueError("source-scope artifact does not belong to source_id")
        self._validate_evidence_span(evidence_start, evidence_end)
        provenance_json = dict(provenance or {})
        if (
            applicability_is_explicit
            and source_artifact_id is None
            and not provenance_json.get("source_role")
            and not self._has_manual_proof(provenance_json)
        ):
            raise ValueError(
                "explicit source-scope applicability requires evidence or reviewed provenance"
            )

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
                provenance_json=provenance_json,
            )
            self.session.add(existing)
            self.session.flush()
            return existing

        existing.confidence = confidence
        existing.applicability_is_explicit = (
            existing.applicability_is_explicit or applicability_is_explicit
        )
        existing.evidence_excerpt = evidence_excerpt or existing.evidence_excerpt
        existing.evidence_start = (
            evidence_start if evidence_start is not None else existing.evidence_start
        )
        existing.evidence_end = evidence_end if evidence_end is not None else existing.evidence_end
        if provenance_json:
            merged = dict(existing.provenance_json or {})
            merged.update(provenance_json)
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
        # ``required`` is the pre-v4 compatibility spelling. Persist only the v4 typed state.
        normalized = "applies" if applicability == "required" else applicability
        if normalized not in {"applies", "not_applicable"}:
            raise ValueError("applicability must be applies, required, or not_applicable")
        node = self._require_scope_by_id(node_id)
        proof = self._validated_proof(node.candidate_id, provenance)
        node_provenance = dict(node.provenance_json or {})
        objective_applicability = dict(node_provenance.get("objective_applicability") or {})
        objective_applicability[objective.value] = normalized
        evidence = dict(node_provenance.get("objective_applicability_evidence") or {})
        evidence[objective.value] = proof
        node_provenance["objective_applicability"] = objective_applicability
        node_provenance["objective_applicability_evidence"] = evidence
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
        node = self._require_scope_by_id(node_id)
        proof = self._validated_proof(node.candidate_id, provenance)
        counts = dict(node.expected_child_counts or {})
        counts[key] = expected_count
        expectation_provenance = dict(node.expectation_provenance or {})
        expectation_provenance[key] = proof
        node.expected_child_counts = counts
        node.expectation_provenance = expectation_provenance
        node.version += 1
        self.session.flush()
        return node

    def _validated_proof(
        self,
        candidate_id: uuid.UUID,
        provenance: dict[str, Any],
    ) -> dict[str, Any]:
        proof = dict(provenance)
        raw_artifact_id = proof.get("source_artifact_id")
        artifact_id: uuid.UUID | None = None
        if raw_artifact_id:
            try:
                artifact_id = uuid.UUID(str(raw_artifact_id))
            except (TypeError, ValueError) as exc:
                raise ValueError("source_artifact_id must be a UUID") from exc
            self._require_candidate_artifact(candidate_id, artifact_id)
            proof["source_artifact_id"] = str(artifact_id)
        if artifact_id is None and not self._has_manual_proof(proof):
            raise ValueError("topology assertion requires source evidence or reviewed provenance")
        self._validate_evidence_span(
            self._optional_int(proof.get("evidence_start"), "evidence_start"),
            self._optional_int(proof.get("evidence_end"), "evidence_end"),
        )
        return proof

    def _require_scope(
        self,
        candidate_id: uuid.UUID,
        node_id: uuid.UUID,
    ) -> CatalogueScopeNode:
        node = self.session.scalar(
            select(CatalogueScopeNode).where(
                CatalogueScopeNode.id == node_id,
                CatalogueScopeNode.candidate_id == candidate_id,
            )
        )
        if node is None:
            raise ValueError("scope node not found for candidate")
        return node

    def _require_scope_by_id(self, node_id: uuid.UUID) -> CatalogueScopeNode:
        node = self.session.get(CatalogueScopeNode, node_id)
        if node is None:
            raise ValueError("scope node not found")
        return node

    def _require_candidate_source(
        self,
        candidate_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> CatalogueCandidateSource:
        source = self.session.scalar(
            select(CatalogueCandidateSource).where(
                CatalogueCandidateSource.id == source_id,
                CatalogueCandidateSource.candidate_id == candidate_id,
            )
        )
        if source is None:
            raise ValueError("candidate source not found")
        return source

    def _require_candidate_artifact(
        self,
        candidate_id: uuid.UUID,
        artifact_id: uuid.UUID,
    ) -> CatalogueSourceArtifact:
        artifact = self.session.scalar(
            select(CatalogueSourceArtifact)
            .join(
                CatalogueCandidateSource,
                CatalogueCandidateSource.id == CatalogueSourceArtifact.source_id,
            )
            .where(
                CatalogueSourceArtifact.id == artifact_id,
                CatalogueCandidateSource.candidate_id == candidate_id,
            )
        )
        if artifact is None:
            raise ValueError("source artifact not found for candidate")
        return artifact

    @staticmethod
    def _objective_keys(objectives: Iterable[ClaimObjective | str]) -> list[str]:
        valid = {objective.value for objective in ClaimObjective}
        values = {
            item.value if isinstance(item, ClaimObjective) else str(item)
            for item in objectives
        }
        invalid = sorted(values - valid - {"*"})
        if invalid:
            raise ValueError(f"unknown topology objectives: {','.join(invalid)}")
        return sorted(values)

    @staticmethod
    def _has_manual_proof(provenance: dict[str, Any]) -> bool:
        return provenance.get("reviewed") is True or provenance.get("asserted") is True

    @staticmethod
    def _optional_int(value: object, field_name: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be an integer")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an integer") from exc

    @staticmethod
    def _validate_evidence_span(start: int | None, end: int | None) -> None:
        if (start is None) != (end is None):
            raise ValueError("evidence spans require both start and end")
        if start is not None and end is not None and (start < 0 or end <= start):
            raise ValueError("evidence span is invalid")
