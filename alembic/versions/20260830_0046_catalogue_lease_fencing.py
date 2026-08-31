"""add lease fencing, terminal run outcomes, and resumable jobs

Revision ID: 20260830_0046
Revises: 20260830_0045
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0046"
down_revision: str | None = "20260830_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


_RUN_STATUS_VALUES = (
    "pending",
    "running",
    "completed",
    "completed_with_review",
    "completed_with_failures",
    "failed",
    "cancelled",
    "budget_exhausted",
)

_OLD_RUN_STATUS_VALUES = (
    "pending",
    "running",
    "completed",
    "failed",
    "budget_exhausted",
)


def upgrade() -> None:
    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.drop_constraint("catalogue_ingestion_run_status", type_="check")
        batch_op.create_check_constraint(
            "catalogue_ingestion_run_status",
            "status IN (" + ", ".join(f"'{value}'" for value in _RUN_STATUS_VALUES) + ")",
        )
        batch_op.add_column(sa.Column("lease_token", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            "ix_catalogue_ingestion_runs_lease_token", ["lease_token"], unique=False
        )
        batch_op.create_index(
            "ix_catalogue_ingestion_runs_lease_expires_at", ["lease_expires_at"], unique=False
        )

    with op.batch_alter_table("catalogue_candidates") as batch_op:
        batch_op.add_column(sa.Column("lease_token", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_catalogue_candidates_lease_token", ["lease_token"], unique=False)

    op.create_table(
        "catalogue_resumable_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("job_key", sa.String(length=128), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=False),
        sa.Column(
            "state",
            _enum(
                "catalogue_resumable_job_state",
                "pending",
                "running",
                "succeeded",
                "failed",
                "lease_lost",
                "cancelled",
            ),
            nullable=False,
        ),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("run_lease_token", sa.String(length=64), nullable=True),
        sa.Column("candidate_lease_token", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["catalogue_ingestion_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_key", name="uq_catalogue_resumable_jobs_key"),
    )
    for column in ("run_id", "candidate_id", "job_key", "stage", "state"):
        op.create_index(
            op.f(f"ix_catalogue_resumable_jobs_{column}"),
            "catalogue_resumable_jobs",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_catalogue_resumable_jobs_run_state",
        "catalogue_resumable_jobs",
        ["run_id", "state", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_resumable_jobs_candidate_stage",
        "catalogue_resumable_jobs",
        ["candidate_id", "stage", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("catalogue_resumable_jobs")

    with op.batch_alter_table("catalogue_candidates") as batch_op:
        batch_op.drop_index("ix_catalogue_candidates_lease_token")
        batch_op.drop_column("lease_token")

    op.execute(
        sa.text(
            "UPDATE catalogue_ingestion_runs SET status = 'completed' "
            "WHERE status IN ('completed_with_review', 'completed_with_failures')"
        )
    )
    op.execute(
        sa.text("UPDATE catalogue_ingestion_runs SET status = 'failed' WHERE status = 'cancelled'")
    )
    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.drop_index("ix_catalogue_ingestion_runs_lease_expires_at")
        batch_op.drop_index("ix_catalogue_ingestion_runs_lease_token")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("lease_token")
        batch_op.drop_constraint("catalogue_ingestion_run_status", type_="check")
        batch_op.create_check_constraint(
            "catalogue_ingestion_run_status",
            "status IN (" + ", ".join(f"'{value}'" for value in _OLD_RUN_STATUS_VALUES) + ")",
        )
