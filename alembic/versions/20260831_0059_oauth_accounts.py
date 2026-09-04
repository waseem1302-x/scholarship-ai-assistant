"""Add oauth_accounts table and make users.password_hash nullable for social login.

Revision ID: 20260831_0059
Revises: 20260830_0058
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0059"
down_revision: str | None = "20260830_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Allow nullable password_hash on users table
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=255),
            nullable=True,
        )

    # 2. Create oauth_accounts table
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("provider_email", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )
    op.create_index("ix_oauth_accounts_provider", "oauth_accounts", ["provider"])
    op.create_index("ix_oauth_accounts_provider_user_id", "oauth_accounts", ["provider_user_id"])
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])
    op.create_index("ix_oauth_user_provider", "oauth_accounts", ["user_id", "provider"])


def downgrade() -> None:
    op.drop_index("ix_oauth_user_provider", table_name="oauth_accounts")
    op.drop_index("ix_oauth_accounts_user_id", table_name="oauth_accounts")
    op.drop_index("ix_oauth_accounts_provider_user_id", table_name="oauth_accounts")
    op.drop_index("ix_oauth_accounts_provider", table_name="oauth_accounts")
    op.drop_table("oauth_accounts")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=255),
            nullable=False,
        )
