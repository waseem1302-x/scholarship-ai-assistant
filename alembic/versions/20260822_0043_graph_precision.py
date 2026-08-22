"""add graph precision fields and multi-level scholarship projection

Revision ID: 20260822_0043
Revises: 20260822_0042
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0043"
down_revision: str | None = "20260822_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.add_column(
            sa.Column(
                "degree_levels",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )
    with op.batch_alter_table("scoped_deadlines") as batch_op:
        batch_op.add_column(sa.Column("local_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "deadline_precision",
                sa.String(length=16),
                nullable=False,
                server_default="datetime",
            )
        )
    with op.batch_alter_table("funding_components") as batch_op:
        batch_op.add_column(sa.Column("frequency", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("funding_components") as batch_op:
        batch_op.drop_column("frequency")
    with op.batch_alter_table("scoped_deadlines") as batch_op:
        batch_op.drop_column("deadline_precision")
        batch_op.drop_column("local_date")
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.drop_column("degree_levels")
