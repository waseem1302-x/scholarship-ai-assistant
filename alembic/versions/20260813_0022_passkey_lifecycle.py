"""Add administrator passkey lifecycle metadata.

Revision ID: 20260813_0022
Revises: 20260813_0021
Create Date: 2026-08-13
"""

import sqlalchemy as sa

from alembic import op

revision = "20260813_0022"
down_revision = "20260813_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("webauthn_credentials") as batch_op:
        batch_op.add_column(
            sa.Column(
                "display_name", sa.String(length=100), nullable=False, server_default="New passkey"
            )
        )
        batch_op.add_column(sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("webauthn_credentials") as batch_op:
        batch_op.drop_column("revoked_at")
        batch_op.drop_column("display_name")
