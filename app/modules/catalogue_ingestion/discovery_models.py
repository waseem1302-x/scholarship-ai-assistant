"""Durable, public-data-only discovery ledger models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
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
    Numeric,
    String,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import enum_values, utc_now


class DiscoveryRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    FAILED = "failed"


class DiscoveryQueryStatus(StrEnum):
    PLANNED = "planned"
    CLAIMED = "claimed"
    CALLING_PROVIDER = "calling_provider"
    RESPONSE_RECEIVED = "response_received"
    LEADS_RECORDED = "leads_recorded"
    COMPLETED = "completed"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_FAILED = "provider_failed"
    TOOL_NOT_EXECUTED = "tool_not_executed"
    RESPONSE_INVALID = "response_invalid"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    CANCELLED = "cancelled"


class DiscoveryAttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER_FAILED = "provider_failed"
    RESPONSE_INVALID = "response_invalid"
    TOOL_NOT_EXECUTED = "tool_not_executed"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    BUDGET_REJECTED = "budget_rejected"
    ABANDONED = "abandoned"


class DiscoveryOfficialityStatus(StrEnum):
    OFFICIAL = "official"
    SUPPORTING_OFFICIAL = "supporting_official"
    THIRD_PARTY = "third_party"
    UNRESOLVED = "unresolved"
    REJECTED_URL_POLICY = "rejected_url_policy"


class CatalogueDiscoveryRun(Base):
    __tablename__ = "catalogue_discovery_runs"
    __table_args__ = (
        CheckConstraint("max_queries > 0", name="max_queries_positive"),
        CheckConstraint("max_provider_calls >= 0", name="max_provider_calls_nonnegative"),
        CheckConstraint("max_tool_calls >= 0", name="max_tool_calls_nonnegative"),
        CheckConstraint("max_leads >= 0", name="max_leads_nonnegative"),
        CheckConstraint("max_response_bytes > 0", name="max_response_bytes_positive"),
        CheckConstraint("max_estimated_cost >= 0", name="max_cost_nonnegative"),
        CheckConstraint("provider_calls_reserved >= 0", name="provider_reserved_nonnegative"),
        CheckConstraint("provider_calls_completed >= 0", name="provider_completed_nonnegative"),
        CheckConstraint("tool_calls_reserved >= 0", name="tool_reserved_nonnegative"),
        CheckConstraint("tool_calls_completed >= 0", name="tool_completed_nonnegative"),
        CheckConstraint("estimated_cost_reserved >= 0", name="cost_reserved_nonnegative"),
        CheckConstraint("estimated_cost_settled >= 0", name="cost_settled_nonnegative"),
        CheckConstraint("raw_leads_seen >= 0", name="raw_leads_seen_nonnegative"),
        CheckConstraint("unique_leads >= 0", name="unique_leads_nonnegative"),
        CheckConstraint("promotions >= 0", name="promotions_nonnegative"),
        Index("ix_catalogue_discovery_runs_status_created", "status", "created_at"),
        Index("ix_catalogue_discovery_runs_target_created", "target_candidate_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    target_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="SET NULL"), index=True
    )
    target_identity_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    objective_kind: Mapped[str] = mapped_column(String(64), index=True)
    objective_scope: Mapped[dict[str, Any]] = mapped_column(JSON)
    objective_field_paths: Mapped[list[str]] = mapped_column(JSON)
    objective_reason_codes: Mapped[list[str]] = mapped_column(JSON)
    objective_criticality_tier: Mapped[int] = mapped_column(Integer)
    objective_priority_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    planner_version: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    status: Mapped[DiscoveryRunStatus] = mapped_column(
        Enum(
            DiscoveryRunStatus,
            name="catalogue_discovery_run_status",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=DiscoveryRunStatus.PENDING,
        index=True,
    )
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
    max_queries: Mapped[int] = mapped_column(Integer)
    max_provider_calls: Mapped[int] = mapped_column(Integer)
    max_tool_calls: Mapped[int] = mapped_column(Integer)
    max_leads: Mapped[int] = mapped_column(Integer)
    max_response_bytes: Mapped[int] = mapped_column(Integer)
    max_estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    provider_calls_reserved: Mapped[int] = mapped_column(Integer, default=0)
    provider_calls_completed: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls_reserved: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls_completed: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_reserved: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    estimated_cost_settled: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    raw_leads_seen: Mapped[int] = mapped_column(Integer, default=0)
    unique_leads: Mapped[int] = mapped_column(Integer, default=0)
    promotions: Mapped[int] = mapped_column(Integer, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    aggregate_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogueDiscoveryQuery(Base):
    __tablename__ = "catalogue_discovery_queries"
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_catalogue_discovery_query_ordinal"),
        UniqueConstraint("run_id", "query_hash", name="uq_catalogue_discovery_query_hash"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("provider_call_count >= 0", name="provider_calls_nonnegative"),
        CheckConstraint("tool_call_count >= 0", name="tool_calls_nonnegative"),
        CheckConstraint("response_bytes >= 0", name="response_bytes_nonnegative"),
        CheckConstraint("latency_ms >= 0", name="latency_nonnegative"),
        CheckConstraint("estimated_cost >= 0", name="estimated_cost_nonnegative"),
        Index(
            "ix_catalogue_discovery_queries_claim",
            "status",
            "next_attempt_at",
            "claimed_until",
            "ordinal",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_discovery_runs.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    query_text: Mapped[str] = mapped_column(String(1000))
    query_hash: Mapped[str] = mapped_column(String(64))
    query_kind: Mapped[str] = mapped_column(String(64))
    allowed_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    public_context: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[DiscoveryQueryStatus] = mapped_column(
        Enum(
            DiscoveryQueryStatus,
            name="catalogue_discovery_query_status",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=DiscoveryQueryStatus.PLANNED,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    claimed_by: Mapped[str | None] = mapped_column(String(100))
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    provider_call_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    response_bytes: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogueDiscoveryAttempt(Base):
    __tablename__ = "catalogue_discovery_attempts"
    __table_args__ = (
        UniqueConstraint(
            "query_id", "attempt_number", name="uq_catalogue_discovery_attempt_number"
        ),
        CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        CheckConstraint("reserved_tool_calls >= 0", name="reserved_tool_calls_nonnegative"),
        CheckConstraint("reserved_estimated_cost >= 0", name="reserved_cost_nonnegative"),
        CheckConstraint("tool_call_count >= 0", name="attempt_tool_calls_nonnegative"),
        CheckConstraint("result_url_count >= 0", name="result_urls_nonnegative"),
        CheckConstraint("response_bytes >= 0", name="attempt_response_bytes_nonnegative"),
        CheckConstraint("estimated_model_cost >= 0", name="model_cost_nonnegative"),
        CheckConstraint("estimated_tool_cost >= 0", name="tool_cost_nonnegative"),
        CheckConstraint("estimated_total_cost >= 0", name="total_cost_nonnegative"),
        CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="http_status_valid",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0", name="input_tokens_nonnegative"
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0", name="output_tokens_nonnegative"
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0", name="attempt_latency_nonnegative"
        ),
        Index("ix_catalogue_discovery_attempts_status_started", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_discovery_queries.id", ondelete="RESTRICT"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[DiscoveryAttemptStatus] = mapped_column(
        Enum(
            DiscoveryAttemptStatus,
            name="catalogue_discovery_attempt_status",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    reserved_tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    reserved_estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    provider_response_id: Mapped[str | None] = mapped_column(String(255))
    http_status: Mapped[int | None] = mapped_column(Integer)
    web_search_executed: Mapped[bool | None] = mapped_column(Boolean)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    result_url_count: Mapped[int] = mapped_column(Integer, default=0)
    response_bytes: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_model_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    estimated_tool_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    estimated_total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogueDiscoveryLead(Base):
    __tablename__ = "catalogue_discovery_leads"
    __table_args__ = (
        UniqueConstraint("url_fingerprint", name="uq_catalogue_discovery_lead_fingerprint"),
        UniqueConstraint("normalized_url", name="uq_catalogue_discovery_lead_url"),
        Index("ix_catalogue_discovery_leads_host_active", "host", "active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    normalized_url: Mapped[str] = mapped_column(String(2048))
    url_fingerprint: Mapped[str] = mapped_column(String(64))
    host: Mapped[str] = mapped_column(String(255), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class CatalogueDiscoveryObservation(Base):
    __tablename__ = "catalogue_discovery_observations"
    __table_args__ = (
        UniqueConstraint(
            "query_id", "lead_id", name="uq_catalogue_discovery_observation_query_lead"
        ),
        CheckConstraint(
            "provider_rank IS NULL OR provider_rank > 0", name="provider_rank_positive"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_discovery_queries.id", ondelete="RESTRICT"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_discovery_leads.id", ondelete="RESTRICT"), index=True
    )
    provider_rank: Mapped[int | None] = mapped_column(Integer)
    provider_source_type: Mapped[str | None] = mapped_column(String(64))
    minimal_title: Mapped[str | None] = mapped_column(String(500))
    discovery_reason: Mapped[str] = mapped_column(String(255))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CatalogueDiscoveryAssessment(Base):
    __tablename__ = "catalogue_discovery_assessments"
    __table_args__ = (
        UniqueConstraint(
            "lead_id",
            "assessment_context_hash",
            "classifier_version",
            name="uq_catalogue_discovery_assessment_context",
        ),
        CheckConstraint(
            "trust_tier IS NULL OR (trust_tier >= 1 AND trust_tier <= 4)",
            name="trust_tier_valid",
        ),
        Index("ix_catalogue_discovery_assessments_run_created", "run_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_discovery_leads.id", ondelete="RESTRICT"), index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_discovery_runs.id", ondelete="RESTRICT"), index=True
    )
    assessment_context_hash: Mapped[str] = mapped_column(String(64))
    context_type: Mapped[str] = mapped_column(String(64))
    context_scholarship_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="RESTRICT"), index=True
    )
    context_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("providers.id", ondelete="RESTRICT"), index=True
    )
    context_institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), index=True
    )
    context_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_cycles.id", ondelete="RESTRICT"), index=True
    )
    owner_type: Mapped[str] = mapped_column(String(32))
    owner_id: Mapped[uuid.UUID | None] = mapped_column()
    canonical_domain: Mapped[str | None] = mapped_column(String(255))
    officiality_status: Mapped[DiscoveryOfficialityStatus] = mapped_column(
        Enum(
            DiscoveryOfficialityStatus,
            name="catalogue_discovery_officiality_status",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    trust_tier: Mapped[int | None] = mapped_column(Integer)
    reason_code: Mapped[str] = mapped_column(String(100))
    reason_detail: Mapped[str] = mapped_column(String(500))
    classifier_version: Mapped[str] = mapped_column(String(100))
    supersedes_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_discovery_assessments.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class CatalogueDiscoveryPromotion(Base):
    __tablename__ = "catalogue_discovery_promotions"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "lead_id", name="uq_catalogue_discovery_promotion_candidate_lead"
        ),
        Index("ix_catalogue_discovery_promotions_run_created", "run_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_discovery_runs.id", ondelete="RESTRICT"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_discovery_leads.id", ondelete="RESTRICT"), index=True
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_discovery_assessments.id", ondelete="RESTRICT"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="RESTRICT"), index=True
    )
    candidate_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidate_sources.id", ondelete="SET NULL"), index=True
    )
    promotion_kind: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


def _reject_provenance_mutation(_mapper: object, _connection: object, target: object) -> None:
    raise ValueError(f"{type(target).__name__} is immutable provenance")


for _immutable_model in (
    CatalogueDiscoveryObservation,
    CatalogueDiscoveryAssessment,
    CatalogueDiscoveryPromotion,
):
    event.listen(_immutable_model, "before_update", _reject_provenance_mutation)
    event.listen(_immutable_model, "before_delete", _reject_provenance_mutation)
