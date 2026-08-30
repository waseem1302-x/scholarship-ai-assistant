"""add durable candidate proposal review and materialization state

Revision ID: 20260830_0053
Revises: 20260830_0052
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0053"
down_revision: str | None = "20260830_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "catalogue_candidate_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "state",
            _enum(
                "catalogue_proposal_state",
                "draft",
                "needs_review",
                "submitted",
                "approved",
                "rejected",
                "needs_changes",
                "materializing",
                "materialized",
                "publication_ready",
                "published",
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("proposal_schema_version", sa.String(length=100), nullable=True),
        sa.Column("proposal_hash", sa.String(length=64), nullable=True),
        sa.Column("approved_proposal_hash", sa.String(length=64), nullable=True),
        sa.Column("review_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("materialization_revision", sa.String(length=100), nullable=True),
        sa.Column("materialization_attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("materialization_failure_code", sa.String(length=100), nullable=True),
        sa.Column("materialization_failure_reason", sa.Text(), nullable=True),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publication_ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "review_revision >= 1", name="ck_catalogue_candidate_reviews_revision_positive"
        ),
        sa.CheckConstraint(
            "materialization_attempt_count >= 0",
            name="ck_catalogue_candidate_reviews_materialization_attempt_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", name="uq_catalogue_candidate_reviews_candidate"),
    )
    for column in (
        "candidate_id",
        "state",
        "reviewed_by_user_id",
        "materialization_revision",
    ):
        op.create_index(
            op.f(f"ix_catalogue_candidate_reviews_{column}"),
            "catalogue_candidate_reviews",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_catalogue_candidate_reviews_state_updated",
        "catalogue_candidate_reviews",
        ["state", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_candidate_reviews_proposal_hash",
        "catalogue_candidate_reviews",
        ["proposal_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("catalogue_candidate_reviews")
