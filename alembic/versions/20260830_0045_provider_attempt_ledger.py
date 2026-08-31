"""add provider attempt ledger and run configuration identity

Revision ID: 20260830_0045
Revises: 20260823_0044
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0045"
down_revision: str | None = "20260823_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.add_column(
            sa.Column("configuration_revision", sa.String(length=100), nullable=True)
        )
        batch_op.add_column(
            sa.Column("configuration_fingerprint", sa.String(length=64), nullable=True)
        )
        batch_op.create_index(
            "ix_catalogue_ingestion_runs_configuration_fingerprint",
            ["configuration_fingerprint"],
            unique=False,
        )

    op.create_table(
        "catalogue_provider_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("extraction_job_key", sa.String(length=128), nullable=False),
        sa.Column("objective", sa.String(length=100), nullable=True),
        sa.Column("objective_bundle", sa.JSON(), nullable=False),
        sa.Column("evidence_block_keys", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("deployment", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=False),
        sa.Column("normalizer_version", sa.String(length=100), nullable=False),
        sa.Column("retry_ordinal", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("lease_token", sa.String(length=100), nullable=True),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column(
            "state",
            _enum(
                "catalogue_provider_attempt_state",
                "reserved",
                "dispatching",
                "dispatched",
                "succeeded",
                "failed",
            ),
            nullable=False,
        ),
        sa.Column(
            "failure_class",
            _enum(
                "catalogue_provider_failure_class",
                "pre_dispatch_failure",
                "connection_establishment_failure",
                "post_dispatch_response_interruption",
                "timeout",
                "rate_limit",
                "provider_server_error",
                "authentication_configuration_error",
                "malformed_provider_response",
                "schema_validation_failure",
                "safety_refusal",
                "budget_rejection",
                "lease_loss",
                "cancelled_by_kill_switch",
                "unknown_potentially_billable_failure",
            ),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("safe_error_detail", sa.Text(), nullable=True),
        sa.Column(
            "accounting_state",
            _enum(
                "catalogue_provider_accounting_state",
                "not_billable",
                "exact",
                "estimated",
                "unknown_potentially_billable",
            ),
            nullable=False,
        ),
        sa.Column("reserved_cost_upper", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("cost_lower_bound", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("cost_upper_bound", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("dispatch_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["catalogue_ingestion_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["extraction_attempt_id"], ["catalogue_extraction_attempts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["catalogue_candidate_sources.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["catalogue_source_artifacts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extraction_job_key",
            "retry_ordinal",
            name="uq_catalogue_provider_attempt_job_retry",
        ),
    )

    for column in (
        "run_id",
        "candidate_id",
        "extraction_attempt_id",
        "source_id",
        "source_artifact_id",
        "extraction_job_key",
        "objective",
        "provider_request_id",
        "state",
        "failure_class",
        "accounting_state",
    ):
        op.create_index(
            op.f(f"ix_catalogue_provider_attempts_{column}"),
            "catalogue_provider_attempts",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_catalogue_provider_attempts_run_state",
        "catalogue_provider_attempts",
        ["run_id", "state", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_provider_attempts_candidate_state",
        "catalogue_provider_attempts",
        ["candidate_id", "state", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_provider_attempts_candidate_objective",
        "catalogue_provider_attempts",
        ["candidate_id", "objective", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_provider_attempts_artifact",
        "catalogue_provider_attempts",
        ["source_artifact_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_provider_attempts_accounting",
        "catalogue_provider_attempts",
        ["accounting_state", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("catalogue_provider_attempts")
    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.drop_index("ix_catalogue_ingestion_runs_configuration_fingerprint")
        batch_op.drop_column("configuration_fingerprint")
        batch_op.drop_column("configuration_revision")
