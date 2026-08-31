"""allow evidence-backed text-only scoped deadlines

Revision ID: 20260830_0055
Revises: 20260830_0054
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0055"
down_revision: str | None = "20260830_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scoped_deadlines") as batch_op:
        batch_op.alter_column(
            "deadline_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )


def downgrade() -> None:
    # This intentionally fails rather than inventing timestamps if text-only
    # deadlines exist. Operators must resolve such rows before downgrading.
    with op.batch_alter_table("scoped_deadlines") as batch_op:
        batch_op.alter_column(
            "deadline_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
