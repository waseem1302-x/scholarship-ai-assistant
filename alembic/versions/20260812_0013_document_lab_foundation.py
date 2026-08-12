"""Create the isolated, consent-gated Document Lab domain.

Revision ID: 20260812_0013
Revises: 20260812_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260812_0013"
down_revision = "20260812_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(values: tuple[str, ...], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def uuid_column(name: str, *constraints: object, **kwargs: object) -> sa.Column:
    return sa.Column(name, sa.Uuid(), *constraints, **kwargs)


def upgrade() -> None:
    document_kind = enum(
        ("cv_resume", "statement_of_purpose", "personal_statement", "motivation_letter"),
        "document_kind",
    )
    version_status = enum(
        ("quarantined", "scanning", "rejected", "extracting", "ready", "failed", "deleted"),
        "document_version_status",
    )
    scan_status = enum(
        ("pending", "clean", "rejected", "unavailable", "failed"), "document_scan_status"
    )
    extraction_status = enum(
        ("pending", "running", "completed", "rejected", "failed"), "document_extraction_status"
    )
    analysis_status = enum(
        ("queued", "running", "completed", "abstained", "failed", "cancelled"),
        "document_analysis_status",
    )
    provider_status = enum(
        (
            "pending",
            "completed",
            "unavailable",
            "rate_limited",
            "quota_exhausted",
            "invalid_response",
            "failed",
            "abstained",
        ),
        "document_analysis_provider_status",
    )
    feedback_category = enum(
        ("strength", "suggestion", "question", "warning"), "document_feedback_category"
    )
    job_kind = enum(("scan", "extract", "analyse"), "document_job_kind")

    op.create_table(
        "document_assets",
        uuid_column("id", primary_key=True),
        uuid_column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("document_kind", document_kind, nullable=False),
        sa.Column("display_name_ciphertext", sa.Text(), nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_document_assets_user_created", "document_assets", ["user_id", "created_at"])
    op.create_index(
        "ix_document_assets_retention_expires_at", "document_assets", ["retention_expires_at"]
    )

    op.create_table(
        "document_versions",
        uuid_column("id", primary_key=True),
        uuid_column("asset_id", sa.ForeignKey("document_assets.id", ondelete="CASCADE")),
        uuid_column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("declared_content_type", sa.String(100), nullable=False),
        sa.Column("detected_content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer()),
        sa.Column("status", version_status, nullable=False, server_default="quarantined"),
        sa.Column("scan_status", scan_status, nullable=False, server_default="pending"),
        sa.Column("rejection_code", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("asset_id", "version_number", name="uq_document_versions_asset_number"),
    )
    op.create_index("ix_document_versions_asset_id", "document_versions", ["asset_id"])
    op.create_index("ix_document_versions_user_id", "document_versions", ["user_id"])
    op.create_index("ix_document_versions_content_sha256", "document_versions", ["content_sha256"])
    op.create_index(
        "ix_document_versions_asset_created", "document_versions", ["asset_id", "created_at"]
    )
    op.create_index("ix_document_versions_user_status", "document_versions", ["user_id", "status"])

    op.create_table(
        "document_extractions",
        uuid_column("id", primary_key=True),
        uuid_column("version_id", sa.ForeignKey("document_versions.id", ondelete="CASCADE")),
        uuid_column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("status", extraction_status, nullable=False, server_default="pending"),
        sa.Column("text_ciphertext", sa.Text()),
        sa.Column("extracted_character_count", sa.Integer()),
        sa.Column(
            "extractor_version",
            sa.String(100),
            nullable=False,
            server_default="phase7.restricted.v1",
        ),
        sa.Column("failure_code", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("version_id", name="uq_document_extractions_version"),
    )
    op.create_index("ix_document_extractions_version_id", "document_extractions", ["version_id"])
    op.create_index("ix_document_extractions_user_id", "document_extractions", ["user_id"])

    op.create_table(
        "document_consents",
        uuid_column("id", primary_key=True),
        uuid_column("version_id", sa.ForeignKey("document_versions.id", ondelete="CASCADE")),
        uuid_column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("analysis_type", document_kind, nullable=False),
        sa.Column("notice_version", sa.String(100), nullable=False),
        sa.Column("provider_config_version", sa.String(100), nullable=False),
        sa.Column(
            "accepted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_document_consents_version_id", "document_consents", ["version_id"])
    op.create_index("ix_document_consents_user_id", "document_consents", ["user_id"])
    op.create_index(
        "ix_document_consents_user_accepted", "document_consents", ["user_id", "accepted_at"]
    )

    op.create_table(
        "document_analyses",
        uuid_column("id", primary_key=True),
        uuid_column("version_id", sa.ForeignKey("document_versions.id", ondelete="CASCADE")),
        uuid_column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        uuid_column("consent_id", sa.ForeignKey("document_consents.id", ondelete="RESTRICT")),
        sa.Column("analysis_type", document_kind, nullable=False),
        sa.Column("status", analysis_status, nullable=False, server_default="queued"),
        sa.Column("provider_status", provider_status, nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(255), nullable=False),
        sa.Column("provider_config_version", sa.String(100), nullable=False),
        sa.Column("rubric_version", sa.String(100), nullable=False),
        sa.Column("summary_ciphertext", sa.Text()),
        sa.Column("confidence", sa.String(20)),
        sa.Column("abstained_reason", sa.String(100)),
        sa.Column("failure_code", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("consent_id"),
    )
    op.create_index("ix_document_analyses_version_id", "document_analyses", ["version_id"])
    op.create_index("ix_document_analyses_user_id", "document_analyses", ["user_id"])
    op.create_index("ix_document_analyses_status", "document_analyses", ["status"])
    op.create_index(
        "ix_document_analyses_user_created", "document_analyses", ["user_id", "created_at"]
    )

    op.create_table(
        "document_feedback_items",
        uuid_column("id", primary_key=True),
        uuid_column("analysis_id", sa.ForeignKey("document_analyses.id", ondelete="CASCADE")),
        sa.Column("category", feedback_category, nullable=False),
        sa.Column("text_ciphertext", sa.Text(), nullable=False),
        sa.Column("excerpt_ciphertext", sa.Text()),
        sa.Column("is_general_suggestion", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_document_feedback_items_analysis_id", "document_feedback_items", ["analysis_id"]
    )
    op.create_index(
        "ix_document_feedback_items_analysis_position",
        "document_feedback_items",
        ["analysis_id", "position"],
    )

    op.create_table(
        "document_analysis_jobs",
        uuid_column("id", primary_key=True),
        uuid_column("version_id", sa.ForeignKey("document_versions.id", ondelete="CASCADE")),
        uuid_column(
            "analysis_id", sa.ForeignKey("document_analyses.id", ondelete="CASCADE"), nullable=True
        ),
        uuid_column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("job_kind", job_kind, nullable=False),
        sa.Column("status", analysis_status, nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("idempotency_key", name="uq_document_analysis_jobs_idempotency"),
    )
    op.create_index(
        "ix_document_analysis_jobs_version_id", "document_analysis_jobs", ["version_id"]
    )
    op.create_index(
        "ix_document_analysis_jobs_analysis_id", "document_analysis_jobs", ["analysis_id"]
    )
    op.create_index("ix_document_analysis_jobs_user_id", "document_analysis_jobs", ["user_id"])
    op.create_index("ix_document_analysis_jobs_status", "document_analysis_jobs", ["status"])
    op.create_index(
        "ix_document_analysis_jobs_status_created",
        "document_analysis_jobs",
        ["status", "created_at"],
    )

    op.create_table(
        "application_document_links",
        uuid_column("id", primary_key=True),
        uuid_column(
            "application_document_id", sa.ForeignKey("application_documents.id", ondelete="CASCADE")
        ),
        uuid_column("version_id", sa.ForeignKey("document_versions.id", ondelete="CASCADE")),
        uuid_column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column(
            "confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "application_document_id", "version_id", name="uq_application_document_links_pair"
        ),
    )
    op.create_index(
        "ix_application_document_links_application_document_id",
        "application_document_links",
        ["application_document_id"],
    )
    op.create_index(
        "ix_application_document_links_version_id", "application_document_links", ["version_id"]
    )
    op.create_index(
        "ix_application_document_links_user_id", "application_document_links", ["user_id"]
    )


def downgrade() -> None:
    for table in (
        "application_document_links",
        "document_analysis_jobs",
        "document_feedback_items",
        "document_analyses",
        "document_consents",
        "document_extractions",
        "document_versions",
        "document_assets",
    ):
        op.drop_table(table)
