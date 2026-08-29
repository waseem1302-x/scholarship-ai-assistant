"""Persistent scholarship topology, source applicability, and scoped coverage state."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import enum_values, utc_now
from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective, ScopedCoverageState


class ScopeNodeType(StrEnum):
    SCHOLARSHIP_FAMILY = "scholarship_family"
    CYCLE = "cycle"
    COUNTRY = "country"
    INSTITUTION = "institution"
    ROUTE = "route"
    PROGRAMME = "programme"
    DEGREE_LEVEL = "degree_level"
    SUBJECT = "subject"
    AWARD_VARIANT = "award_variant"
    APPLICATION_CHANNEL = "application_channel"


class ScopeEdgeType(StrEnum):
    CONTAINS = "contains"
    PARENT_CHILD = "parent_child"
    APPLIES_TO = "applies_to"
    INHERITS_TO = "inherits_to"


class SourceScopeRelationship(StrEnum):
    AUTHORITATIVE_FOR = "authoritative_for"
    SUPPORTS = "supports"
    ENUMERATES = "enumerates"
    APPLIES_TO = "applies_to"


class ScopeDiscoveryConfidence(StrEnum):
    ASSERTED = "asserted"
    HIGH = "high"
    MEDIUM = "medium"
    COMPATIBILITY = "compatibility"
    UNRESOLVED = "unresolved"


class CatalogueScopeNode(Base):
    __tablename__ = "catalogue_scope_nodes"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "node_type",
            "canonical_key",
            "lifecycle_key",
            name="uq_catalogue_scope_node_identity",
        ),
        Index(
            "ix_catalogue_scope_nodes_candidate_type",
            "candidate_id",
            "node_type",
            "canonical_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    node_type: Mapped[ScopeNodeType] = mapped_column(
        Enum(
            ScopeNodeType,
            name="catalogue_scope_node_type",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    canonical_key: Mapped[str] = mapped_column(String(255))
    display_label: Mapped[str] = mapped_column(String(255))
    lifecycle_key: Mapped[str] = mapped_column(String(120), default="", server_default="")
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidate_sources.id", ondelete="SET NULL"), index=True
    )
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_source_artifacts.id", ondelete="SET NULL"), index=True
    )
    discovery_confidence: Mapped[ScopeDiscoveryConfidence] = mapped_column(
        Enum(
            ScopeDiscoveryConfidence,
            name="catalogue_scope_discovery_confidence",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=ScopeDiscoveryConfidence.UNRESOLVED,
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expected_child_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    expectation_provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class CatalogueScopeEdge(Base):
    __tablename__ = "catalogue_scope_edges"
    __table_args__ = (
        CheckConstraint(
            "parent_node_id != child_node_id",
            name="ck_catalogue_scope_edges_not_self",
        ),
        UniqueConstraint(
            "candidate_id",
            "parent_node_id",
            "child_node_id",
            "relationship_type",
            name="uq_catalogue_scope_edge_identity",
        ),
        Index(
            "ix_catalogue_scope_edges_candidate_relationship",
            "candidate_id",
            "relationship_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    parent_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_scope_nodes.id", ondelete="CASCADE"), index=True
    )
    child_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_scope_nodes.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[ScopeEdgeType] = mapped_column(
        Enum(
            ScopeEdgeType,
            name="catalogue_scope_edge_type",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    objective_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_source_artifacts.id", ondelete="SET NULL"), index=True
    )
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)
    evidence_start: Mapped[int | None] = mapped_column(Integer)
    evidence_end: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[ScopeDiscoveryConfidence] = mapped_column(
        Enum(
            ScopeDiscoveryConfidence,
            name="catalogue_scope_edge_confidence",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=ScopeDiscoveryConfidence.UNRESOLVED,
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )


class CatalogueSourceScopeLink(Base):
    __tablename__ = "catalogue_source_scope_links"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "scope_node_id",
            "relationship_type",
            "source_artifact_id",
            name="uq_catalogue_source_scope_link_identity",
        ),
        Index(
            "ix_catalogue_source_scope_links_candidate_scope",
            "candidate_id",
            "scope_node_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidate_sources.id", ondelete="CASCADE"), index=True
    )
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_source_artifacts.id", ondelete="SET NULL"), index=True
    )
    scope_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_scope_nodes.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[SourceScopeRelationship] = mapped_column(
        Enum(
            SourceScopeRelationship,
            name="catalogue_source_scope_relationship",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    confidence: Mapped[ScopeDiscoveryConfidence] = mapped_column(
        Enum(
            ScopeDiscoveryConfidence,
            name="catalogue_source_scope_confidence",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=ScopeDiscoveryConfidence.UNRESOLVED,
    )
    applicability_is_explicit: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)
    evidence_start: Mapped[int | None] = mapped_column(Integer)
    evidence_end: Mapped[int | None] = mapped_column(Integer)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )


class CatalogueCoverageCell(Base):
    __tablename__ = "catalogue_coverage_cells"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "objective",
            "scope_node_id",
            name="uq_catalogue_coverage_cell_identity",
        ),
        Index(
            "ix_catalogue_coverage_cells_candidate_state",
            "candidate_id",
            "state",
            "objective",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    objective: Mapped[ClaimObjective] = mapped_column(
        Enum(
            ClaimObjective,
            name="catalogue_coverage_objective",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    scope_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_scope_nodes.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[ScopedCoverageState] = mapped_column(
        Enum(
            ScopedCoverageState,
            name="catalogue_scoped_coverage_state",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=ScopedCoverageState.UNKNOWN,
        index=True,
    )
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    supporting_claim_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    supporting_evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_item_count: Mapped[int | None] = mapped_column(Integer)
    resolved_item_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reason: Mapped[str] = mapped_column(String(500))
    missing_frontier_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    evaluator_version: Mapped[str] = mapped_column(String(100))
    input_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )


def _proof_record_is_trusted(value: object) -> bool:
    return isinstance(value, dict) and bool(
        value.get("source_artifact_id")
        or value.get("reviewed") is True
        or value.get("asserted_candidate_seed") is True
        or value.get("asserted") is True
    )


@event.listens_for(CatalogueScopeNode, "before_insert", propagate=True)
@event.listens_for(CatalogueScopeNode, "before_update", propagate=True)
def _validate_scope_node_proofs(*args: object) -> None:
    target = args[-1]
    if not isinstance(target, CatalogueScopeNode):
        return
    expected = dict(target.expected_child_counts or {})
    provenance = dict(target.expectation_provenance or {})
    for key, raw_count in expected.items():
        try:
            count = int(raw_count)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid topology expected count for {key}") from exc
        if count < 0:
            raise ValueError(f"negative topology expected count for {key}")
        if not _proof_record_is_trusted(provenance.get(key)):
            raise ValueError(f"topology expected count lacks trusted provenance for {key}")

    node_provenance = dict(target.provenance_json or {})
    applicability = node_provenance.get("objective_applicability", {})
    if not applicability:
        return
    if not isinstance(applicability, dict):
        raise ValueError("objective_applicability must be an object")
    evidence = node_provenance.get("objective_applicability_evidence", {})
    if not isinstance(evidence, dict):
        raise ValueError("objective_applicability_evidence must be an object")
    valid_objectives = {objective.value for objective in ClaimObjective}
    for objective, state in applicability.items():
        if objective not in valid_objectives:
            raise ValueError(f"unknown objective applicability key: {objective}")
        if state not in {"applies", "not_applicable"}:
            raise ValueError(f"invalid objective applicability state: {state}")
        if not _proof_record_is_trusted(evidence.get(objective)):
            raise ValueError(f"objective applicability lacks trusted provenance for {objective}")


@event.listens_for(CatalogueScopeEdge, "before_insert", propagate=True)
@event.listens_for(CatalogueScopeEdge, "before_update", propagate=True)
def _validate_scope_edge_objectives(*args: object) -> None:
    target = args[-1]
    if not isinstance(target, CatalogueScopeEdge):
        return
    provenance = dict(target.provenance_json or {})
    legacy_objectives = provenance.get("objectives")
    keys = set(target.objective_keys or [])
    if isinstance(legacy_objectives, list):
        keys.update(str(value) for value in legacy_objectives)
    valid_objectives = {objective.value for objective in ClaimObjective}
    invalid = sorted(keys - valid_objectives - {"*"})
    if invalid:
        raise ValueError(f"unknown topology edge objectives: {','.join(invalid)}")
    target.objective_keys = sorted(keys)
    provenance["objectives"] = list(target.objective_keys)
    target.provenance_json = provenance

    if target.relationship_type is not ScopeEdgeType.INHERITS_TO:
        return
    if not target.objective_keys:
        raise ValueError("inherits_to edges require explicit objective keys")
    if target.confidence is ScopeDiscoveryConfidence.UNRESOLVED:
        raise ValueError("inherits_to edges require resolved confidence")
    if not (
        target.source_artifact_id is not None
        or provenance.get("reviewed") is True
        or provenance.get("asserted") is True
    ):
        raise ValueError("inherits_to edges require evidence or reviewed provenance")


@event.listens_for(CatalogueSourceScopeLink, "before_insert", propagate=True)
@event.listens_for(CatalogueSourceScopeLink, "before_update", propagate=True)
def _validate_explicit_source_scope_link(*args: object) -> None:
    target = args[-1]
    if not isinstance(target, CatalogueSourceScopeLink) or not target.applicability_is_explicit:
        return
    provenance = dict(target.provenance_json or {})
    if target.source_artifact_id is not None or provenance.get("source_role"):
        return
    if provenance.get("reviewed") is True or provenance.get("asserted") is True:
        return
    raise ValueError("explicit source-scope applicability requires evidence or reviewed provenance")
