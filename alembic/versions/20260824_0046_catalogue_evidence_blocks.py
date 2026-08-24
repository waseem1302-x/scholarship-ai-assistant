"""add immutable deterministic catalogue evidence blocks

Revision ID: 20260824_0046
Revises: 20260824_0045
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0046"
down_revision: str | None = "20260824_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalogue_evidence_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("block_id", sa.String(length=64), nullable=False),
        sa.Column("canonicalization_version", sa.String(length=64), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["catalogue_source_artifacts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "block_index", name="uq_catalogue_evidence_block_index"),
        sa.UniqueConstraint("artifact_id", "block_id", name="uq_catalogue_evidence_block_id"),
    )
    op.create_index(
        "ix_catalogue_evidence_blocks_artifact_id", "catalogue_evidence_blocks", ["artifact_id"]
    )
    op.create_index(
        "ix_catalogue_evidence_blocks_artifact_offsets",
        "catalogue_evidence_blocks",
        ["artifact_id", "start_offset"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalogue_evidence_blocks_artifact_offsets", table_name="catalogue_evidence_blocks"
    )
    op.drop_index(
        "ix_catalogue_evidence_blocks_artifact_id", table_name="catalogue_evidence_blocks"
    )
    op.drop_table("catalogue_evidence_blocks")
