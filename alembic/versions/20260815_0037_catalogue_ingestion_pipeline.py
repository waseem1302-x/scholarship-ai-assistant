"""Add bounded catalogue ingestion staging and scalable source-monitor claims.

Revision ID: 20260815_0037
Revises: 20260814_0036
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260815_0037"
down_revision = "20260814_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.add_column(
        "sources", sa.Column("monitor_next_check_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "sources", sa.Column("monitor_claimed_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "sources",
        sa.Column("monitor_failure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        op.f("ix_sources_monitor_next_check_at"),
        "sources",
        ["monitor_next_check_at"],
        unique=False,
    )
    op.create_index(
        "ix_sources_monitor_claim",
        "sources",
        ["monitor_next_check_at", "monitor_claimed_until", "verification_status"],
        unique=False,
    )

    op.create_table(
        "catalogue_ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "mode",
            _enum(
                "catalogue_ingestion_mode",
                "candidate_only",
                "extraction",
                "validation",
                "review_queue",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum(
                "catalogue_ingestion_run_status",
                "pending",
                "running",
                "completed",
                "failed",
                "budget_exhausted",
            ),
            nullable=False,
        ),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checkpoint_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_candidates", sa.Integer(), nullable=False),
        sa.Column("max_pages_per_candidate", sa.Integer(), nullable=False),
        sa.Column("max_model_calls", sa.Integer(), nullable=False),
        sa.Column("max_input_characters", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("max_estimated_cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("model_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("aggregate_summary", sa.JSON(), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_catalogue_ingestion_runs_source_fingerprint"),
        "catalogue_ingestion_runs",
        ["source_fingerprint"],
    )
    op.create_index(
        op.f("ix_catalogue_ingestion_runs_status"), "catalogue_ingestion_runs", ["status"]
    )
    op.create_index(
        "ix_catalogue_ingestion_runs_status_created",
        "catalogue_ingestion_runs",
        ["status", "created_at"],
    )

    op.create_table(
        "catalogue_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("seed_index", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("seed_name", sa.String(length=255), nullable=False),
        sa.Column("seed_provider", sa.String(length=255), nullable=True),
        sa.Column("seed_university", sa.String(length=255), nullable=True),
        sa.Column("seed_country", sa.String(length=100), nullable=True),
        sa.Column("seed_cycle", sa.String(length=120), nullable=True),
        sa.Column("seed_intake_year", sa.Integer(), nullable=True),
        sa.Column("seed_official_url", sa.String(length=2048), nullable=True),
        sa.Column("seed_keywords", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            _enum(
                "catalogue_candidate_status",
                "discovered",
                "official_source_candidate",
                "source_fetched",
                "extracted",
                "validation_failed",
                "conflict_detected",
                "duplicate_candidate",
                "needs_review",
                "ready_for_review",
                "submitted_for_review",
                "approved",
                "rejected",
                "published",
                "source_changed",
            ),
            nullable=False,
        ),
        sa.Column("proposed_payload", sa.JSON(), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=False),
        sa.Column("duplicate_opportunity_ids", sa.JSON(), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opportunity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["catalogue_ingestion_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_catalogue_candidates_idempotency"),
    )
    for column in ("run_id", "status", "next_attempt_at", "claimed_until", "opportunity_id"):
        op.create_index(op.f(f"ix_catalogue_candidates_{column}"), "catalogue_candidates", [column])
    op.create_index(
        "ix_catalogue_candidates_claim",
        "catalogue_candidates",
        ["status", "next_attempt_at", "claimed_until", "created_at"],
    )
    op.create_index(
        "ix_catalogue_candidates_run_seed", "catalogue_candidates", ["run_id", "seed_index"]
    )

    op.create_table(
        "catalogue_candidate_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=False),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "status",
            _enum(
                "catalogue_candidate_source_status",
                "discovered",
                "fetched",
                "failed",
                "manual_review",
            ),
            nullable=False,
        ),
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trust_tier", sa.Integer(), nullable=True),
        sa.Column("classification_reason", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("relevant_excerpt", sa.Text(), nullable=True),
        sa.Column("bytes_read", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id", "canonical_url", name="uq_catalogue_candidate_source_url"
        ),
    )
    op.create_index(
        op.f("ix_catalogue_candidate_sources_candidate_id"),
        "catalogue_candidate_sources",
        ["candidate_id"],
    )
    op.create_index(
        op.f("ix_catalogue_candidate_sources_is_official"),
        "catalogue_candidate_sources",
        ["is_official"],
    )
    op.create_index(
        "ix_catalogue_candidate_sources_hash",
        "catalogue_candidate_sources",
        ["content_hash", "candidate_id"],
    )
    op.create_index(
        "ix_catalogue_candidate_sources_official",
        "catalogue_candidate_sources",
        ["is_official", "trust_tier"],
    )

    op.create_table(
        "catalogue_extraction_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            _enum(
                "catalogue_extraction_attempt_status",
                "succeeded",
                "provider_failed",
                "schema_failed",
                "validation_failed",
                "reused",
            ),
            nullable=False,
        ),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["catalogue_candidate_sources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "source_id",
            "content_hash",
            "schema_version",
            "provider",
            "model",
            name="uq_catalogue_extraction_version",
        ),
    )
    op.create_index(
        op.f("ix_catalogue_extraction_attempts_candidate_id"),
        "catalogue_extraction_attempts",
        ["candidate_id"],
    )
    op.create_index(
        op.f("ix_catalogue_extraction_attempts_source_id"),
        "catalogue_extraction_attempts",
        ["source_id"],
    )
    op.create_index(
        "ix_catalogue_extraction_attempts_status_created",
        "catalogue_extraction_attempts",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalogue_extraction_attempts_status_created",
        table_name="catalogue_extraction_attempts",
    )
    op.drop_index(
        op.f("ix_catalogue_extraction_attempts_source_id"),
        table_name="catalogue_extraction_attempts",
    )
    op.drop_index(
        op.f("ix_catalogue_extraction_attempts_candidate_id"),
        table_name="catalogue_extraction_attempts",
    )
    op.drop_table("catalogue_extraction_attempts")
    op.drop_index(
        "ix_catalogue_candidate_sources_official", table_name="catalogue_candidate_sources"
    )
    op.drop_index("ix_catalogue_candidate_sources_hash", table_name="catalogue_candidate_sources")
    op.drop_index(
        op.f("ix_catalogue_candidate_sources_is_official"), table_name="catalogue_candidate_sources"
    )
    op.drop_index(
        op.f("ix_catalogue_candidate_sources_candidate_id"),
        table_name="catalogue_candidate_sources",
    )
    op.drop_table("catalogue_candidate_sources")
    op.drop_index("ix_catalogue_candidates_run_seed", table_name="catalogue_candidates")
    op.drop_index("ix_catalogue_candidates_claim", table_name="catalogue_candidates")
    for column in reversed(
        ("run_id", "status", "next_attempt_at", "claimed_until", "opportunity_id")
    ):
        op.drop_index(op.f(f"ix_catalogue_candidates_{column}"), table_name="catalogue_candidates")
    op.drop_table("catalogue_candidates")
    op.drop_index(
        "ix_catalogue_ingestion_runs_status_created", table_name="catalogue_ingestion_runs"
    )
    op.drop_index(op.f("ix_catalogue_ingestion_runs_status"), table_name="catalogue_ingestion_runs")
    op.drop_index(
        op.f("ix_catalogue_ingestion_runs_source_fingerprint"),
        table_name="catalogue_ingestion_runs",
    )
    op.drop_table("catalogue_ingestion_runs")
    op.drop_index("ix_sources_monitor_claim", table_name="sources")
    op.drop_index(op.f("ix_sources_monitor_next_check_at"), table_name="sources")
    op.drop_column("sources", "monitor_failure_count")
    op.drop_column("sources", "monitor_claimed_until")
    op.drop_column("sources", "monitor_next_check_at")
