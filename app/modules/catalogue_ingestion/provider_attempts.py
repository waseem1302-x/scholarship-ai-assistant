"""Provider-attempt accounting records for paid catalogue extraction.

One row represents one orchestration-owned outbound attempt. Parsed extraction results remain in
``catalogue_extraction_attempts`` so retries, transport failures, accounting uncertainty, and
schema/normalizer revisions do not overwrite one another.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import enum_values, utc_now


class ProviderAttemptState(StrEnum):
    RESERVED = "reserved"
    DISPATCHING = "dispatching"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProviderFailureClass(StrEnum):
    PRE_DISPATCH_FAILURE = "pre_dispatch_failure"
    CONNECTION_ESTABLISHMENT_FAILURE = "connection_establishment_failure"
    POST_DISPATCH_RESPONSE_INTERRUPTION = "post_dispatch_response_interruption"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    PROVIDER_SERVER_ERROR = "provider_server_error"
    AUTHENTICATION_CONFIGURATION_ERROR = "authentication_configuration_error"
    MALFORMED_PROVIDER_RESPONSE = "malformed_provider_response"
    SCHEMA_VALIDATION_FAILURE = "schema_validation_failure"
    SAFETY_REFUSAL = "safety_refusal"
    BUDGET_REJECTION = "budget_rejection"
    LEASE_LOSS = "lease_loss"
    CANCELLED_BY_KILL_SWITCH = "cancelled_by_kill_switch"
    UNKNOWN_POTENTIALLY_BILLABLE_FAILURE = "unknown_potentially_billable_failure"


class ProviderAccountingState(StrEnum):
    NOT_BILLABLE = "not_billable"
    EXACT = "exact"
    ESTIMATED = "estimated"
    UNKNOWN_POTENTIALLY_BILLABLE = "unknown_potentially_billable"


class CatalogueProviderAttempt(Base):
    """Durable identity and accounting lifecycle for exactly one outbound attempt."""

    __tablename__ = "catalogue_provider_attempts"
    __table_args__ = (
        UniqueConstraint(
            "extraction_job_key",
            "retry_ordinal",
            name="uq_catalogue_provider_attempt_job_retry",
        ),
        Index("ix_catalogue_provider_attempts_run_state", "run_id", "state", "created_at"),
        Index(
            "ix_catalogue_provider_attempts_candidate_state",
            "candidate_id",
            "state",
            "created_at",
        ),
        Index(
            "ix_catalogue_provider_attempts_candidate_objective",
            "candidate_id",
            "objective",
            "created_at",
        ),
        Index(
            "ix_catalogue_provider_attempts_artifact",
            "source_artifact_id",
            "created_at",
        ),
        Index(
            "ix_catalogue_provider_attempts_accounting",
            "accounting_state",
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
    extraction_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_extraction_attempts.id", ondelete="SET NULL"), index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidate_sources.id", ondelete="SET NULL"), index=True
    )
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_source_artifacts.id", ondelete="RESTRICT"), index=True
    )
    extraction_job_key: Mapped[str] = mapped_column(String(128), index=True)
    objective: Mapped[str | None] = mapped_column(String(100), index=True)
    objective_bundle: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_block_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    provider: Mapped[str] = mapped_column(String(100))
    deployment: Mapped[str | None] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(255))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(100))
    parser_version: Mapped[str] = mapped_column(String(100))
    normalizer_version: Mapped[str] = mapped_column(String(100))
    retry_ordinal: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str | None] = mapped_column(String(100))
    lease_token: Mapped[str | None] = mapped_column(String(100))
    provider_request_id: Mapped[str | None] = mapped_column(String(255), index=True)
    state: Mapped[ProviderAttemptState] = mapped_column(
        Enum(
            ProviderAttemptState,
            name="catalogue_provider_attempt_state",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=ProviderAttemptState.RESERVED,
        index=True,
    )
    failure_class: Mapped[ProviderFailureClass | None] = mapped_column(
        Enum(
            ProviderFailureClass,
            name="catalogue_provider_failure_class",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(100))
    safe_error_detail: Mapped[str | None] = mapped_column(Text)
    accounting_state: Mapped[ProviderAccountingState] = mapped_column(
        Enum(
            ProviderAccountingState,
            name="catalogue_provider_accounting_state",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=ProviderAccountingState.ESTIMATED,
        index=True,
    )
    reserved_cost_upper: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    cost_lower_bound: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    cost_upper_bound: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    dispatch_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
