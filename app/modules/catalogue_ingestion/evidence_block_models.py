"""Immutable complete-document evidence blocks and deterministic routing decisions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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
from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective

EVIDENCE_BLOCK_BUILDER_VERSION = "catalogue-evidence-blocks.v2"
EVIDENCE_ROUTER_VERSION = "catalogue-evidence-router.v2"


class CatalogueEvidenceBlock(Base):
    """Append-only exact span over one immutable source artifact."""

    __tablename__ = "catalogue_evidence_blocks"
    __table_args__ = (
        UniqueConstraint(
            "source_artifact_id",
            "builder_version",
            "block_index",
            name="uq_catalogue_evidence_block_position",
        ),
        UniqueConstraint("block_key", name="uq_catalogue_evidence_block_key"),
        Index(
            "ix_catalogue_evidence_blocks_candidate_artifact",
            "candidate_id",
            "source_artifact_id",
            "block_index",
        ),
        Index(
            "ix_catalogue_evidence_blocks_content_hash",
            "source_content_hash",
            "block_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidate_sources.id", ondelete="CASCADE"), index=True
    )
    source_artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_source_artifacts.id", ondelete="RESTRICT"), index=True
    )
    block_index: Mapped[int] = mapped_column(Integer)
    block_key: Mapped[str] = mapped_column(String(64), index=True)
    block_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_content_hash: Mapped[str] = mapped_column(String(64), index=True)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    block_text: Mapped[str] = mapped_column(Text)
    heading: Mapped[str | None] = mapped_column(String(500))
    section_key: Mapped[str | None] = mapped_column(String(255))
    coordinate_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    topology_hints: Mapped[list[str]] = mapped_column(JSON, default=list)
    language_hints: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_role: Mapped[str] = mapped_column(String(32))
    builder_version: Mapped[str] = mapped_column(
        String(100), default=EVIDENCE_BLOCK_BUILDER_VERSION
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class CatalogueEvidenceRoute(Base):
    """Append-only block x topology-scope x objective relevance decision."""

    __tablename__ = "catalogue_evidence_routes"
    __table_args__ = (
        UniqueConstraint("route_key", name="uq_catalogue_evidence_route_key"),
        Index(
            "ix_catalogue_evidence_routes_candidate_selected",
            "candidate_id",
            "selected",
            "objective",
        ),
        Index(
            "ix_catalogue_evidence_routes_block_scope",
            "evidence_block_id",
            "scope_node_id",
            "objective",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    route_key: Mapped[str] = mapped_column(String(64), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    evidence_block_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_evidence_blocks.id", ondelete="RESTRICT"), index=True
    )
    coverage_cell_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_coverage_cells.id", ondelete="SET NULL"), index=True
    )
    scope_node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_scope_nodes.id", ondelete="SET NULL"), index=True
    )
    objective: Mapped[ClaimObjective] = mapped_column(
        Enum(
            ClaimObjective,
            name="catalogue_evidence_route_objective",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    scope_type: Mapped[str] = mapped_column(String(64))
    scope_key: Mapped[str] = mapped_column(String(255))
    relevance_score: Mapped[int] = mapped_column(Integer)
    relevance_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    router_version: Mapped[str] = mapped_column(String(100), default=EVIDENCE_ROUTER_VERSION)
    coverage_input_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


def _immutable_record(kind: str) -> None:
    raise RuntimeError(f"{kind} records are append-only; create a new version")


@event.listens_for(CatalogueEvidenceBlock, "before_update", propagate=True)
def _prevent_evidence_block_update(*_: object) -> None:
    _immutable_record("catalogue evidence block")


@event.listens_for(CatalogueEvidenceBlock, "before_delete", propagate=True)
def _prevent_evidence_block_delete(*_: object) -> None:
    _immutable_record("catalogue evidence block")


@event.listens_for(CatalogueEvidenceRoute, "before_update", propagate=True)
def _prevent_evidence_route_update(*_: object) -> None:
    _immutable_record("catalogue evidence route")


@event.listens_for(CatalogueEvidenceRoute, "before_delete", propagate=True)
def _prevent_evidence_route_delete(*_: object) -> None:
    _immutable_record("catalogue evidence route")


__all__ = [
    "EVIDENCE_BLOCK_BUILDER_VERSION",
    "EVIDENCE_ROUTER_VERSION",
    "CatalogueEvidenceBlock",
    "CatalogueEvidenceRoute",
]
