"""Create saved opportunities application tracker.

Revision ID: 20260722_0004
Revises: 20260722_0003
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260722_0004"
down_revision: str | None = "20260722_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum_values(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "saved_opportunities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            enum_values(
                "interested",
                "researching",
                "preparing_documents",
                "waiting_for_recommendation",
                "ready_to_apply",
                "submitted",
                "interview_stage",
                "accepted",
                "rejected",
                "withdrawn",
                "expired",
                name="application_status",
            ),
            nullable=False,
        ),
        sa.Column("personal_notes", sa.Text(), nullable=True),
        sa.Column("personal_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_checklist", sa.JSON(), nullable=False),
        sa.Column("recommendation_letters", sa.JSON(), nullable=False),
        sa.Column("test_requirements", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "opportunity_id", name="uq_saved_opportunities_user_opportunity"
        ),
    )
    op.create_index(
        op.f("ix_saved_opportunities_opportunity_id"),
        "saved_opportunities",
        ["opportunity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_saved_opportunities_personal_deadline"),
        "saved_opportunities",
        ["personal_deadline"],
        unique=False,
    )
    op.create_index(
        op.f("ix_saved_opportunities_status"),
        "saved_opportunities",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_saved_opportunities_user_id"),
        "saved_opportunities",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_saved_opportunities_user_status",
        "saved_opportunities",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_saved_opportunities_user_status", table_name="saved_opportunities")
    op.drop_index(op.f("ix_saved_opportunities_user_id"), table_name="saved_opportunities")
    op.drop_index(op.f("ix_saved_opportunities_status"), table_name="saved_opportunities")
    op.drop_index(
        op.f("ix_saved_opportunities_personal_deadline"), table_name="saved_opportunities"
    )
    op.drop_index(op.f("ix_saved_opportunities_opportunity_id"), table_name="saved_opportunities")
    op.drop_table("saved_opportunities")
