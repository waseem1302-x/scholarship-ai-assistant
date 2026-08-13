"""Record versioned beta terms and privacy acceptance.

Revision ID: 20260813_0017
Revises: 20260813_0016
Create Date: 2026-08-13
"""

import sqlalchemy as sa

from alembic import op

revision = "20260813_0017"
down_revision = "20260813_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "beta_legal_acceptances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("terms_version", sa.String(length=100), nullable=False),
        sa.Column("privacy_notice_version", sa.String(length=100), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "terms_version",
            "privacy_notice_version",
            name="uq_beta_legal_acceptance_version",
        ),
    )
    op.create_index("ix_beta_legal_acceptances_user_id", "beta_legal_acceptances", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_beta_legal_acceptances_user_id", table_name="beta_legal_acceptances")
    op.drop_table("beta_legal_acceptances")
