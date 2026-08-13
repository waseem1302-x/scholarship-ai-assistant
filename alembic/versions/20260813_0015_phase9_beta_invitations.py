"""Add durable Phase 9 beta invitations.

Revision ID: 20260813_0015
Revises: 20260813_0014
Create Date: 2026-08-13
"""

import sqlalchemy as sa

from alembic import op

revision = "20260813_0015"
down_revision = "20260813_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "beta_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "redeemed",
                "revoked",
                "expired",
                name="beta_invitation_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("max_redemptions", sa.Integer(), nullable=False),
        sa.Column("redemption_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("redeemed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["redeemed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
        sa.UniqueConstraint("redeemed_by_user_id"),
    )
    op.create_index("ix_beta_invitations_email", "beta_invitations", ["email"])
    op.create_index("ix_beta_invitations_code_hash", "beta_invitations", ["code_hash"])
    op.create_index("ix_beta_invitations_expires_at", "beta_invitations", ["expires_at"])
    op.create_index(
        "ix_beta_invitations_created_by_user_id",
        "beta_invitations",
        ["created_by_user_id"],
    )
    op.create_index("ix_beta_invitations_email_status", "beta_invitations", ["email", "status"])


def downgrade() -> None:
    op.drop_index("ix_beta_invitations_email_status", table_name="beta_invitations")
    op.drop_index("ix_beta_invitations_created_by_user_id", table_name="beta_invitations")
    op.drop_index("ix_beta_invitations_expires_at", table_name="beta_invitations")
    op.drop_index("ix_beta_invitations_code_hash", table_name="beta_invitations")
    op.drop_index("ix_beta_invitations_email", table_name="beta_invitations")
    op.drop_table("beta_invitations")
