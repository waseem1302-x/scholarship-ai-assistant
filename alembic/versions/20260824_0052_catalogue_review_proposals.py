"""add immutable catalogue review proposal and decision lineage

Revision ID: 20260824_0052
Revises: 20260824_0051
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0052"
down_revision: str | None = "20260824_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalogue_review_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("payload_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_versions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id", "proposal_hash", name="uq_catalogue_review_proposal_hash"
        ),
    )
    op.create_index(
        "ix_catalogue_review_proposals_candidate_created",
        "catalogue_review_proposals",
        ["candidate_id", "created_at"],
    )
    op.create_table(
        "catalogue_review_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.Column("prior_candidate_status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["catalogue_review_proposals.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalogue_review_decisions_proposal_created",
        "catalogue_review_decisions",
        ["proposal_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalogue_review_decisions_proposal_created", table_name="catalogue_review_decisions"
    )
    op.drop_table("catalogue_review_decisions")
    op.drop_index(
        "ix_catalogue_review_proposals_candidate_created", table_name="catalogue_review_proposals"
    )
    op.drop_table("catalogue_review_proposals")
