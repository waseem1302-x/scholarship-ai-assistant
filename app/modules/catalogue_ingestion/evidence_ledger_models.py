"""PR6 normalized evidence-ledger persistence models.

These rows preserve source assertions, policy interpretation, resolution, and
review history. They are not a second scholarship catalogue and cannot publish
canonical graph facts by themselves.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import enum_values, utc_now
from app.modules.catalogue_ingestion.claim_core import (
    ClaimType,
    ClaimValueState,
    EvidenceRole,
)
from app.modules.catalogue_ingestion.resolution_core import (
    ApplicabilityStatus,
    AuthorityStatus,
    EvidenceMatchStatus,
    ResolutionMemberRole,
    ResolutionOutcome,
    ScopeResolutionStatus,
)
from app.modules.opportunities.evidence_models import OfficialityStatus, SourceOwnerType


class LedgerIntegrityError(RuntimeError):
    """Raised when an append-only PR6 ledger boundary is violated."""


class EvidenceBundleStatus(StrEnum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    READY_FOR_RESOLUTION = "ready_for_resolution"
    RESOLVING = "resolving"
    RESOLVED = "resolved"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    BUDGET_EXHAUSTED = "budget_exhausted"
    FAILED = "failed"


class SourceExtractionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SourceExtractionAttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER_FAILED = "provider_failed"
    SCHEMA_FAILED = "schema_failed"
    ABANDONED = "abandoned"


class ClaimEvidenceValidationStatus(StrEnum):
    PENDING = "pending"
    MATCHED = "matched"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class ConflictSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKING = "blocking"


class ConflictSetStatus(StrEnum):
    OPEN = "open"
    RESOLVED_DETERMINISTICALLY = "resolved_deterministically"
    RESOLVED_BY_REVIEW = "resolved_by_review"
    SUPERSEDED = "superseded"


class ConflictReviewDecisionType(StrEnum):
    SELECT_CLAIM = "select_claim"
    CONFIRM_SCOPE_SPLIT = "confirm_scope_split"
    CONFIRM_SUPERSESSION = "confirm_supersession"
    KEEP_UNRESOLVED = "keep_unresolved"
    REJECT_ALL = "reject_all"


class MaterializationOperation(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    NOOP = "noop"
    SUPERSEDE = "supersede"
    DEACTIVATE = "deactivate"


def _enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        validate_strings=True,
        create_constraint=True,
        values_callable=enum_values,
    )


class CatalogueCandidateSourceSnapshot(Base):
    __tablename__ = "catalogue_candidate_source_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "candidate_source_id",
            "content_hash",
            name="uq_cat_candidate_snapshot_source_hash",
        ),
        CheckConstraint(
            "http_status >= 100 AND http_status <= 599",
            name="ck_cat_candidate_snapshot_http_status",
        ),
        CheckConstraint(
            "byte_count >= 0",
            name="ck_cat_candidate_snapshot_byte_count",
        ),
        CheckConstraint(
            "character_count >= 0",
            name="ck_cat_candidate_snapshot_char_count",
        ),
        Index(
            "ix_cat_candidate_snapshot_source_fetched",
            "candidate_source_id",
            "fetched_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidate_sources.id", ondelete="RESTRICT"),
        index=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    requested_url: Mapped[str] = mapped_column(String(2048))
    final_url: Mapped[str] = mapped_column(String(2048))
    http_status: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(128))
    normalized_text: Mapped[str] = mapped_column(Text)
    storage_reference: Mapped[str | None] = mapped_column(String(2048))
    extraction_method: Mapped[str] = mapped_column(String(64))
    language_code: Mapped[str | None] = mapped_column(String(16))
    byte_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    character_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fetch_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class CatalogueEvidenceBundle(Base):
    __tablename__ = "catalogue_evidence_bundles"
    __table_args__ = (
        CheckConstraint(
            "(candidate_id IS NOT NULL AND opportunity_id IS NULL) OR "
            "(candidate_id IS NULL AND opportunity_id IS NOT NULL)",
            name="ck_cat_bundle_target_xor",
        ),
        UniqueConstraint(
            "candidate_id",
            "objective_kind",
            "input_fingerprint",
            "resolver_policy_version",
            name="uq_cat_bundle_candidate_objective_input",
        ),
        UniqueConstraint(
            "opportunity_id",
            "objective_kind",
            "input_fingerprint",
            "resolver_policy_version",
            name="uq_cat_bundle_opportunity_objective_input",
        ),
        Index("ix_cat_bundle_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="RESTRICT"),
        index=True,
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="RESTRICT"),
        index=True,
    )
    objective_kind: Mapped[str] = mapped_column(String(64))
    objective_scope_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    target_identity_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolver_policy_version: Mapped[str] = mapped_column(String(100))
    status: Mapped[EvidenceBundleStatus] = mapped_column(
        _enum(EvidenceBundleStatus, "cat_evidence_bundle_status"),
        default=EvidenceBundleStatus.PENDING,
        server_default=EvidenceBundleStatus.PENDING.value,
        index=True,
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))


class CatalogueEvidenceBundleSource(Base):
    __tablename__ = "catalogue_evidence_bundle_sources"
    __table_args__ = (
        CheckConstraint(
            "(candidate_source_snapshot_id IS NOT NULL AND source_snapshot_id IS NULL) OR "
            "(candidate_source_snapshot_id IS NULL AND source_snapshot_id IS NOT NULL)",
            name="ck_cat_bundle_source_snapshot_xor",
        ),
        UniqueConstraint("id", "bundle_id", name="uq_cat_bundle_source_id_bundle"),
        UniqueConstraint(
            "bundle_id",
            "candidate_source_snapshot_id",
            name="uq_cat_bundle_candidate_snapshot",
        ),
        UniqueConstraint(
            "bundle_id",
            "source_snapshot_id",
            name="uq_cat_bundle_canonical_snapshot",
        ),
        Index("ix_cat_bundle_source_bundle", "bundle_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bundle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_evidence_bundles.id", ondelete="RESTRICT"),
        index=True,
    )
    candidate_source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidate_source_snapshots.id", ondelete="RESTRICT"),
        index=True,
    )
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="RESTRICT"),
        index=True,
    )
    source_context_hash: Mapped[str] = mapped_column(String(64))
    normalized_url: Mapped[str] = mapped_column(String(2048))
    domain: Mapped[str] = mapped_column(String(255))
    source_owner_type: Mapped[SourceOwnerType] = mapped_column(
        _enum(SourceOwnerType, "cat_bundle_source_owner_type")
    )
    source_owner_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    officiality_status: Mapped[OfficialityStatus] = mapped_column(
        _enum(OfficialityStatus, "cat_bundle_officiality_status")
    )
    authority_class: Mapped[str] = mapped_column(String(64))
    authority_scope_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    authority_policy_version: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class CatalogueSourceExtraction(Base):
    __tablename__ = "catalogue_source_extractions"
    __table_args__ = (
        CheckConstraint(
            "(candidate_source_snapshot_id IS NOT NULL AND source_snapshot_id IS NULL) OR "
            "(candidate_source_snapshot_id IS NULL AND source_snapshot_id IS NOT NULL)",
            name="ck_cat_source_extraction_snapshot_xor",
        ),
        CheckConstraint(
            "(status = 'pending' AND started_at IS NULL AND completed_at IS NULL "
            "AND accepted_output_json IS NULL AND failure_code IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL "
            "AND accepted_output_json IS NULL AND failure_code IS NULL) OR "
            "(status = 'succeeded' AND started_at IS NOT NULL AND completed_at IS NOT NULL "
            "AND accepted_output_json IS NOT NULL AND failure_code IS NULL) OR "
            "(status = 'failed' AND completed_at IS NOT NULL "
            "AND accepted_output_json IS NULL AND failure_code IS NOT NULL)",
            name="ck_cat_source_extraction_state_shape",
        ),
        UniqueConstraint(
            "candidate_source_snapshot_id",
            "contract_fingerprint",
            name="uq_cat_extraction_candidate_contract",
        ),
        UniqueConstraint(
            "source_snapshot_id",
            "contract_fingerprint",
            name="uq_cat_extraction_canonical_contract",
        ),
        Index("ix_cat_source_extraction_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidate_source_snapshots.id", ondelete="RESTRICT"),
        index=True,
    )
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="RESTRICT"),
        index=True,
    )
    target_context_hash: Mapped[str] = mapped_column(String(64))
    claim_plan_hash: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(100))
    instruction_version: Mapped[str] = mapped_column(String(100))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    contract_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[SourceExtractionStatus] = mapped_column(
        _enum(SourceExtractionStatus, "cat_source_extraction_status"),
        default=SourceExtractionStatus.PENDING,
        server_default=SourceExtractionStatus.PENDING.value,
        index=True,
    )
    accepted_output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogueSourceExtractionAttempt(Base):
    __tablename__ = "catalogue_source_extraction_attempts"
    __table_args__ = (
        UniqueConstraint(
            "extraction_id",
            "attempt_number",
            name="uq_cat_source_attempt_number",
        ),
        CheckConstraint("attempt_number > 0", name="ck_cat_source_attempt_positive"),
        CheckConstraint("input_tokens >= 0", name="ck_cat_source_attempt_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="ck_cat_source_attempt_output_tokens"),
        CheckConstraint("estimated_cost >= 0", name="ck_cat_source_attempt_cost"),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_cat_source_attempt_latency",
        ),
        CheckConstraint(
            "(status = 'in_progress' AND completed_at IS NULL AND error_code IS NULL) OR "
            "(status = 'succeeded' AND completed_at IS NOT NULL AND error_code IS NULL) OR "
            "(status IN ('rate_limited', 'timeout', 'provider_failed', 'schema_failed', "
            "'abandoned') AND completed_at IS NOT NULL AND error_code IS NOT NULL)",
            name="ck_cat_source_attempt_state_shape",
        ),
        Index("ix_cat_source_attempt_status", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_source_extractions.id", ondelete="RESTRICT"),
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[SourceExtractionAttemptStatus] = mapped_column(
        _enum(SourceExtractionAttemptStatus, "cat_source_attempt_status"),
        default=SourceExtractionAttemptStatus.IN_PROGRESS,
        server_default=SourceExtractionAttemptStatus.IN_PROGRESS.value,
        index=True,
    )
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    provider_response_id: Mapped[str | None] = mapped_column(String(255))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        default=Decimal("0"),
        server_default="0",
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogueFieldClaim(Base):
    __tablename__ = "catalogue_field_claims"
    __table_args__ = (
        UniqueConstraint(
            "source_extraction_id",
            "ordinal",
            name="uq_cat_field_claim_extraction_ordinal",
        ),
        UniqueConstraint(
            "source_extraction_id",
            "claim_fingerprint",
            name="uq_cat_field_claim_extraction_fingerprint",
        ),
        CheckConstraint("ordinal >= 0", name="ck_cat_field_claim_ordinal"),
        CheckConstraint(
            "(value_state = 'asserted_value' AND source_value_json IS NOT NULL "
            "AND source_value_hash IS NOT NULL) OR "
            "(value_state <> 'asserted_value' AND source_value_json IS NULL "
            "AND source_value_hash IS NULL)",
            name="ck_cat_field_claim_value_state_shape",
        ),
        CheckConstraint(
            "value_state = 'asserted_value' OR claim_type NOT IN "
            "('degree_level', 'funding_component', 'eligibility_rule') "
            "OR source_subject_json IS NOT NULL",
            name="ck_cat_field_claim_collection_subject",
        ),
        Index("ix_cat_field_claim_type_created", "claim_type", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_extraction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_source_extractions.id", ondelete="RESTRICT"),
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    claim_type: Mapped[ClaimType] = mapped_column(
        _enum(ClaimType, "cat_field_claim_type"),
        index=True,
    )
    source_subject_json: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    scope_hint_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    source_value_hash: Mapped[str | None] = mapped_column(String(64))
    value_state: Mapped[ClaimValueState] = mapped_column(
        _enum(ClaimValueState, "cat_field_claim_value_state"),
        index=True,
    )
    claim_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class CatalogueClaimEvidence(Base):
    __tablename__ = "catalogue_claim_evidence"
    __table_args__ = (
        UniqueConstraint("claim_id", "ordinal", name="uq_cat_claim_evidence_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_cat_claim_evidence_ordinal"),
        CheckConstraint(
            "length(trim(excerpt)) > 0",
            name="ck_cat_claim_evidence_excerpt_nonempty",
        ),
        CheckConstraint(
            "(validation_status = 'pending' AND excerpt_start IS NULL "
            "AND excerpt_end IS NULL AND validated_at IS NULL AND failure_code IS NULL) OR "
            "(validation_status = 'matched' AND excerpt_start IS NOT NULL "
            "AND excerpt_end IS NOT NULL AND excerpt_start >= 0 "
            "AND excerpt_end >= excerpt_start AND validated_at IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(validation_status IN ('not_found', 'ambiguous', 'invalid') "
            "AND excerpt_start IS NULL AND excerpt_end IS NULL "
            "AND validated_at IS NOT NULL AND failure_code IS NOT NULL)",
            name="ck_cat_claim_evidence_state_shape",
        ),
        Index("ix_cat_claim_evidence_status", "validation_status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_field_claims.id", ondelete="RESTRICT"),
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    role: Mapped[EvidenceRole] = mapped_column(_enum(EvidenceRole, "cat_claim_evidence_role"))
    excerpt: Mapped[str] = mapped_column(Text)
    section_label: Mapped[str | None] = mapped_column(String(255))
    locator: Mapped[str | None] = mapped_column(String(500))
    validation_status: Mapped[ClaimEvidenceValidationStatus] = mapped_column(
        _enum(ClaimEvidenceValidationStatus, "cat_claim_evidence_validation"),
        default=ClaimEvidenceValidationStatus.PENDING,
        server_default=ClaimEvidenceValidationStatus.PENDING.value,
        index=True,
    )
    excerpt_start: Mapped[int | None] = mapped_column(Integer)
    excerpt_end: Mapped[int | None] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogueEvidenceBundleClaim(Base):
    __tablename__ = "catalogue_evidence_bundle_claims"
    __table_args__ = (
        ForeignKeyConstraint(
            ["bundle_source_id", "bundle_id"],
            [
                "catalogue_evidence_bundle_sources.id",
                "catalogue_evidence_bundle_sources.bundle_id",
            ],
            ondelete="RESTRICT",
            name="fk_cat_bundle_claim_source_bundle",
        ),
        UniqueConstraint("id", "bundle_id", name="uq_cat_bundle_claim_id_bundle"),
        UniqueConstraint("bundle_id", "claim_id", name="uq_cat_bundle_claim"),
        Index("ix_cat_bundle_claim_source", "bundle_source_id", "claim_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bundle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_evidence_bundles.id", ondelete="RESTRICT"),
        index=True,
    )
    bundle_source_id: Mapped[uuid.UUID] = mapped_column(index=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_field_claims.id", ondelete="RESTRICT"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class CatalogueClaimAssessment(Base):
    __tablename__ = "catalogue_claim_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["bundle_claim_id", "bundle_id"],
            [
                "catalogue_evidence_bundle_claims.id",
                "catalogue_evidence_bundle_claims.bundle_id",
            ],
            ondelete="RESTRICT",
            name="fk_cat_claim_assessment_bundle_claim_bundle",
        ),
        UniqueConstraint("id", "bundle_id", name="uq_cat_claim_assessment_id_bundle"),
        UniqueConstraint(
            "bundle_claim_id",
            "policy_fingerprint",
            name="uq_cat_claim_assessment_policy",
        ),
        CheckConstraint(
            "(candidate_id IS NOT NULL AND scholarship_id IS NULL) OR "
            "(candidate_id IS NULL AND scholarship_id IS NOT NULL)",
            name="ck_cat_claim_assessment_target_xor",
        ),
        CheckConstraint(
            "track_id IS NULL OR cycle_id IS NOT NULL",
            name="ck_cat_claim_assessment_track_cycle",
        ),
        CheckConstraint(
            "programme_id IS NULL OR institution_id IS NOT NULL",
            name="ck_cat_claim_assessment_programme_institution",
        ),
        CheckConstraint(
            "candidate_id IS NULL OR (cycle_id IS NULL AND track_id IS NULL "
            "AND institution_id IS NULL AND programme_id IS NULL)",
            name="ck_cat_claim_assessment_candidate_scope",
        ),
        CheckConstraint(
            "(authority_status = 'authorized' AND authority_priority IS NOT NULL "
            "AND authority_priority >= 0) OR "
            "(authority_status <> 'authorized' AND authority_priority IS NULL)",
            name="ck_cat_claim_assessment_authority_priority",
        ),
        Index(
            "ix_cat_claim_assessment_claim_key",
            "claim_key_hash",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bundle_claim_id: Mapped[uuid.UUID] = mapped_column(index=True)
    bundle_id: Mapped[uuid.UUID] = mapped_column(index=True)
    supersedes_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_claim_assessments.id", ondelete="RESTRICT"),
        index=True,
    )
    policy_fingerprint: Mapped[str] = mapped_column(String(64))
    scope_resolver_version: Mapped[str] = mapped_column(String(100))
    authority_policy_version: Mapped[str] = mapped_column(String(100))
    canonicalizer_version: Mapped[str] = mapped_column(String(100))
    cycle_policy_version: Mapped[str] = mapped_column(String(100))
    evidence_status: Mapped[EvidenceMatchStatus] = mapped_column(
        _enum(EvidenceMatchStatus, "cat_claim_assessment_evidence")
    )
    scope_status: Mapped[ScopeResolutionStatus] = mapped_column(
        _enum(ScopeResolutionStatus, "cat_claim_assessment_scope")
    )
    authority_status: Mapped[AuthorityStatus] = mapped_column(
        _enum(AuthorityStatus, "cat_claim_assessment_authority")
    )
    authority_priority: Mapped[int | None] = mapped_column(Integer)
    applicability_status: Mapped[ApplicabilityStatus] = mapped_column(
        _enum(ApplicabilityStatus, "cat_claim_assessment_applicability")
    )
    canonical_field_path: Mapped[str] = mapped_column(String(255))
    collection_key: Mapped[str] = mapped_column(String(255))
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="RESTRICT"),
        index=True,
    )
    scholarship_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="RESTRICT"),
        index=True,
    )
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_cycles.id", ondelete="RESTRICT"),
        index=True,
    )
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_tracks.id", ondelete="RESTRICT"),
        index=True,
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"),
        index=True,
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_programmes.id", ondelete="RESTRICT"),
        index=True,
    )
    normalized_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    normalized_value_hash: Mapped[str | None] = mapped_column(String(64))
    claim_key_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class CatalogueClaimResolution(Base):
    __tablename__ = "catalogue_claim_resolutions"
    __table_args__ = (
        UniqueConstraint(
            "bundle_id",
            "claim_key_hash",
            "policy_fingerprint",
            name="uq_cat_claim_resolution_policy",
        ),
        UniqueConstraint("id", "bundle_id", name="uq_cat_resolution_id_bundle"),
        CheckConstraint(
            "(effective_state IS NULL AND effective_value_json IS NULL "
            "AND effective_value_hash IS NULL) OR "
            "(effective_state = 'asserted_value' AND effective_value_json IS NOT NULL "
            "AND effective_value_hash IS NOT NULL) OR "
            "(effective_state IS NOT NULL AND effective_state <> 'asserted_value' "
            "AND effective_value_json IS NULL AND effective_value_hash IS NOT NULL)",
            name="ck_cat_claim_resolution_effective_state_shape",
        ),
        Index("ix_cat_claim_resolution_outcome", "outcome", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bundle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_evidence_bundles.id", ondelete="RESTRICT"),
        index=True,
    )
    supersedes_resolution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_claim_resolutions.id", ondelete="RESTRICT"),
        index=True,
    )
    claim_key_hash: Mapped[str] = mapped_column(String(64))
    canonical_field_path: Mapped[str] = mapped_column(String(255))
    collection_key: Mapped[str] = mapped_column(String(255))
    scope_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolver_family: Mapped[str] = mapped_column(String(64))
    policy_fingerprint: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[ResolutionOutcome] = mapped_column(
        _enum(ResolutionOutcome, "cat_claim_resolution_outcome"),
        index=True,
    )
    effective_state: Mapped[ClaimValueState | None] = mapped_column(
        _enum(ClaimValueState, "cat_claim_resolution_effective_state")
    )
    effective_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    effective_value_hash: Mapped[str | None] = mapped_column(String(64))
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class CatalogueClaimResolutionMember(Base):
    __tablename__ = "catalogue_claim_resolution_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["resolution_id", "bundle_id"],
            ["catalogue_claim_resolutions.id", "catalogue_claim_resolutions.bundle_id"],
            ondelete="RESTRICT",
            name="fk_cat_resolution_member_resolution_bundle",
        ),
        ForeignKeyConstraint(
            ["claim_assessment_id", "bundle_id"],
            ["catalogue_claim_assessments.id", "catalogue_claim_assessments.bundle_id"],
            ondelete="RESTRICT",
            name="fk_cat_resolution_member_assessment_bundle",
        ),
        UniqueConstraint(
            "resolution_id",
            "claim_assessment_id",
            name="uq_cat_resolution_member_assessment",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    resolution_id: Mapped[uuid.UUID] = mapped_column(index=True)
    claim_assessment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    bundle_id: Mapped[uuid.UUID] = mapped_column(index=True)
    role: Mapped[ResolutionMemberRole] = mapped_column(
        _enum(ResolutionMemberRole, "cat_resolution_member_role")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class CatalogueConflictSet(Base):
    __tablename__ = "catalogue_conflict_sets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["resolution_id", "bundle_id"],
            ["catalogue_claim_resolutions.id", "catalogue_claim_resolutions.bundle_id"],
            ondelete="RESTRICT",
            name="fk_cat_conflict_resolution_bundle",
        ),
        UniqueConstraint("id", "bundle_id", name="uq_cat_conflict_set_id_bundle"),
        UniqueConstraint("resolution_id", name="uq_cat_conflict_resolution"),
        CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL) OR "
            "(status <> 'open' AND resolved_at IS NOT NULL)",
            name="ck_cat_conflict_resolution_time",
        ),
        Index("ix_cat_conflict_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bundle_id: Mapped[uuid.UUID] = mapped_column(index=True)
    resolution_id: Mapped[uuid.UUID] = mapped_column(index=True)
    claim_key_hash: Mapped[str] = mapped_column(String(64))
    severity: Mapped[ConflictSeverity] = mapped_column(
        _enum(ConflictSeverity, "cat_conflict_severity")
    )
    status: Mapped[ConflictSetStatus] = mapped_column(
        _enum(ConflictSetStatus, "cat_conflict_status"),
        default=ConflictSetStatus.OPEN,
        server_default=ConflictSetStatus.OPEN.value,
        index=True,
    )
    reason_code: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogueConflictClaim(Base):
    __tablename__ = "catalogue_conflict_claims"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conflict_set_id", "bundle_id"],
            ["catalogue_conflict_sets.id", "catalogue_conflict_sets.bundle_id"],
            ondelete="RESTRICT",
            name="fk_cat_conflict_claim_set_bundle",
        ),
        ForeignKeyConstraint(
            ["claim_assessment_id", "bundle_id"],
            ["catalogue_claim_assessments.id", "catalogue_claim_assessments.bundle_id"],
            ondelete="RESTRICT",
            name="fk_cat_conflict_claim_assessment_bundle",
        ),
        UniqueConstraint(
            "conflict_set_id",
            "claim_assessment_id",
            name="uq_cat_conflict_claim_assessment",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conflict_set_id: Mapped[uuid.UUID] = mapped_column(index=True)
    claim_assessment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    bundle_id: Mapped[uuid.UUID] = mapped_column(index=True)
    role: Mapped[ResolutionMemberRole] = mapped_column(
        _enum(ResolutionMemberRole, "cat_conflict_claim_role")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class CatalogueConflictReviewDecision(Base):
    __tablename__ = "catalogue_conflict_review_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conflict_set_id", "selected_claim_assessment_id"],
            [
                "catalogue_conflict_claims.conflict_set_id",
                "catalogue_conflict_claims.claim_assessment_id",
            ],
            ondelete="RESTRICT",
            name="fk_cat_conflict_review_selected_membership",
        ),
        CheckConstraint(
            "(decision = 'select_claim' AND selected_claim_assessment_id IS NOT NULL) OR "
            "(decision <> 'select_claim' AND selected_claim_assessment_id IS NULL)",
            name="ck_cat_conflict_review_selected_claim",
        ),
        CheckConstraint(
            "length(trim(resolution_notes)) > 0",
            name="ck_cat_conflict_review_notes_nonempty",
        ),
        Index("ix_cat_conflict_review_conflict", "conflict_set_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conflict_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_conflict_sets.id", ondelete="RESTRICT"),
        index=True,
    )
    supersedes_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_conflict_review_decisions.id", ondelete="RESTRICT"),
        index=True,
    )
    decision: Mapped[ConflictReviewDecisionType] = mapped_column(
        _enum(ConflictReviewDecisionType, "cat_conflict_review_decision")
    )
    selected_claim_assessment_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    resolution_notes: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(index=True)
    reviewer_identity_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class CatalogueSnapshotPromotion(Base):
    __tablename__ = "catalogue_snapshot_promotions"
    __table_args__ = (
        UniqueConstraint(
            "candidate_source_snapshot_id",
            name="uq_cat_snapshot_promotion_candidate",
        ),
        UniqueConstraint(
            "candidate_source_snapshot_id",
            "source_snapshot_id",
            name="uq_cat_snapshot_promotion_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidate_source_snapshots.id", ondelete="RESTRICT"),
        index=True,
    )
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="RESTRICT"),
        index=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_candidates.id", ondelete="RESTRICT"),
        index=True,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="RESTRICT"),
        index=True,
    )
    promotion_reason: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class CatalogueGraphMaterialization(Base):
    __tablename__ = "catalogue_graph_materializations"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_cat_graph_materialization_key"),
        Index("ix_cat_graph_materialization_target", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    resolution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_claim_resolutions.id", ondelete="RESTRICT"),
        index=True,
    )
    materializer_version: Mapped[str] = mapped_column(String(100))
    operation: Mapped[MaterializationOperation] = mapped_column(
        _enum(MaterializationOperation, "cat_materialization_operation")
    )
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    field_path: Mapped[str] = mapped_column(String(255))
    target_state_fingerprint: Mapped[str] = mapped_column(String(64))
    resulting_state_fingerprint: Mapped[str | None] = mapped_column(String(64))
    previous_materialization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_graph_materializations.id", ondelete="RESTRICT"),
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


_IMMUTABLE_MODELS = (
    CatalogueCandidateSourceSnapshot,
    CatalogueEvidenceBundleSource,
    CatalogueFieldClaim,
    CatalogueEvidenceBundleClaim,
    CatalogueClaimAssessment,
    CatalogueClaimResolution,
    CatalogueClaimResolutionMember,
    CatalogueConflictClaim,
    CatalogueConflictReviewDecision,
    CatalogueSnapshotPromotion,
    CatalogueGraphMaterialization,
)


def _raise_immutable() -> None:
    raise LedgerIntegrityError("PR6 ledger history is immutable; append a new record")


for _model in _IMMUTABLE_MODELS:
    event.listen(_model, "before_update", lambda *_: _raise_immutable())
    event.listen(_model, "before_delete", lambda *_: _raise_immutable())


def _changed_columns(target: object) -> set[str]:
    state = sa_inspect(target)
    return {
        attribute.key
        for attribute in state.mapper.column_attrs
        if state.attrs[attribute.key].history.has_changes()
    }


def _previous_enum_value(target: object, attribute_name: str) -> object | None:
    history = getattr(sa_inspect(target).attrs, attribute_name).history
    if history.deleted:
        return history.deleted[0]
    return None


@event.listens_for(CatalogueSourceExtraction, "before_update")
def _guard_source_extraction_update(*args: object) -> None:
    target = args[-1]
    if not isinstance(target, CatalogueSourceExtraction):
        return
    previous = _previous_enum_value(target, "status")
    changed = _changed_columns(target)
    if previous is None:
        raise LedgerIntegrityError("source extraction updates require an explicit state transition")
    allowed = {
        SourceExtractionStatus.PENDING: {
            SourceExtractionStatus.RUNNING,
            SourceExtractionStatus.FAILED,
        },
        SourceExtractionStatus.RUNNING: {
            SourceExtractionStatus.SUCCEEDED,
            SourceExtractionStatus.FAILED,
        },
    }
    if target.status not in allowed.get(previous, set()):
        raise LedgerIntegrityError("invalid or terminal source extraction state transition")
    allowed_columns = {
        "status",
        "started_at",
        "completed_at",
        "accepted_output_json",
        "failure_code",
    }
    if not changed <= allowed_columns:
        raise LedgerIntegrityError("source extraction contract fields are immutable")


@event.listens_for(CatalogueSourceExtraction, "before_delete")
def _guard_source_extraction_delete(*_: object) -> None:
    _raise_immutable()


@event.listens_for(CatalogueSourceExtractionAttempt, "before_update")
def _guard_source_attempt_update(*args: object) -> None:
    target = args[-1]
    if not isinstance(target, CatalogueSourceExtractionAttempt):
        return
    previous = _previous_enum_value(target, "status")
    if previous is not SourceExtractionAttemptStatus.IN_PROGRESS:
        raise LedgerIntegrityError("terminal source extraction attempts are immutable")
    if target.status is SourceExtractionAttemptStatus.IN_PROGRESS:
        raise LedgerIntegrityError("provider attempt must transition directly to terminal state")
    changed = _changed_columns(target)
    allowed_columns = {
        "status",
        "provider_response_id",
        "input_tokens",
        "output_tokens",
        "estimated_cost",
        "latency_ms",
        "error_code",
        "completed_at",
    }
    if not changed <= allowed_columns:
        raise LedgerIntegrityError("provider attempt request identity is immutable")


@event.listens_for(CatalogueSourceExtractionAttempt, "before_delete")
def _guard_source_attempt_delete(*_: object) -> None:
    _raise_immutable()


@event.listens_for(CatalogueClaimEvidence, "before_update")
def _guard_claim_evidence_update(*args: object) -> None:
    target = args[-1]
    if not isinstance(target, CatalogueClaimEvidence):
        return
    previous = _previous_enum_value(target, "validation_status")
    if previous is not ClaimEvidenceValidationStatus.PENDING:
        raise LedgerIntegrityError("terminal claim evidence is immutable")
    if target.validation_status is ClaimEvidenceValidationStatus.PENDING:
        raise LedgerIntegrityError("claim evidence must transition directly to terminal state")
    changed = _changed_columns(target)
    allowed_columns = {
        "validation_status",
        "excerpt_start",
        "excerpt_end",
        "failure_code",
        "validated_at",
    }
    if not changed <= allowed_columns:
        raise LedgerIntegrityError("claim evidence source assertion fields are immutable")


@event.listens_for(CatalogueClaimEvidence, "before_delete")
def _guard_claim_evidence_delete(*_: object) -> None:
    _raise_immutable()


_BUNDLE_TRANSITIONS = {
    EvidenceBundleStatus.PENDING: {
        EvidenceBundleStatus.EXTRACTING,
        EvidenceBundleStatus.READY_FOR_RESOLUTION,
        EvidenceBundleStatus.BLOCKED,
        EvidenceBundleStatus.BUDGET_EXHAUSTED,
        EvidenceBundleStatus.FAILED,
    },
    EvidenceBundleStatus.EXTRACTING: {
        EvidenceBundleStatus.READY_FOR_RESOLUTION,
        EvidenceBundleStatus.BLOCKED,
        EvidenceBundleStatus.BUDGET_EXHAUSTED,
        EvidenceBundleStatus.FAILED,
    },
    EvidenceBundleStatus.READY_FOR_RESOLUTION: {
        EvidenceBundleStatus.RESOLVING,
        EvidenceBundleStatus.BLOCKED,
        EvidenceBundleStatus.FAILED,
    },
    EvidenceBundleStatus.RESOLVING: {
        EvidenceBundleStatus.RESOLVED,
        EvidenceBundleStatus.REVIEW_REQUIRED,
        EvidenceBundleStatus.BLOCKED,
        EvidenceBundleStatus.FAILED,
    },
}


@event.listens_for(CatalogueEvidenceBundle, "before_update")
def _guard_bundle_update(*args: object) -> None:
    target = args[-1]
    if not isinstance(target, CatalogueEvidenceBundle):
        return
    previous = _previous_enum_value(target, "status")
    if previous is None or target.status not in _BUNDLE_TRANSITIONS.get(previous, set()):
        raise LedgerIntegrityError("invalid or terminal evidence-bundle state transition")
    changed = _changed_columns(target)
    allowed_columns = {"status", "started_at", "completed_at", "failure_code"}
    if not changed <= allowed_columns:
        raise LedgerIntegrityError("evidence-bundle objective identity is immutable")


@event.listens_for(CatalogueEvidenceBundle, "before_delete")
def _guard_bundle_delete(*_: object) -> None:
    _raise_immutable()


_CONFLICT_TRANSITIONS = {
    ConflictSetStatus.OPEN: {
        ConflictSetStatus.RESOLVED_DETERMINISTICALLY,
        ConflictSetStatus.RESOLVED_BY_REVIEW,
        ConflictSetStatus.SUPERSEDED,
    }
}


@event.listens_for(CatalogueConflictSet, "before_update")
def _guard_conflict_update(*args: object) -> None:
    target = args[-1]
    if not isinstance(target, CatalogueConflictSet):
        return
    previous = _previous_enum_value(target, "status")
    if previous is None or target.status not in _CONFLICT_TRANSITIONS.get(previous, set()):
        raise LedgerIntegrityError("invalid or terminal conflict-set state transition")
    changed = _changed_columns(target)
    if not changed <= {"status", "resolved_at"}:
        raise LedgerIntegrityError("conflict-set evidence identity is immutable")


@event.listens_for(CatalogueConflictSet, "before_delete")
def _guard_conflict_delete(*_: object) -> None:
    _raise_immutable()


__all__ = [
    "CatalogueCandidateSourceSnapshot",
    "CatalogueClaimAssessment",
    "CatalogueClaimEvidence",
    "CatalogueClaimResolution",
    "CatalogueClaimResolutionMember",
    "CatalogueConflictClaim",
    "CatalogueConflictReviewDecision",
    "CatalogueConflictSet",
    "CatalogueEvidenceBundle",
    "CatalogueEvidenceBundleClaim",
    "CatalogueEvidenceBundleSource",
    "CatalogueFieldClaim",
    "CatalogueGraphMaterialization",
    "CatalogueSnapshotPromotion",
    "CatalogueSourceExtraction",
    "CatalogueSourceExtractionAttempt",
    "ClaimEvidenceValidationStatus",
    "ConflictReviewDecisionType",
    "ConflictSetStatus",
    "ConflictSeverity",
    "EvidenceBundleStatus",
    "LedgerIntegrityError",
    "MaterializationOperation",
    "SourceExtractionAttemptStatus",
    "SourceExtractionStatus",
]
