"""Pipeline staging and audit records; the opportunity catalogue remains the source of truth."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.auth.models import enum_values, utc_now
from app.modules.catalogue_ingestion import discovery_models as _discovery_models  # noqa: F401
from app.modules.opportunities.graph_models import RelationshipKind


class IngestionRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DEAD_LETTER = "dead_letter"


class IngestionRunStage(StrEnum):
    QUEUED = "queued"
    ACQUIRING = "acquiring"
    EXTRACTING = "extracting"
    RESOLVING = "resolving"
    COMPLETE = "complete"
    DEAD_LETTER = "dead_letter"


class IngestionRunRetryClass(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


class IngestionMode(StrEnum):
    CANDIDATE_ONLY = "candidate_only"
    EXTRACTION = "extraction"
    VALIDATION = "validation"
    REVIEW_QUEUE = "review_queue"


class IngestionInputKind(StrEnum):
    SEED_SOURCE = "seed_source"
    DIRECT_URL = "direct_url"


class CandidateStatus(StrEnum):
    DISCOVERED = "discovered"
    OFFICIAL_SOURCE_CANDIDATE = "official_source_candidate"
    SOURCE_FETCHED = "source_fetched"
    EXTRACTED = "extracted"
    VALIDATION_FAILED = "validation_failed"
    CONFLICT_DETECTED = "conflict_detected"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    NEEDS_REVIEW = "needs_review"
    READY_FOR_REVIEW = "ready_for_review"
    SUBMITTED_FOR_REVIEW = "submitted_for_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    SOURCE_CHANGED = "source_changed"


class CandidateSourceStatus(StrEnum):
    DISCOVERED = "discovered"
    FETCHED = "fetched"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class CandidateSourceRole(StrEnum):
    DISCOVERED = "discovered"
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    CRAWLED = "crawled"


class ExtractionAttemptStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PROVIDER_FAILED = "provider_failed"
    SCHEMA_FAILED = "schema_failed"
    VALIDATION_FAILED = "validation_failed"
    REUSED = "reused"


class ClassificationConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    UNRESOLVED = "unresolved"


class ClassificationDecisionStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ReviewDecisionAction(StrEnum):
    SUBMITTED = "submitted"


class CatalogueIngestionRun(Base):
    __tablename__ = "catalogue_ingestion_runs"
    __table_args__ = (
        Index("ix_catalogue_ingestion_runs_status_created", "status", "created_at"),
        Index(
            "ix_catalogue_ingestion_runs_claim",
            "status",
            "next_attempt_at",
            "claimed_until",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_label: Mapped[str] = mapped_column(String(255))
    source_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, default=lambda: uuid.uuid4().hex
    )
    input_kind: Mapped[IngestionInputKind] = mapped_column(
        Enum(
            IngestionInputKind,
            name="catalogue_ingestion_input_kind",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=IngestionInputKind.SEED_SOURCE,
        server_default=IngestionInputKind.SEED_SOURCE.value,
        index=True,
    )
    operator_url: Mapped[str | None] = mapped_column(String(2048))
    mode: Mapped[IngestionMode] = mapped_column(
        Enum(
            IngestionMode,
            name="catalogue_ingestion_mode",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        )
    )
    status: Mapped[IngestionRunStatus] = mapped_column(
        Enum(
            IngestionRunStatus,
            name="catalogue_ingestion_run_status",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=IngestionRunStatus.PENDING,
        index=True,
    )
    stage: Mapped[IngestionRunStage] = mapped_column(
        Enum(
            IngestionRunStage,
            name="catalogue_ingestion_run_stage",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=IngestionRunStage.QUEUED,
        server_default=IngestionRunStage.QUEUED.value,
        index=True,
    )
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    checkpoint_cursor: Mapped[int] = mapped_column(Integer, default=0)
    max_candidates: Mapped[int] = mapped_column(Integer)
    max_pages_per_candidate: Mapped[int] = mapped_column(Integer)
    max_model_calls: Mapped[int] = mapped_column(Integer)
    max_input_characters: Mapped[int] = mapped_column(Integer)
    max_output_tokens: Mapped[int] = mapped_column(Integer)
    max_estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    aggregate_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    last_error_reason: Mapped[str | None] = mapped_column(Text)
    retry_class: Mapped[IngestionRunRetryClass | None] = mapped_column(
        Enum(
            IngestionRunRetryClass,
            name="catalogue_ingestion_run_retry_class",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        )
    )
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    claimed_by: Mapped[str | None] = mapped_column(String(100))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), index=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    candidates: Mapped[list["CatalogueCandidate"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class CatalogueCandidate(Base):
    __tablename__ = "catalogue_candidates"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_catalogue_candidates_idempotency"),
        Index(
            "ix_catalogue_candidates_claim",
            "status",
            "next_attempt_at",
            "claimed_until",
            "created_at",
        ),
        Index("ix_catalogue_candidates_run_seed", "run_id", "seed_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_ingestion_runs.id", ondelete="CASCADE"), index=True
    )
    seed_index: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    seed_name: Mapped[str] = mapped_column(String(255))
    seed_provider: Mapped[str | None] = mapped_column(String(255))
    seed_university: Mapped[str | None] = mapped_column(String(255))
    seed_country: Mapped[str | None] = mapped_column(String(100))
    seed_cycle: Mapped[str | None] = mapped_column(String(120))
    seed_intake_year: Mapped[int | None] = mapped_column(Integer)
    seed_official_url: Mapped[str | None] = mapped_column(String(2048))
    identity_hint_is_asserted: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    seed_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(
            CandidateStatus,
            name="catalogue_candidate_status",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=CandidateStatus.DISCOVERED,
        index=True,
    )
    proposed_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    acquisition_bundle: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    validation_errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    conflicts: Mapped[list[str]] = mapped_column(JSON, default=list)
    duplicate_opportunity_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    claimed_by: Mapped[str | None] = mapped_column(String(100))
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), index=True
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

    run: Mapped[CatalogueIngestionRun] = relationship(back_populates="candidates")
    sources: Mapped[list["CatalogueCandidateSource"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    extraction_attempts: Mapped[list["CatalogueExtractionAttempt"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    classification_decisions: Mapped[list["ClassificationDecision"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    review_proposals: Mapped[list["CatalogueReviewProposal"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class CatalogueCandidateSource(Base):
    __tablename__ = "catalogue_candidate_sources"
    __table_args__ = (
        UniqueConstraint("candidate_id", "canonical_url", name="uq_catalogue_candidate_source_url"),
        UniqueConstraint(
            "candidate_id",
            "discovery_lead_id",
            name="uq_catalogue_candidate_source_discovery_lead",
        ),
        Index("ix_catalogue_candidate_sources_hash", "content_hash", "candidate_id"),
        Index("ix_catalogue_candidate_sources_official", "is_official", "trust_tier"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    discovery_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_discovery_leads.id", ondelete="SET NULL"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str] = mapped_column(String(2048))
    final_url: Mapped[str | None] = mapped_column(String(2048))
    source_role: Mapped[CandidateSourceRole] = mapped_column(
        Enum(
            CandidateSourceRole,
            name="catalogue_candidate_source_role",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=CandidateSourceRole.DISCOVERED,
        server_default=CandidateSourceRole.DISCOVERED.value,
    )
    status: Mapped[CandidateSourceStatus] = mapped_column(
        Enum(
            CandidateSourceStatus,
            name="catalogue_candidate_source_status",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=CandidateSourceStatus.DISCOVERED,
    )
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    trust_tier: Mapped[int | None] = mapped_column(Integer)
    classification_reason: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(255))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    relevant_excerpt: Mapped[str | None] = mapped_column(Text)
    bytes_read: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    candidate: Mapped[CatalogueCandidate] = relationship(back_populates="sources")
    extraction_attempts: Mapped[list["CatalogueExtractionAttempt"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["CatalogueSourceArtifact"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class CatalogueSourceArtifact(Base):
    """Immutable fetched text used as the pre-canonical evidence boundary."""

    __tablename__ = "catalogue_source_artifacts"
    __table_args__ = (
        UniqueConstraint("source_id", "content_hash", name="uq_catalogue_source_artifact_hash"),
        Index("ix_catalogue_source_artifacts_hash_created", "content_hash", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidate_sources.id", ondelete="RESTRICT"), index=True
    )
    final_url: Mapped[str] = mapped_column(String(2048))
    content_type: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64))
    normalized_text: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(64))
    byte_count: Mapped[int] = mapped_column(Integer)
    character_count: Mapped[int] = mapped_column(Integer)
    fetch_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    source: Mapped[CatalogueCandidateSource] = relationship(back_populates="artifacts")
    evidence_blocks: Mapped[list["CatalogueEvidenceBlock"]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )
    routing_decisions: Mapped[list["CatalogueSourceRoutingDecision"]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )


@event.listens_for(CatalogueSourceArtifact, "before_update", propagate=True)
def _prevent_source_artifact_update(*_: object) -> None:
    raise RuntimeError("catalogue source artifacts are immutable; create a new artifact")


@event.listens_for(CatalogueSourceArtifact, "before_delete", propagate=True)
def _prevent_source_artifact_delete(*_: object) -> None:
    raise RuntimeError("catalogue source artifacts cannot be deleted")


class CatalogueEvidenceBlock(Base):
    """Versioned deterministic citation unit derived from one immutable artifact."""

    __tablename__ = "catalogue_evidence_blocks"
    __table_args__ = (
        UniqueConstraint("artifact_id", "block_index", name="uq_catalogue_evidence_block_index"),
        UniqueConstraint("artifact_id", "block_id", name="uq_catalogue_evidence_block_id"),
        Index("ix_catalogue_evidence_blocks_artifact_offsets", "artifact_id", "start_offset"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_source_artifacts.id", ondelete="RESTRICT"), index=True
    )
    block_id: Mapped[str] = mapped_column(String(64))
    canonicalization_version: Mapped[str] = mapped_column(String(64))
    block_index: Mapped[int] = mapped_column(Integer)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    artifact: Mapped[CatalogueSourceArtifact] = relationship(back_populates="evidence_blocks")


@event.listens_for(CatalogueEvidenceBlock, "before_update", propagate=True)
def _prevent_evidence_block_update(*_: object) -> None:
    raise RuntimeError("catalogue evidence blocks are immutable; create a new artifact")


@event.listens_for(CatalogueEvidenceBlock, "before_delete", propagate=True)
def _prevent_evidence_block_delete(*_: object) -> None:
    raise RuntimeError("catalogue evidence blocks cannot be deleted")


class CatalogueExtractionAttempt(Base):
    __tablename__ = "catalogue_extraction_attempts"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "source_id",
            "content_hash",
            "schema_version",
            "provider",
            "model",
            name="uq_catalogue_extraction_version",
        ),
        Index("ix_catalogue_extraction_attempts_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidate_sources.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    schema_version: Mapped[str] = mapped_column(String(100))
    content_hash: Mapped[str] = mapped_column(String(64))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[ExtractionAttemptStatus] = mapped_column(
        Enum(
            ExtractionAttemptStatus,
            name="catalogue_extraction_attempt_status",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        )
    )
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    candidate: Mapped[CatalogueCandidate] = relationship(back_populates="extraction_attempts")
    source: Mapped[CatalogueCandidateSource] = relationship(back_populates="extraction_attempts")


class CatalogueSourceRoutingDecision(Base):
    """Versioned deterministic role/cycle decision for one immutable artifact."""

    __tablename__ = "catalogue_source_routing_decisions"
    __table_args__ = (
        UniqueConstraint(
            "artifact_id",
            "classifier_version",
            name="uq_catalogue_source_routing_artifact_version",
        ),
        Index("ix_catalogue_source_routing_role_cycle", "role", "cycle"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_source_artifacts.id", ondelete="RESTRICT"), index=True
    )
    classifier_version: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(64))
    cycle: Mapped[str] = mapped_column(String(32))
    authority_tier: Mapped[str] = mapped_column(String(16), default="unresolved")
    deterministic_signals: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(default=0.0)
    ambiguity_reason: Mapped[str | None] = mapped_column(String(255))
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, default=True)
    applicable_objectives: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    artifact: Mapped[CatalogueSourceArtifact] = relationship(back_populates="routing_decisions")


class ClassificationDecision(Base):
    """Append-only classifier proposal awaiting an explicit human review action."""

    __tablename__ = "classification_decisions"
    __table_args__ = (
        Index("ix_classification_decisions_candidate_created", "candidate_id", "created_at"),
        Index("ix_classification_decisions_status_created", "decision_status", "created_at"),
        Index(
            "ix_classification_decisions_relationship_status",
            "proposed_relationship",
            "decision_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    proposed_relationship: Mapped[RelationshipKind] = mapped_column(
        Enum(
            RelationshipKind,
            name="classification_relationship_kind",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    parent_scholarship_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), index=True
    )
    proposed_new_scholarship_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), index=True
    )
    deterministic_signals: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    confidence_band: Mapped[ClassificationConfidenceBand] = mapped_column(
        Enum(
            ClassificationConfidenceBand,
            name="classification_confidence_band",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        index=True,
    )
    evidence_snapshot_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision_status: Mapped[ClassificationDecisionStatus] = mapped_column(
        Enum(
            ClassificationDecisionStatus,
            name="classification_decision_status",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        default=ClassificationDecisionStatus.NEEDS_REVIEW,
        server_default=ClassificationDecisionStatus.NEEDS_REVIEW.value,
        index=True,
    )
    reason_code: Mapped[str] = mapped_column(String(100))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    candidate: Mapped[CatalogueCandidate] = relationship(back_populates="classification_decisions")


class CatalogueReviewProposal(Base):
    """Immutable snapshot of the candidate payload and cited evidence at review time."""

    __tablename__ = "catalogue_review_proposals"
    __table_args__ = (
        UniqueConstraint("candidate_id", "proposal_hash", name="uq_catalogue_review_proposal_hash"),
        Index("ix_catalogue_review_proposals_candidate_created", "candidate_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="CASCADE"), index=True
    )
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_versions: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    candidate: Mapped[CatalogueCandidate] = relationship(back_populates="review_proposals")
    decisions: Mapped[list["CatalogueReviewDecision"]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan"
    )


class CatalogueReviewDecision(Base):
    """Append-only human action referring to one immutable review proposal."""

    __tablename__ = "catalogue_review_decisions"
    __table_args__ = (
        Index("ix_catalogue_review_decisions_proposal_created", "proposal_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_review_proposals.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[ReviewDecisionAction] = mapped_column(
        Enum(
            ReviewDecisionAction,
            name="catalogue_review_decision_action",
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
        ),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    prior_candidate_status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    proposal: Mapped[CatalogueReviewProposal] = relationship(back_populates="decisions")
