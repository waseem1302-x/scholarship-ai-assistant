import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.auth.models import enum_values, utc_now


class DocumentKind(StrEnum):
    CV_RESUME = "cv_resume"
    STATEMENT_OF_PURPOSE = "statement_of_purpose"
    PERSONAL_STATEMENT = "personal_statement"
    MOTIVATION_LETTER = "motivation_letter"


class DocumentVersionStatus(StrEnum):
    QUARANTINED = "quarantined"
    SCANNING = "scanning"
    REJECTED = "rejected"
    EXTRACTING = "extracting"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class DocumentDeletionStatus(StrEnum):
    PENDING_DELETE = "pending_delete"
    OBJECT_DELETED = "object_deleted"


class ScanStatus(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class AnalysisStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    ABSTAINED = "abstained"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisProviderStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    INVALID_RESPONSE = "invalid_response"
    FAILED = "failed"
    ABSTAINED = "abstained"


class FeedbackCategory(StrEnum):
    STRENGTH = "strength"
    SUGGESTION = "suggestion"
    QUESTION = "question"
    WARNING = "warning"


class DocumentJobKind(StrEnum):
    SCAN = "scan"
    EXTRACT = "extract"
    ANALYSE = "analyse"


class DocumentAsset(Base):
    __tablename__ = "document_assets"
    __table_args__ = (Index("ix_document_assets_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_kind: Mapped[DocumentKind] = mapped_column(
        Enum(
            DocumentKind,
            name="document_kind",
            native_enum=False,
            values_callable=enum_values,
        )
    )
    # Original names are encrypted before persistence; they are never safe log fields.
    display_name_ciphertext: Mapped[str] = mapped_column(Text)
    retention_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_status: Mapped[str | None] = mapped_column(String(32), index=True)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "version_number",
            name="uq_document_versions_asset_number",
        ),
        Index("ix_document_versions_asset_created", "asset_id", "created_at"),
        Index("ix_document_versions_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_assets.id", ondelete="CASCADE"), index=True
    )
    # Redundant owner key makes every data access and foreign-domain link explicit.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    encryption_key_version: Mapped[str] = mapped_column(String(100), default="phase7.local-key.v1")
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    declared_content_type: Mapped[str] = mapped_column(String(100))
    detected_content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[DocumentVersionStatus] = mapped_column(
        Enum(
            DocumentVersionStatus,
            name="document_version_status",
            native_enum=False,
            values_callable=enum_values,
        ),
        default=DocumentVersionStatus.QUARANTINED,
        index=True,
    )
    scan_status: Mapped[ScanStatus] = mapped_column(
        Enum(
            ScanStatus,
            name="document_scan_status",
            native_enum=False,
            values_callable=enum_values,
        ),
        default=ScanStatus.PENDING,
    )
    rejection_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"
    __table_args__ = (UniqueConstraint("version_id", name="uq_document_extractions_version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ExtractionStatus] = mapped_column(
        Enum(
            ExtractionStatus,
            name="document_extraction_status",
            native_enum=False,
            values_callable=enum_values,
        ),
        default=ExtractionStatus.PENDING,
    )
    text_ciphertext: Mapped[str | None] = mapped_column(Text)
    extracted_character_count: Mapped[int | None] = mapped_column(Integer)
    extractor_version: Mapped[str] = mapped_column(String(100), default="phase7.restricted.v1")
    failure_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentConsent(Base):
    __tablename__ = "document_consents"
    __table_args__ = (Index("ix_document_consents_user_accepted", "user_id", "accepted_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    analysis_type: Mapped[DocumentKind] = mapped_column(
        Enum(
            DocumentKind,
            name="document_consent_kind",
            native_enum=False,
            values_callable=enum_values,
        )
    )
    notice_version: Mapped[str] = mapped_column(String(100))
    provider_config_version: Mapped[str] = mapped_column(String(100))
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class DocumentAnalysis(Base):
    __tablename__ = "document_analyses"
    __table_args__ = (Index("ix_document_analyses_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    consent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_consents.id", ondelete="RESTRICT"), unique=True
    )
    analysis_type: Mapped[DocumentKind] = mapped_column(
        Enum(
            DocumentKind,
            name="document_analysis_kind",
            native_enum=False,
            values_callable=enum_values,
        )
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(
            AnalysisStatus,
            name="document_analysis_status",
            native_enum=False,
            values_callable=enum_values,
        ),
        default=AnalysisStatus.QUEUED,
        index=True,
    )
    provider_status: Mapped[AnalysisProviderStatus] = mapped_column(
        Enum(
            AnalysisProviderStatus,
            name="document_analysis_provider_status",
            native_enum=False,
            values_callable=enum_values,
        ),
        default=AnalysisProviderStatus.PENDING,
    )
    provider: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(255))
    provider_config_version: Mapped[str] = mapped_column(String(100))
    rubric_version: Mapped[str] = mapped_column(String(100))
    summary_ciphertext: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(String(20))
    abstained_reason: Mapped[str | None] = mapped_column(String(100))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentFeedbackItem(Base):
    __tablename__ = "document_feedback_items"
    __table_args__ = (
        Index(
            "ix_document_feedback_items_analysis_position",
            "analysis_id",
            "position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_analyses.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[FeedbackCategory] = mapped_column(
        Enum(
            FeedbackCategory,
            name="document_feedback_category",
            native_enum=False,
            values_callable=enum_values,
        )
    )
    text_ciphertext: Mapped[str] = mapped_column(Text)
    excerpt_ciphertext: Mapped[str | None] = mapped_column(Text)
    rubric_category: Mapped[str] = mapped_column(String(100), default="general")
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    is_general_suggestion: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class DocumentAnalysisJob(Base):
    __tablename__ = "document_analysis_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_document_analysis_jobs_idempotency"),
        Index("ix_document_analysis_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_analyses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_kind: Mapped[DocumentJobKind] = mapped_column(
        Enum(
            DocumentJobKind,
            name="document_job_kind",
            native_enum=False,
            values_callable=enum_values,
        )
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(
            AnalysisStatus,
            name="document_job_status",
            native_enum=False,
            values_callable=enum_values,
        ),
        default=AnalysisStatus.QUEUED,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(100))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(64), index=True)
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplicationDocumentLink(Base):
    __tablename__ = "application_document_links"
    __table_args__ = (
        UniqueConstraint(
            "application_document_id",
            "version_id",
            name="uq_application_document_links_pair",
        ),
        Index("ix_application_document_links_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application_documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
