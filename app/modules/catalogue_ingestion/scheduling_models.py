"""Persistent provider lanes, circuit breakers, and scheduling decisions."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import enum_values, utc_now
from app.modules.catalogue_ingestion.provider_attempts import ProviderFailureClass


class ProviderCircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class SchedulingDecisionKind(StrEnum):
    DISPATCH_ALLOWED = "dispatch_allowed"
    CIRCUIT_OPEN = "circuit_open"
    CONCURRENCY_LIMIT = "concurrency_limit"
    KILL_SWITCH = "kill_switch"


class CatalogueProviderLane(Base):
    __tablename__ = "catalogue_provider_lanes"
    __table_args__ = (
        UniqueConstraint("provider", "deployment", name="uq_catalogue_provider_lane"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(100), index=True)
    deployment: Mapped[str] = mapped_column(String(255), default="")
    last_admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )


class CatalogueProviderCircuit(Base):
    __tablename__ = "catalogue_provider_circuits"
    __table_args__ = (
        UniqueConstraint(
            "lane_id",
            "failure_class",
            name="uq_catalogue_provider_circuit_failure_class",
        ),
        Index("ix_catalogue_provider_circuits_state_until", "state", "opened_until"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lane_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_provider_lanes.id", ondelete="CASCADE"), index=True
    )
    failure_class: Mapped[ProviderFailureClass] = mapped_column(
        Enum(
            ProviderFailureClass,
            name="catalogue_provider_circuit_failure_class",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    state: Mapped[ProviderCircuitState] = mapped_column(
        Enum(
            ProviderCircuitState,
            name="catalogue_provider_circuit_state",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=ProviderCircuitState.CLOSED,
        index=True,
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    opened_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )


class CatalogueSchedulingDecision(Base):
    __tablename__ = "catalogue_scheduling_decisions"
    __table_args__ = (
        Index("ix_catalogue_scheduling_decisions_run_created", "run_id", "created_at"),
        Index("ix_catalogue_scheduling_decisions_candidate_created", "candidate_id", "created_at"),
        Index(
            "ix_catalogue_scheduling_decisions_lane_created",
            "provider",
            "deployment",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_ingestion_runs.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    logical_job_key: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(100))
    deployment: Mapped[str] = mapped_column(String(255), default="")
    decision: Mapped[SchedulingDecisionKind] = mapped_column(
        Enum(
            SchedulingDecisionKind,
            name="catalogue_scheduling_decision_kind",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    reason: Mapped[str] = mapped_column(String(100))
    active_attempts: Mapped[int] = mapped_column(Integer, default=0)
    concurrency_limit: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


def _reject_decision_mutation(_mapper: object, _connection: object, target: object) -> None:
    raise ValueError(f"{type(target).__name__} is immutable scheduling provenance")


event.listen(CatalogueSchedulingDecision, "before_update", _reject_decision_mutation)
event.listen(CatalogueSchedulingDecision, "before_delete", _reject_decision_mutation)
