"""Add review-only scholarship relationship classification decisions.

Revision ID: 20260817_0040
Revises: 20260817_0039
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260817_0040"
down_revision = "20260817_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "classification_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "proposed_relationship",
            _enum(
                "classification_relationship_kind",
                "same_scholarship",
                "same_scheme_track",
                "participating_institution",
                "eligible_programme",
                "institution_specific_requirement",
                "institution_specific_deadline",
                "independent_university_scholarship",
                "independent_government_scholarship",
                "independent_foundation_scholarship",
                "co_funded_award",
                "successor",
                "predecessor",
                "duplicate",
                "unresolved",
            ),
            nullable=False,
        ),
        sa.Column("parent_scholarship_id", sa.Uuid(), nullable=True),
        sa.Column("proposed_new_scholarship_id", sa.Uuid(), nullable=True),
        sa.Column("deterministic_signals", sa.JSON(), nullable=False),
        sa.Column("model_output", sa.JSON(), nullable=True),
        sa.Column(
            "confidence_band",
            _enum("classification_confidence_band", "high", "medium", "unresolved"),
            nullable=False,
        ),
        sa.Column("evidence_snapshot_ids", sa.JSON(), nullable=False),
        sa.Column(
            "decision_status",
            _enum(
                "classification_decision_status",
                "needs_review",
                "approved",
                "rejected",
                "superseded",
            ),
            nullable=False,
            server_default="needs_review",
        ),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["catalogue_candidates.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_scholarship_id"],
            ["opportunities.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_new_scholarship_id"],
            ["opportunities.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "candidate_id",
        "proposed_relationship",
        "parent_scholarship_id",
        "proposed_new_scholarship_id",
        "confidence_band",
        "decision_status",
        "reviewer_id",
    ):
        op.create_index(
            op.f(f"ix_classification_decisions_{column}"),
            "classification_decisions",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_classification_decisions_candidate_created",
        "classification_decisions",
        ["candidate_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_classification_decisions_status_created",
        "classification_decisions",
        ["decision_status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_classification_decisions_relationship_status",
        "classification_decisions",
        ["proposed_relationship", "decision_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_classification_decisions_relationship_status",
        table_name="classification_decisions",
    )
    op.drop_index(
        "ix_classification_decisions_status_created",
        table_name="classification_decisions",
    )
    op.drop_index(
        "ix_classification_decisions_candidate_created",
        table_name="classification_decisions",
    )
    for column in reversed(
        (
            "candidate_id",
            "proposed_relationship",
            "parent_scholarship_id",
            "proposed_new_scholarship_id",
            "confidence_band",
            "decision_status",
            "reviewer_id",
        )
    ):
        op.drop_index(
            op.f(f"ix_classification_decisions_{column}"),
            table_name="classification_decisions",
        )
    op.drop_table("classification_decisions")
