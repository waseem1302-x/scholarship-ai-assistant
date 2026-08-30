"""add logical job identity to catalogue extraction attempts

Revision ID: 20260830_0052
Revises: 20260830_0051
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0052"
down_revision: str | None = "20260830_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "uq_catalogue_extraction_version"
_INDEX = "ix_catalogue_extraction_attempts_extraction_job_key"
_OLD_COLUMNS = (
    "candidate_id",
    "source_id",
    "content_hash",
    "schema_version",
    "prompt_hash",
    "provider",
    "model",
)
_NEW_COLUMNS = (*_OLD_COLUMNS, "extraction_job_key")


def upgrade() -> None:
    op.add_column(
        "catalogue_extraction_attempts",
        sa.Column("extraction_job_key", sa.String(length=64), server_default="", nullable=False),
    )
    op.create_index(
        _INDEX,
        "catalogue_extraction_attempts",
        ["extraction_job_key"],
        unique=False,
    )
    op.drop_constraint(_CONSTRAINT, "catalogue_extraction_attempts", type_="unique")
    op.create_unique_constraint(
        _CONSTRAINT,
        "catalogue_extraction_attempts",
        list(_NEW_COLUMNS),
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "catalogue_extraction_attempts", type_="unique")
    op.create_unique_constraint(
        _CONSTRAINT,
        "catalogue_extraction_attempts",
        list(_OLD_COLUMNS),
    )
    op.drop_index(_INDEX, table_name="catalogue_extraction_attempts")
    op.drop_column("catalogue_extraction_attempts", "extraction_job_key")
