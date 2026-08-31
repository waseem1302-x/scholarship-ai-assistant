"""Add explicit human review state for discovery leads.

Revision ID: 20260830_0057
Revises: 20260830_0056
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0057"
down_revision: str | None = "20260830_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("catalogue_discovery_leads") as batch_op:
        batch_op.add_column(
            sa.Column(
                "review_status",
                sa.String(length=32),
                server_default="pending",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("review_reason", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_catalogue_discovery_leads_reviewer",
            "users",
            ["reviewed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_catalogue_discovery_leads_review_status",
            ["review_status"],
            unique=False,
        )
        batch_op.create_index(
            "ix_catalogue_discovery_leads_reviewed_by_user_id",
            ["reviewed_by_user_id"],
            unique=False,
        )
        batch_op.create_check_constraint(
            "ck_catalogue_discovery_lead_review_status",
            "review_status IN ('pending', 'approved', 'rejected')",
        )


def downgrade() -> None:
    with op.batch_alter_table("catalogue_discovery_leads") as batch_op:
        batch_op.drop_constraint("ck_catalogue_discovery_lead_review_status", type_="check")
        batch_op.drop_index("ix_catalogue_discovery_leads_reviewed_by_user_id")
        batch_op.drop_index("ix_catalogue_discovery_leads_review_status")
        batch_op.drop_constraint("fk_catalogue_discovery_leads_reviewer", type_="foreignkey")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by_user_id")
        batch_op.drop_column("review_reason")
        batch_op.drop_column("review_status")
