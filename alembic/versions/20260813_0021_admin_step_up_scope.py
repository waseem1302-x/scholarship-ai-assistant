"""Scope reusable short-lived administrator step-up sessions.

Revision ID: 20260813_0021
Revises: 20260813_0020
Create Date: 2026-08-13
"""

import sqlalchemy as sa

from alembic import op

revision = "20260813_0021"
down_revision = "20260813_0020"
branch_labels = None
depends_on = None

DEFAULT_SCOPE = "admin_sensitive_operations"


def upgrade() -> None:
    with op.batch_alter_table("admin_step_up_tokens") as batch_op:
        batch_op.add_column(
            sa.Column("scope", sa.String(length=64), nullable=False, server_default=DEFAULT_SCOPE)
        )


def downgrade() -> None:
    with op.batch_alter_table("admin_step_up_tokens") as batch_op:
        batch_op.drop_column("scope")
