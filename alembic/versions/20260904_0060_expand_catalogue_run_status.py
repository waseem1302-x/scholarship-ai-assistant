"""expand catalogue ingestion run status storage

Revision ID: 20260904_0060
Revises: 20260831_0059
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260904_0060"
down_revision: str | None = "20260831_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=16),
            type_=sa.String(length=23),
            existing_nullable=False,
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE catalogue_ingestion_runs SET status = 'completed' "
            "WHERE status = 'completed_with_review'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE catalogue_ingestion_runs SET status = 'failed' "
            "WHERE status = 'completed_with_failures'"
        )
    )
    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=23),
            type_=sa.String(length=16),
            existing_nullable=False,
        )
