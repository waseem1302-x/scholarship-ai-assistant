"""Reserve beta invitations until the invited email is verified.

Revision ID: 20260813_0019
Revises: 20260813_0018
Create Date: 2026-08-13
"""

import sqlalchemy as sa

from alembic import op

revision = "20260813_0019"
down_revision = "20260813_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode keeps this portable to the SQLite migration verification suite.
    with op.batch_alter_table("beta_invitations") as batch_op:
        batch_op.add_column(sa.Column("reserved_by_user_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_beta_invitations_reserved_by_user_id_users",
            "users",
            ["reserved_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_beta_invitations_reserved_by_user_id", ["reserved_by_user_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("beta_invitations") as batch_op:
        batch_op.drop_constraint("uq_beta_invitations_reserved_by_user_id", type_="unique")
        batch_op.drop_constraint(
            "fk_beta_invitations_reserved_by_user_id_users", type_="foreignkey"
        )
        batch_op.drop_column("reserved_at")
        batch_op.drop_column("reserved_by_user_id")
