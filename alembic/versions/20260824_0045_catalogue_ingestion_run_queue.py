"""add durable fenced queue fields to catalogue ingestion runs

Revision ID: 20260824_0045
Revises: 20260823_0044
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0045"
down_revision: str | None = "20260823_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


run_stage = sa.Enum(
    "queued",
    "acquiring",
    "extracting",
    "resolving",
    "complete",
    "dead_letter",
    name="catalogue_ingestion_run_stage",
    native_enum=False,
    create_constraint=True,
)
retry_class = sa.Enum(
    "transient",
    "permanent",
    name="catalogue_ingestion_run_retry_class",
    native_enum=False,
    create_constraint=True,
)
previous_run_status = sa.Enum(
    "pending",
    "running",
    "completed",
    "failed",
    "budget_exhausted",
    name="catalogue_ingestion_run_status",
    native_enum=False,
    create_constraint=True,
)
run_status = sa.Enum(
    "pending",
    "running",
    "completed",
    "failed",
    "budget_exhausted",
    "dead_letter",
    name="catalogue_ingestion_run_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.alter_column(
            "status", existing_type=previous_run_status, type_=run_status, existing_nullable=False
        )
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("stage", run_stage, nullable=False, server_default="queued"))
        batch_op.add_column(sa.Column("last_error_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("retry_class", retry_class, nullable=True))
        batch_op.add_column(
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3")
        )
        batch_op.add_column(
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("claimed_by", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("lease_token", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True)
        )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "UPDATE catalogue_ingestion_runs "
            "SET idempotency_key = 'legacy:' || CAST(id AS TEXT) "
            "WHERE idempotency_key IS NULL"
        )
    else:
        op.execute(
            "UPDATE catalogue_ingestion_runs "
            "SET idempotency_key = 'legacy:' || id "
            "WHERE idempotency_key IS NULL"
        )

    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.alter_column(
            "idempotency_key", existing_type=sa.String(length=128), nullable=False
        )
        batch_op.create_unique_constraint(
            "uq_catalogue_ingestion_runs_idempotency", ["idempotency_key"]
        )
        batch_op.create_index(
            "ix_catalogue_ingestion_runs_claim",
            ["status", "next_attempt_at", "claimed_until", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_catalogue_ingestion_runs_lease_token", ["lease_token"], unique=False
        )


def downgrade() -> None:
    op.execute("UPDATE catalogue_ingestion_runs SET status = 'failed' WHERE status = 'dead_letter'")
    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.drop_index("ix_catalogue_ingestion_runs_lease_token")
        batch_op.drop_index("ix_catalogue_ingestion_runs_claim")
        batch_op.drop_constraint("uq_catalogue_ingestion_runs_idempotency", type_="unique")
        batch_op.drop_constraint("catalogue_ingestion_run_retry_class", type_="check")
        batch_op.drop_constraint("catalogue_ingestion_run_stage", type_="check")
        batch_op.drop_column("dead_lettered_at")
        batch_op.drop_column("lease_token")
        batch_op.drop_column("claimed_until")
        batch_op.drop_column("claimed_at")
        batch_op.drop_column("claimed_by")
        batch_op.drop_column("next_attempt_at")
        batch_op.drop_column("attempt_count")
        batch_op.drop_column("max_attempts")
        batch_op.drop_column("retry_class")
        batch_op.drop_column("last_error_reason")
        batch_op.drop_column("stage")
        batch_op.drop_column("idempotency_key")
        batch_op.alter_column(
            "status", existing_type=run_status, type_=previous_run_status, existing_nullable=False
        )
