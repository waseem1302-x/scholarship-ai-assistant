"""Add safe health state for Phase 9 scheduled jobs.

Revision ID: 20260813_0018
Revises: 20260813_0017
Create Date: 2026-08-13
"""

import sqlalchemy as sa

from alembic import op

revision = "20260813_0018"
down_revision = "20260813_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operational_job_health",
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_name"),
    )


def downgrade() -> None:
    op.drop_table("operational_job_health")
