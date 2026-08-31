"""Add rate-aware provider scheduling and circuit-breaker state.

Revision ID: 20260830_0058
Revises: 20260830_0057
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0058"
down_revision: str | None = "20260830_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalogue_provider_lanes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("deployment", sa.String(length=255), nullable=False),
        sa.Column("last_admitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "deployment", name="uq_catalogue_provider_lane"),
    )
    op.create_index(
        "ix_catalogue_provider_lanes_provider", "catalogue_provider_lanes", ["provider"]
    )
    op.create_table(
        "catalogue_provider_circuits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lane_id", sa.Uuid(), nullable=False),
        sa.Column("failure_class", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("opened_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["lane_id"], ["catalogue_provider_lanes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lane_id", "failure_class", name="uq_catalogue_provider_circuit_failure_class"
        ),
    )
    op.create_index(
        "ix_catalogue_provider_circuits_lane_id", "catalogue_provider_circuits", ["lane_id"]
    )
    op.create_index(
        "ix_catalogue_provider_circuits_failure_class",
        "catalogue_provider_circuits",
        ["failure_class"],
    )
    op.create_index(
        "ix_catalogue_provider_circuits_state", "catalogue_provider_circuits", ["state"]
    )
    op.create_index(
        "ix_catalogue_provider_circuits_opened_until",
        "catalogue_provider_circuits",
        ["opened_until"],
    )
    op.create_index(
        "ix_catalogue_provider_circuits_state_until",
        "catalogue_provider_circuits",
        ["state", "opened_until"],
    )
    op.create_table(
        "catalogue_scheduling_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("logical_job_key", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("deployment", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("active_attempts", sa.Integer(), nullable=False),
        sa.Column("concurrency_limit", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["catalogue_ingestion_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalogue_scheduling_decisions_run_id", "catalogue_scheduling_decisions", ["run_id"]
    )
    op.create_index(
        "ix_catalogue_scheduling_decisions_candidate_id",
        "catalogue_scheduling_decisions",
        ["candidate_id"],
    )
    op.create_index(
        "ix_catalogue_scheduling_decisions_logical_job_key",
        "catalogue_scheduling_decisions",
        ["logical_job_key"],
    )
    op.create_index(
        "ix_catalogue_scheduling_decisions_decision", "catalogue_scheduling_decisions", ["decision"]
    )
    op.create_index(
        "ix_catalogue_scheduling_decisions_run_created",
        "catalogue_scheduling_decisions",
        ["run_id", "created_at"],
    )
    op.create_index(
        "ix_catalogue_scheduling_decisions_candidate_created",
        "catalogue_scheduling_decisions",
        ["candidate_id", "created_at"],
    )
    op.create_index(
        "ix_catalogue_scheduling_decisions_lane_created",
        "catalogue_scheduling_decisions",
        ["provider", "deployment", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("catalogue_scheduling_decisions")
    op.drop_table("catalogue_provider_circuits")
    op.drop_table("catalogue_provider_lanes")
