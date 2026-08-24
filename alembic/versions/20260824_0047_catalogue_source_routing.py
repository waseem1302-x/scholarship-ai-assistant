"""persist deterministic catalogue source routing decisions

Revision ID: 20260824_0047
Revises: 20260824_0046
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0047"
down_revision: str | None = "20260824_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalogue_source_routing_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("classifier_version", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("cycle", sa.String(length=32), nullable=False),
        sa.Column("deterministic_signals", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("ambiguity_reason", sa.String(length=255), nullable=True),
        sa.Column("requires_manual_review", sa.Boolean(), nullable=False),
        sa.Column("applicable_objectives", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["catalogue_source_artifacts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_id", "classifier_version", name="uq_catalogue_source_routing_artifact_version"
        ),
    )
    op.create_index(
        "ix_catalogue_source_routing_role_cycle",
        "catalogue_source_routing_decisions",
        ["role", "cycle"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalogue_source_routing_role_cycle", table_name="catalogue_source_routing_decisions"
    )
    op.drop_table("catalogue_source_routing_decisions")
