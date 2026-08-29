"""Content-addressed extraction cache entries and append-only cache decision ledger."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import utc_now

EXTRACTION_CACHE_VERSION = "catalogue-extraction-cache.v1"


class ExtractionCacheDecision(StrEnum):
    HIT = "hit"
    MISS = "miss"
    INVALIDATED = "invalidated"
    QUARANTINED = "quarantined"


class CatalogueExtractionCacheEntry(Base):
    """One reusable validated structured extraction result.

    Only successful, reusable results belong here. Failures and quarantined outputs remain visible
    through the provider/extraction ledgers and cache-event ledger and therefore cannot poison a
    valid cache key.
    """

    __tablename__ = "catalogue_extraction_cache_entries"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_catalogue_extraction_cache_key"),
        Index(
            "ix_catalogue_extraction_cache_content_authority",
            "normalized_content_hash",
            "authority_context_hash",
        ),
        Index(
            "ix_catalogue_extraction_cache_versions",
            "prompt_hash",
            "schema_version",
            "parser_version",
            "normalizer_version",
            "resolver_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    origin_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="SET NULL"), index=True
    )
    origin_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidate_sources.id", ondelete="SET NULL"), index=True
    )
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_source_artifacts.id", ondelete="SET NULL"), index=True
    )
    normalized_content_hash: Mapped[str] = mapped_column(String(64), index=True)
    authority_context_hash: Mapped[str] = mapped_column(String(64), index=True)
    evidence_block_set_hash: Mapped[str] = mapped_column(String(64), index=True)
    evidence_block_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    scope_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    objective_bundle: Mapped[list[str]] = mapped_column(JSON, default=list)
    objective_bundle_hash: Mapped[str] = mapped_column(String(64), index=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[str] = mapped_column(String(100), index=True)
    parser_version: Mapped[str] = mapped_column(String(100))
    normalizer_version: Mapped[str] = mapped_column(String(100))
    resolver_version: Mapped[str] = mapped_column(String(100))
    validator_version: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(100), index=True)
    model: Mapped[str] = mapped_column(String(255))
    capability_identity_hash: Mapped[str] = mapped_column(String(64), index=True)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    cache_version: Mapped[str] = mapped_column(String(100), default=EXTRACTION_CACHE_VERSION)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class CatalogueExtractionCacheEvent(Base):
    """Append-only hit/miss/invalidation/quarantine explanation."""

    __tablename__ = "catalogue_extraction_cache_events"
    __table_args__ = (
        Index(
            "ix_catalogue_extraction_cache_events_candidate_decision",
            "candidate_id",
            "decision",
            "created_at",
        ),
        Index(
            "ix_catalogue_extraction_cache_events_key_created",
            "cache_key",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_ingestion_runs.id", ondelete="SET NULL"), index=True
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="SET NULL"), index=True
    )
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_source_artifacts.id", ondelete="SET NULL"), index=True
    )
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(100))
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


def _append_only(kind: str) -> None:
    raise RuntimeError(f"{kind} records are append-only; create a new record")


@event.listens_for(CatalogueExtractionCacheEntry, "before_update", propagate=True)
def _prevent_cache_entry_update(*_: object) -> None:
    _append_only("catalogue extraction cache entry")


@event.listens_for(CatalogueExtractionCacheEntry, "before_delete", propagate=True)
def _prevent_cache_entry_delete(*_: object) -> None:
    _append_only("catalogue extraction cache entry")


@event.listens_for(CatalogueExtractionCacheEvent, "before_update", propagate=True)
def _prevent_cache_event_update(*_: object) -> None:
    _append_only("catalogue extraction cache event")


@event.listens_for(CatalogueExtractionCacheEvent, "before_delete", propagate=True)
def _prevent_cache_event_delete(*_: object) -> None:
    _append_only("catalogue extraction cache event")


__all__ = [
    "EXTRACTION_CACHE_VERSION",
    "CatalogueExtractionCacheEntry",
    "CatalogueExtractionCacheEvent",
    "ExtractionCacheDecision",
]
