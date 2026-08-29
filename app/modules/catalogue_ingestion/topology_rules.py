"""Typed writers for reviewed/evidenced topology expectations and applicability."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueScopeEdge,
    CatalogueScopeNode,
    ScopeDiscoveryConfidence,
    ScopeEdgeType,
    ScopeNodeType,
)


def record_expected_child_count(
    node: CatalogueScopeNode,
    *,
    child_type: ScopeNodeType,
    expected_count: int,
    source_artifact_id: uuid.UUID | None = None,
    evidence_start: int | None = None,
    evidence_end: int | None = None,
    reviewed: bool = False,
    reason: str | None = None,
) -> None:
    """Persist an evidenced expected number of direct topology children."""

    _record_expected_count(
        node,
        key=child_type.value,
        expected_count=expected_count,
        source_artifact_id=source_artifact_id,
        evidence_start=evidence_start,
        evidence_end=evidence_end,
        reviewed=reviewed,
        reason=reason,
    )


def record_expected_objective_items(
    node: CatalogueScopeNode,
    *,
    objective: ClaimObjective,
    expected_count: int,
    source_artifact_id: uuid.UUID | None = None,
    evidence_start: int | None = None,
    evidence_end: int | None = None,
    reviewed: bool = False,
    reason: str | None = None,
) -> None:
    """Persist an evidenced finite item count used to close one objective at one scope."""

    _record_expected_count(
        node,
        key=f"objective:{objective.value}",
        expected_count=expected_count,
        source_artifact_id=source_artifact_id,
        evidence_start=evidence_start,
        evidence_end=evidence_end,
        reviewed=reviewed,
        reason=reason,
    )


def record_objective_applicability(
    node: CatalogueScopeNode,
    *,
    objective: ClaimObjective,
    applies: bool,
    source_artifact_id: uuid.UUID | None = None,
    evidence_start: int | None = None,
    evidence_end: int | None = None,
    reviewed: bool = False,
    reason: str | None = None,
) -> None:
    """Record explicit scope applicability; provider self-report is not accepted here."""

    proof = _proof_record(
        source_artifact_id=source_artifact_id,
        evidence_start=evidence_start,
        evidence_end=evidence_end,
        reviewed=reviewed,
        reason=reason,
    )
    provenance = dict(node.provenance_json or {})
    applicability = dict(provenance.get("objective_applicability") or {})
    evidence = dict(provenance.get("objective_applicability_evidence") or {})
    applicability[objective.value] = "applies" if applies else "not_applicable"
    evidence[objective.value] = proof
    provenance["objective_applicability"] = applicability
    provenance["objective_applicability_evidence"] = evidence
    node.provenance_json = provenance


def upsert_inheritance_edge(
    session: Session,
    *,
    parent: CatalogueScopeNode,
    child: CatalogueScopeNode,
    objectives: Iterable[ClaimObjective],
    source_artifact_id: uuid.UUID | None = None,
    evidence_excerpt: str | None = None,
    evidence_start: int | None = None,
    evidence_end: int | None = None,
    reviewed: bool = False,
    reason: str | None = None,
    confidence: ScopeDiscoveryConfidence = ScopeDiscoveryConfidence.HIGH,
) -> CatalogueScopeEdge:
    """Create or update a directional, objective-scoped inheritance relationship."""

    if parent.candidate_id != child.candidate_id:
        raise ValueError("topology inheritance cannot cross candidates")
    if parent.id == child.id:
        raise ValueError("topology inheritance cannot target the same node")
    objective_keys = sorted({objective.value for objective in objectives})
    if not objective_keys:
        raise ValueError("topology inheritance requires at least one objective")
    if source_artifact_id is None and not reviewed:
        raise ValueError("topology inheritance requires source evidence or explicit review")

    edge = session.scalar(
        select(CatalogueScopeEdge).where(
            CatalogueScopeEdge.candidate_id == parent.candidate_id,
            CatalogueScopeEdge.parent_node_id == parent.id,
            CatalogueScopeEdge.child_node_id == child.id,
            CatalogueScopeEdge.relationship_type == ScopeEdgeType.INHERITS_TO,
        )
    )
    provenance = {
        "objectives": objective_keys,
        "reviewed": reviewed,
        "reason": reason,
    }
    if edge is None:
        edge = CatalogueScopeEdge(
            candidate_id=parent.candidate_id,
            parent_node_id=parent.id,
            child_node_id=child.id,
            relationship_type=ScopeEdgeType.INHERITS_TO,
            objective_keys=objective_keys,
            source_artifact_id=source_artifact_id,
            evidence_excerpt=evidence_excerpt,
            evidence_start=evidence_start,
            evidence_end=evidence_end,
            confidence=confidence,
            provenance_json=provenance,
        )
        session.add(edge)
        return edge

    edge.objective_keys = objective_keys
    edge.source_artifact_id = source_artifact_id
    edge.evidence_excerpt = evidence_excerpt
    edge.evidence_start = evidence_start
    edge.evidence_end = evidence_end
    edge.confidence = confidence
    edge.provenance_json = provenance
    return edge


def _record_expected_count(
    node: CatalogueScopeNode,
    *,
    key: str,
    expected_count: int,
    source_artifact_id: uuid.UUID | None,
    evidence_start: int | None,
    evidence_end: int | None,
    reviewed: bool,
    reason: str | None,
) -> None:
    if expected_count < 0:
        raise ValueError("expected topology counts cannot be negative")
    proof = _proof_record(
        source_artifact_id=source_artifact_id,
        evidence_start=evidence_start,
        evidence_end=evidence_end,
        reviewed=reviewed,
        reason=reason,
    )
    counts = dict(node.expected_child_counts or {})
    provenance = dict(node.expectation_provenance or {})
    counts[key] = expected_count
    provenance[key] = proof
    node.expected_child_counts = counts
    node.expectation_provenance = provenance


def _proof_record(
    *,
    source_artifact_id: uuid.UUID | None,
    evidence_start: int | None,
    evidence_end: int | None,
    reviewed: bool,
    reason: str | None,
) -> dict[str, object]:
    if source_artifact_id is None and not reviewed:
        raise ValueError("topology assertions require source evidence or explicit review")
    if (evidence_start is None) != (evidence_end is None):
        raise ValueError("topology evidence spans require both start and end")
    if evidence_start is not None and evidence_end is not None:
        if evidence_start < 0 or evidence_end <= evidence_start:
            raise ValueError("topology evidence span is invalid")
    return {
        "source_artifact_id": str(source_artifact_id) if source_artifact_id is not None else None,
        "evidence_start": evidence_start,
        "evidence_end": evidence_end,
        "reviewed": reviewed,
        "reason": reason,
    }
