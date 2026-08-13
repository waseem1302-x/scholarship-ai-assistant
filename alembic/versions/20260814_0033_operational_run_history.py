"""Persist safe operational job run history.

Revision ID: 20260814_0033
Revises: 20260814_0032
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260814_0033"
down_revision = "20260814_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_job_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_name",
            sa.String(100),
            sa.ForeignKey("operational_job_health.job_name", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100)),
        sa.Column("release_version", sa.String(100), nullable=False, server_default="unknown"),
    )
    op.create_index("ix_operational_job_runs_job_name", "operational_job_runs", ["job_name"])
    op.create_index(
        "ix_operational_job_runs_job_started",
        "operational_job_runs",
        ["job_name", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("operational_job_runs")
