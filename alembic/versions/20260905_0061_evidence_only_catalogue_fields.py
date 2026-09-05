"""allow scholarship-level institutions and unknown deadline timezones

Revision ID: 20260905_0061
Revises: 20260904_0060
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260905_0061"
down_revision: str | None = "20260904_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("institution_participations") as batch_op:
        batch_op.alter_column(
            "track_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )
    with op.batch_alter_table("scoped_deadlines") as batch_op:
        batch_op.alter_column(
            "timezone",
            existing_type=sa.String(length=64),
            nullable=True,
            server_default=None,
        )


def downgrade() -> None:
    # Downgrade deliberately fails if new rows contain NULL in either column; callers must
    # resolve those values rather than having the migration invent a track or timezone.
    with op.batch_alter_table("scoped_deadlines") as batch_op:
        batch_op.alter_column(
            "timezone",
            existing_type=sa.String(length=64),
            nullable=False,
            server_default="UTC",
        )
    with op.batch_alter_table("institution_participations") as batch_op:
        batch_op.alter_column(
            "track_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
