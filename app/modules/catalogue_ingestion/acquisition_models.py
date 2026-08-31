"""Append-only acquisition plan and budget snapshots for catalogue candidates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import utc_now

ACQUISITION_SNAPSHOT_REVISION = "catalogue-acquisition.v1"


class CatalogueAcquisitionSnapshot(Base):
    __tablename__ = "catalogue_acquisition_snapshots"
    __table_args__ = (
        Index(
            "ix_catalogue_acquisition_snapshots_candidate_created",
            "candidate_id",
            "created_at",
        ),
        Index(
            "ix_catalogue_acquisition_snapshots_run_created",
            "run_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_ingestion_runs.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[str] = mapped_column(
        String(100),
        default=ACQUISITION_SNAPSHOT_REVISION,
        server_default=ACQUISITION_SNAPSHOT_REVISION,
    )
    coverage_revision: Mapped[str | None] = mapped_column(String(100))
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    budget_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


@event.listens_for(CatalogueAcquisitionSnapshot, "before_update", propagate=True)
def _prevent_acquisition_snapshot_update(*_: object) -> None:
    raise RuntimeError("catalogue acquisition snapshots are append-only")


@event.listens_for(CatalogueAcquisitionSnapshot, "before_delete", propagate=True)
def _prevent_acquisition_snapshot_delete(*_: object) -> None:
    raise RuntimeError("catalogue acquisition snapshots cannot be deleted")


__all__ = ["ACQUISITION_SNAPSHOT_REVISION", "CatalogueAcquisitionSnapshot"]
