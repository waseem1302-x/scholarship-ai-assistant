"""add append-only catalogue acquisition snapshots

Revision ID: 20260830_0048
Revises: 20260830_0047
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0048"
down_revision: str | None = "20260830_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalogue_acquisition_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "revision",
            sa.String(length=100),
            nullable=False,
            server_default="catalogue-acquisition.v1",
        ),
        sa.Column("coverage_revision", sa.String(length=100), nullable=True),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("budget_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["catalogue_ingestion_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_catalogue_acquisition_snapshots_run_id"),
        "catalogue_acquisition_snapshots",
        ["run_id"],
    )
    op.create_index(
        op.f("ix_catalogue_acquisition_snapshots_candidate_id"),
        "catalogue_acquisition_snapshots",
        ["candidate_id"],
    )
    op.create_index(
        "ix_catalogue_acquisition_snapshots_candidate_created",
        "catalogue_acquisition_snapshots",
        ["candidate_id", "created_at"],
    )
    op.create_index(
        "ix_catalogue_acquisition_snapshots_run_created",
        "catalogue_acquisition_snapshots",
        ["run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("catalogue_acquisition_snapshots")
