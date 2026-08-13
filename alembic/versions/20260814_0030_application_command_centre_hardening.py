"""Harden application command centre concurrency and idempotency.

Revision ID: 20260814_0030
Revises: 20260814_0029
Create Date: 2026-08-14
"""

from alembic import op

revision = "20260814_0030"
down_revision = "20260814_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("application_reminders") as batch_op:
        batch_op.drop_constraint("uq_application_reminders_idempotency", type_="unique")
        batch_op.create_unique_constraint(
            "uq_application_reminders_application_idempotency",
            ["application_id", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("application_reminders") as batch_op:
        batch_op.drop_constraint(
            "uq_application_reminders_application_idempotency", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_application_reminders_idempotency", ["idempotency_key"]
        )
